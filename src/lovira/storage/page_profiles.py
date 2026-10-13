"""Non-sensitive Page enrichment cache, backwards-compatible with Lovira's SQLite DB.

Tokens remain exclusively in SecretVault. The new table stores *metadata only*.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PageProfileStore:
    def __init__(self, db_manager):
        self.db = db_manager
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.db.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_profile_cache (
                    page_id TEXT PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
                    public_json TEXT NOT NULL DEFAULT '{}',
                    token_meta_json TEXT NOT NULL DEFAULT '{}',
                    public_checked_at TEXT,
                    token_checked_at TEXT
                )
            """)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        with self.db.connection_scope() as conn:
            rows = conn.execute("SELECT * FROM page_profile_cache").fetchall()
        return {str(r["page_id"]): self._decode(r) for r in rows}

    def get(self, page_id: str) -> Dict[str, Any]:
        with self.db.connection_scope() as conn:
            row = conn.execute("SELECT * FROM page_profile_cache WHERE page_id=?", (page_id,)).fetchone()
        return self._decode(row) if row else {"public": {}, "token": {}}

    @staticmethod
    def _decode(row) -> Dict[str, Any]:
        return {
            "public": json.loads(row["public_json"] or "{}"),
            "token": json.loads(row["token_meta_json"] or "{}"),
            "public_checked_at": row["public_checked_at"],
            "token_checked_at": row["token_checked_at"],
        }

    def save_public(self, page_id: str, details: Dict[str, Any]) -> None:
        """Merge good fields; a partial API response does not erase previous data."""
        cached = self.get(page_id).get("public", {})
        merged = {**cached, **{k: v for k, v in details.items() if v is not None}}
        if details.get("followers_count") is not None or details.get("fan_count") is not None:
            merged["metrics_checked_at"] = _utcnow()
        with self.db.transaction() as conn:
            conn.execute("""
                INSERT INTO page_profile_cache(page_id, public_json, public_checked_at)
                VALUES (?, ?, ?)
                ON CONFLICT(page_id) DO UPDATE SET
                    public_json=excluded.public_json,
                    public_checked_at=excluded.public_checked_at
            """, (page_id, json.dumps(merged, ensure_ascii=False), _utcnow()))
            if merged.get("name") or merged.get("avatar_url"):
                conn.execute("""
                    UPDATE pages SET
                        name=COALESCE(NULLIF(?, ''), name),
                        avatar_url=COALESCE(NULLIF(?, ''), avatar_url),
                        updated_at=datetime('now')
                    WHERE id=?
                """, (merged.get("name"), merged.get("avatar_url"), page_id))

    def save_token_meta(self, page_id: str, meta: Dict[str, Any]) -> None:
        """Never store access tokens, app secrets or full raw Graph responses."""
        allow = {
            "expires_at", "data_access_expires_at", "scopes", "tasks",
            "is_valid", "status", "type", "error", "identity_verified"
        }
        safe = {k: v for k, v in meta.items() if k in allow}
        with self.db.transaction() as conn:
            conn.execute("""
                INSERT INTO page_profile_cache(page_id, token_meta_json, token_checked_at)
                VALUES (?, ?, ?)
                ON CONFLICT(page_id) DO UPDATE SET
                    token_meta_json=excluded.token_meta_json,
                    token_checked_at=excluded.token_checked_at
            """, (page_id, json.dumps(safe, ensure_ascii=False), _utcnow()))

    def set_status(self, page_id: str, status: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE pages SET status=?, updated_at=datetime('now') WHERE id=?", (status, page_id))
