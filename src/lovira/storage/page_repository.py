"""
Lovira-Facebook Manager
Quản lý Fanpage, Nhóm & Xử lý Gỡ Page có Lịch (PageRepository)
- Lưu trữ Fanpage, nhóm Page, liên kết tài khoản (Section 5.3)
- Tích hợp SecretVault: Token được bảo vệ, database chỉ giữ token_ref
- Audit lịch local và lịch remote khi gỡ Page khỏi tool (AC-11)
"""

import json
import uuid
from typing import List, Optional, Dict, Any, Tuple
from .db import DatabaseManager
from src.lovira.security.vault import SecretVault


class PageRepository:
    """Quản lý các bảng pages, page_groups, account_page_links."""

    def __init__(self, db_manager: DatabaseManager, secret_vault: SecretVault):
        self.db = db_manager
        self.vault = secret_vault

    def create_page_group(self, name: str, color: str = "#3B82F6") -> str:
        """Tạo nhóm Fanpage mới."""
        group_id = f"grp_{uuid.uuid4().hex[:8]}"
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO page_groups (id, name, color) VALUES (?, ?, ?);",
                (group_id, name, color),
            )
        return group_id

    def list_page_groups(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả các nhóm Page."""
        with self.db.connection_scope() as conn:
            cursor = conn.execute("SELECT * FROM page_groups ORDER BY name ASC;")
            return [dict(row) for row in cursor.fetchall()]

    def upsert_page(
        self,
        facebook_page_id: str,
        name: str,
        avatar_url: str = "",
        group_id: Optional[str] = None,
        notes: str = "",
        status: str = "ready",
    ) -> str:
        """Thêm mới hoặc cập nhật thông tin Fanpage (unique theo facebook_page_id)."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT id FROM pages WHERE facebook_page_id = ?;",
                (facebook_page_id,),
            )
            existing = cursor.fetchone()
            if existing:
                page_id = existing["id"]
                conn.execute(
                    """
                    UPDATE pages
                    SET name = ?, avatar_url = ?, group_id = ?, notes = ?, status = ?, updated_at = datetime('now', 'utc')
                    WHERE id = ?;
                    """,
                    (name, avatar_url, group_id, notes, status, page_id),
                )
            else:
                page_id = f"page_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO pages (id, facebook_page_id, name, avatar_url, group_id, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (page_id, facebook_page_id, name, avatar_url, group_id, notes, status),
                )
        return page_id

    def save_page_token(self, page_id: str, raw_token: str, account_id: Optional[str] = None, tasks: Optional[List[str]] = None) -> str:
        """Lưu token an toàn vào SecretVault và cập nhật token_ref vào account_page_links."""
        token_key = f"fb_token_{page_id}"
        self.vault.set_secret(token_key, raw_token)

        # Important: [] means no permission has been proven. Do not fabricate
        # CREATE_CONTENT/MANAGE, which can make an unverified Page look ready.
        tasks_json = json.dumps(tasks if tasks is not None else [])
        acc_id = account_id or f"acc_direct_{page_id}"

        # Đảm bảo account_id tồn tại
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO facebook_accounts (id, facebook_user_id, name)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO NOTHING;
                """,
                (acc_id, acc_id, "Tài khoản kết nối"),
            )

            link_id = f"lnk_{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO account_page_links (id, account_id, page_id, token_ref, granted_tasks)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, page_id) DO UPDATE SET
                    token_ref = EXCLUDED.token_ref,
                    granted_tasks = EXCLUDED.granted_tasks,
                    checked_at = datetime('now', 'utc');
                """,
                (link_id, acc_id, page_id, token_key, tasks_json),
            )
        return token_key

    def update_page_status(self, page_id: str, status: str) -> None:
        """Cập nhật trạng thái kết nối của Fanpage (ready, token_expired, unverified, insufficient_permissions)."""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE pages SET status = ?, updated_at = datetime('now', 'utc') WHERE id = ?;",
                (status, page_id),
            )

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết của một Fanpage theo ID."""
        with self.db.connection_scope() as conn:
            cursor = conn.execute("SELECT * FROM pages WHERE id = ?;", (page_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_page_token(self, page_id: str) -> Optional[str]:
        """Truy xuất token giải mã từ SecretVault."""
        token_key = f"fb_token_{page_id}"
        return self.vault.get_secret(token_key)

    def list_pages(self, group_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các Page kèm thông tin nhóm và quyền tác vụ."""
        query = """
            SELECT p.*, g.name AS group_name, g.color AS group_color, l.granted_tasks
            FROM pages p
            LEFT JOIN page_groups g ON p.group_id = g.id
            LEFT JOIN account_page_links l ON p.id = l.page_id
        """
        params: List[Any] = []
        if group_id:
            query += " WHERE p.group_id = ?"
            params.append(group_id)

        query += " ORDER BY p.name ASC;"

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, params)
            pages: List[Dict[str, Any]] = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("granted_tasks"):
                    try:
                        d["granted_tasks"] = json.loads(d["granted_tasks"])
                    except json.JSONDecodeError:
                        d["granted_tasks"] = []
                else:
                    d["granted_tasks"] = []
                pages.append(d)
            return pages

    def check_page_schedules(self, page_id: str) -> Dict[str, Any]:
        """
        Kiểm tra các lịch đăng đang chờ của Page (AC-11):
        - local_count: các lịch đang trong hàng đợi của Lovira trên máy
        - remote_count: các lịch đã được Facebook tiếp nhận thành công
        """
        local_count = 0
        remote_count = 0
        remote_jobs: List[Dict[str, Any]] = []

        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT id, batch_id, state, schedule_mode, remote_scheduled_id, scheduled_at_utc
                FROM publish_jobs
                WHERE page_id = ? AND state IN ('scheduled_local', 'queued', 'scheduled_remote', 'processing');
                """,
                (page_id,),
            )
            for row in cursor.fetchall():
                if row["state"] == "scheduled_remote" or row["remote_scheduled_id"]:
                    remote_count += 1
                    remote_jobs.append({
                        "job_id": row["id"],
                        "remote_scheduled_id": row["remote_scheduled_id"],
                        "scheduled_at_utc": row["scheduled_at_utc"],
                    })
                else:
                    local_count += 1

        return {
            "page_id": page_id,
            "local_count": local_count,
            "remote_count": remote_count,
            "remote_jobs": remote_jobs,
        }

    def unlink_page(self, page_id: str, force: bool = False) -> Tuple[bool, str]:
        """
        Gỡ Page khỏi Lovira (AC-11):
        - Nếu có lịch đang chờ và force=False -> Từ chối và hiển thị chi tiết số lịch local & remote
        - Nếu force=True -> Xóa liên kết, xóa Page khỏi tool (KHÔNG xóa fanpage thật trên Facebook)
        """
        sched = self.check_page_schedules(page_id)
        total_sched = sched["local_count"] + sched["remote_count"]

        if total_sched > 0 and not force:
            return (
                False,
                f"Page này đang có {sched['local_count']} lịch trên máy và {sched['remote_count']} lịch đã gửi Facebook. "
                f"Vui lòng xác nhận hủy hoặc quản lý các lịch này trước khi gỡ liên kết.",
            )

        # Xóa secret khỏi vault
        self.vault.delete_secret(f"fb_token_{page_id}")

        with self.db.transaction() as conn:
            # Xóa các lịch liên quan khi force=True (đã được người dùng xác nhận)
            conn.execute("DELETE FROM publish_jobs WHERE page_id = ?;", (page_id,))
            # Xóa các liên kết và page
            conn.execute("DELETE FROM account_page_links WHERE page_id = ?;", (page_id,))
            conn.execute("DELETE FROM pages WHERE id = ?;", (page_id,))

        return True, "Đã gỡ liên kết Page khỏi Lovira thành công."
