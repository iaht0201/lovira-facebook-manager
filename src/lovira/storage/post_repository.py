"""
Lovira-Facebook Manager
Quản lý Bộ nhớ đệm Bài viết & Giám sát Facebook Reels (PostCacheRepository & PostSyncService)
- Quản lý posts_cache: Lưu trữ bài viết và Facebook Reels thuộc Page quản lý (Section 6.1, 6.2)
- Hỗ trợ lọc theo Page, loại bài (post, reels), tìm kiếm caption
- Xử lý chỉ số tương tác (views, likes, comments): Nếu thiếu quyền đọc hoặc không có dữ liệu,
  trả về None / 'Chưa có dữ liệu', KHÔNG gán 0 (AC-10)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from src.lovira.storage.db import DatabaseManager
from src.lovira.integrations.facebook.client import FacebookGraphClient

logger = logging.getLogger(__name__)


class PostCacheRepository:
    """Quản lý dữ liệu bộ nhớ đệm bài viết & Facebook Reels trong SQLite."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def upsert_post(
        self,
        page_id: str,
        remote_post_id: str,
        post_type: str,
        metadata: Dict[str, Any],
    ) -> str:
        """Thêm hoặc cập nhật bài viết / Reel trong cache."""
        post_id = f"post_{uuid.uuid4().hex[:12]}"
        meta_json = json.dumps(metadata, ensure_ascii=False)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO posts_cache (id, page_id, remote_post_id, post_type, metadata, synced_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'utc'))
                ON CONFLICT(page_id, remote_post_id) DO UPDATE SET
                    post_type = excluded.post_type,
                    metadata = excluded.metadata,
                    synced_at = excluded.synced_at;
                """,
                (post_id, page_id, remote_post_id, post_type, meta_json),
            )
        return post_id

    def get_post(self, page_id: str, remote_post_id: str) -> Optional[Dict[str, Any]]:
        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT id, page_id, remote_post_id, post_type, metadata, synced_at
                FROM posts_cache
                WHERE page_id = ? AND remote_post_id = ?;
                """,
                (page_id, remote_post_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "page_id": row["page_id"],
                "remote_post_id": row["remote_post_id"],
                "post_type": row["post_type"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "synced_at": row["synced_at"],
            }

    def list_posts(
        self,
        page_id: Optional[str] = None,
        post_type: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lọc và tìm kiếm danh sách bài viết / Reels đã đồng bộ."""
        query = "SELECT id, page_id, remote_post_id, post_type, metadata, synced_at FROM posts_cache WHERE 1=1"
        params: List[Any] = []

        if page_id:
            query += " AND page_id = ?"
            params.append(page_id)

        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)

        if search_query:
            query += " AND metadata LIKE ?"
            params.append(f"%{search_query}%")

        query += " ORDER BY synced_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, tuple(params))
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "id": row["id"],
                        "page_id": row["page_id"],
                        "remote_post_id": row["remote_post_id"],
                        "post_type": row["post_type"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "synced_at": row["synced_at"],
                    }
                )
            return results

    def delete_post(self, page_id: str, remote_post_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM posts_cache WHERE page_id = ? AND remote_post_id = ?;",
                (page_id, remote_post_id),
            )
            return cursor.rowcount > 0


class FacebookPostSyncService:
    """Đồng bộ bài viết và Facebook Reels từ Graph API về cơ sở dữ liệu local."""

    def __init__(self, fb_client: FacebookGraphClient, post_repo: PostCacheRepository):
        self.fb = fb_client
        self.repo = post_repo

    @staticmethod
    def parse_reels_metadata(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bóc tách metadata Facebook Reels chuẩn hóa.
        AC-10: Các chỉ số không có quyền đọc (views, insights) phải là None / 'Chưa có dữ liệu',
        tuyệt đối không tự ý gán số 0.
        """
        parsed = {
            "id": raw_data.get("id"),
            "caption": raw_data.get("description") or raw_data.get("message") or "",
            "created_time": raw_data.get("created_time"),
            "permalink_url": raw_data.get("permalink_url"),
            "thumbnail_url": raw_data.get("picture") or raw_data.get("thumbnail_url"),
            "status": raw_data.get("status", {}).get("video_status", "published") if isinstance(raw_data.get("status"), dict) else "published",
        }

        # Bóc tách insights / chỉ số
        insights = raw_data.get("insights")
        if insights and isinstance(insights, dict) and "data" in insights:
            metrics_dict = {}
            for item in insights["data"]:
                m_name = item.get("name")
                values = item.get("values", [{}])
                metrics_dict[m_name] = values[0].get("value")
            parsed["views"] = metrics_dict.get("post_video_views")
            parsed["likes"] = metrics_dict.get("post_reactions_like_total")
        else:
            # AC-10: Thiếu quyền đọc chỉ số insights -> Gán None (Chưa có dữ liệu), không gán 0
            parsed["views"] = None
            parsed["likes"] = None

        return parsed

    def sync_reels_for_page(
        self,
        page_id: str,
        facebook_page_id: str,
        page_token: str,
    ) -> List[Dict[str, Any]]:
        """
        Đồng bộ danh sách Reels thuộc Page quản lý từ Facebook Graph API (Section 6.2).
        """
        endpoint = f"/{facebook_page_id}/video_reels"
        params = {
            "fields": "id,description,created_time,permalink_url,picture,status",
            "access_token": page_token,
            "limit": 25,
        }

        url = self.fb._url(endpoint)
        try:
            resp = self.fb.session.get(url, params=params, timeout=15.0)
            if resp.status_code != 200:
                logger.warning(f"Lỗi khi đồng bộ Reels của Page {facebook_page_id}: {resp.text}")
                return []

            data = resp.json().get("data", [])
            synced_posts = []

            for raw_item in data:
                parsed_meta = self.parse_reels_metadata(raw_item)
                remote_id = parsed_meta["id"]
                if remote_id:
                    self.repo.upsert_post(
                        page_id=page_id,
                        remote_post_id=remote_id,
                        post_type="reels",
                        metadata=parsed_meta,
                    )
                    synced_posts.append(parsed_meta)

            logger.info(f"Đã đồng bộ thành công {len(synced_posts)} Reels cho Page {facebook_page_id}.")
            return synced_posts

        except Exception as e:
            logger.error(f"Ngoại lệ khi đồng bộ Reels: {e}")
            return []
