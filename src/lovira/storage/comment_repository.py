"""
Lovira-Facebook Manager
Quản lý Bộ nhớ đệm Bình luận & Mẫu phản hồi (CommentCacheRepository, ReplyTemplateRepository & FacebookCommentService)
- Quản lý comments_cache: lưu trữ bình luận theo Page và bài viết (Section 6.3)
- Quản lý reply_templates: mẫu trả lời có tên, nội dung, nhóm và phạm vi áp dụng Page
- Tương tác Graph API: đồng bộ bình luận, trả lời với tư cách Page, ẩn/bỏ ẩn bình luận
"""

import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from src.lovira.storage.db import DatabaseManager
from src.lovira.integrations.facebook.client import FacebookGraphClient

logger = logging.getLogger(__name__)


class CommentCacheRepository:
    """Quản lý cache bình luận từ Facebook trong SQLite."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def upsert_comment(
        self,
        page_id: str,
        remote_comment_id: str,
        post_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> str:
        comment_id = f"comment_{uuid.uuid4().hex[:12]}"
        meta_json = json.dumps(metadata, ensure_ascii=False)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO comments_cache (id, page_id, remote_comment_id, post_id, metadata, synced_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'utc'))
                ON CONFLICT(page_id, remote_comment_id) DO UPDATE SET
                    post_id = excluded.post_id,
                    metadata = excluded.metadata,
                    synced_at = excluded.synced_at;
                """,
                (comment_id, page_id, remote_comment_id, post_id, meta_json),
            )
        return comment_id

    def get_comment(self, page_id: str, remote_comment_id: str) -> Optional[Dict[str, Any]]:
        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT id, page_id, remote_comment_id, post_id, metadata, synced_at
                FROM comments_cache
                WHERE page_id = ? AND remote_comment_id = ?;
                """,
                (page_id, remote_comment_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "page_id": row["page_id"],
                "remote_comment_id": row["remote_comment_id"],
                "post_id": row["post_id"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "synced_at": row["synced_at"],
            }

    def list_comments(
        self,
        page_id: Optional[str] = None,
        post_id: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = "SELECT id, page_id, remote_comment_id, post_id, metadata, synced_at FROM comments_cache WHERE 1=1"
        params: List[Any] = []

        if page_id:
            query += " AND page_id = ?"
            params.append(page_id)

        if post_id:
            query += " AND post_id = ?"
            params.append(post_id)

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
                        "remote_comment_id": row["remote_comment_id"],
                        "post_id": row["post_id"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "synced_at": row["synced_at"],
                    }
                )
            return results

    def delete_comment(self, page_id: str, remote_comment_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM comments_cache WHERE page_id = ? AND remote_comment_id = ?;",
                (page_id, remote_comment_id),
            )
            return cursor.rowcount > 0


class ReplyTemplateRepository:
    """Quản lý các mẫu phản hồi bình luận & sản phẩm Shopee (Section 6.3)."""

    _instance: Optional["ReplyTemplateRepository"] = None

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._ensure_schema()
        ReplyTemplateRepository._instance = self

    @classmethod
    def get_instance(cls, db_manager: Optional[DatabaseManager] = None) -> Optional["ReplyTemplateRepository"]:
        """Lấy instance toàn cục của ReplyTemplateRepository."""
        if cls._instance is None and db_manager is not None:
            cls._instance = ReplyTemplateRepository(db_manager)
        return cls._instance

    def _ensure_schema(self) -> None:
        """Đảm bảo các cột product_url, image_url, local_image_path, price tồn tại."""
        try:
            with self.db.transaction() as conn:
                cursor = conn.execute("PRAGMA table_info(reply_templates);")
                columns = {row["name"] for row in cursor.fetchall()}
                if "product_url" not in columns:
                    conn.execute("ALTER TABLE reply_templates ADD COLUMN product_url TEXT;")
                if "image_url" not in columns:
                    conn.execute("ALTER TABLE reply_templates ADD COLUMN image_url TEXT;")
                if "local_image_path" not in columns:
                    conn.execute("ALTER TABLE reply_templates ADD COLUMN local_image_path TEXT;")
                if "price" not in columns:
                    conn.execute("ALTER TABLE reply_templates ADD COLUMN price TEXT;")
        except Exception as e:
            logger.debug(f"Schema update for reply_templates: {e}")

    def create_template(
        self,
        name: str,
        content: str,
        group_id: Optional[str] = None,
        page_scope: Optional[List[str]] = None,
        product_url: Optional[str] = None,
        image_url: Optional[str] = None,
        local_image_path: Optional[str] = None,
        price: Optional[str] = None,
    ) -> str:
        template_id = f"tpl_{uuid.uuid4().hex[:12]}"
        scope_json = json.dumps(page_scope, ensure_ascii=False) if page_scope else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO reply_templates (
                    id, name, content, group_id, page_scope,
                    product_url, image_url, local_image_path, price,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'utc'), datetime('now', 'utc'));
                """,
                (
                    template_id,
                    name,
                    content,
                    group_id,
                    scope_json,
                    product_url,
                    image_url,
                    local_image_path,
                    price,
                ),
            )
        return template_id

    def list_templates(
        self,
        page_id: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.db.connection_scope() as conn:
            query = """
                SELECT id, name, content, group_id, page_scope,
                       product_url, image_url, local_image_path, price,
                       created_at, updated_at
                FROM reply_templates
                ORDER BY updated_at DESC;
            """
            cursor = conn.execute(query)
            all_templates = []
            for row in cursor.fetchall():
                scope = json.loads(row["page_scope"]) if row["page_scope"] else None
                if page_id and scope is not None and page_id not in scope:
                    continue
                if group_id and row["group_id"] != group_id:
                    continue
                all_templates.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "content": row["content"],
                        "group_id": row["group_id"],
                        "page_scope": scope,
                        "product_url": row["product_url"] or "",
                        "image_url": row["image_url"] or "",
                        "local_image_path": row["local_image_path"] or "",
                        "price": row["price"] or "",
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )
            return all_templates

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, content, group_id, page_scope,
                       product_url, image_url, local_image_path, price,
                       created_at, updated_at
                FROM reply_templates WHERE id = ?;
                """,
                (template_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "content": row["content"],
                "group_id": row["group_id"],
                "page_scope": json.loads(row["page_scope"]) if row["page_scope"] else None,
                "product_url": row["product_url"] or "",
                "image_url": row["image_url"] or "",
                "local_image_path": row["local_image_path"] or "",
                "price": row["price"] or "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        content: Optional[str] = None,
        page_scope: Optional[List[str]] = None,
        product_url: Optional[str] = None,
        image_url: Optional[str] = None,
        local_image_path: Optional[str] = None,
        price: Optional[str] = None,
    ) -> bool:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if page_scope is not None:
            updates.append("page_scope = ?")
            params.append(json.dumps(page_scope, ensure_ascii=False))
        if product_url is not None:
            updates.append("product_url = ?")
            params.append(product_url)
        if image_url is not None:
            updates.append("image_url = ?")
            params.append(image_url)
        if local_image_path is not None:
            updates.append("local_image_path = ?")
            params.append(local_image_path)
        if price is not None:
            updates.append("price = ?")
            params.append(price)

        if not updates:
            return False

        updates.append("updated_at = datetime('now', 'utc')")
        params.append(template_id)

        sql = f"UPDATE reply_templates SET {', '.join(updates)} WHERE id = ?;"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            return cursor.rowcount > 0

    def delete_template(self, template_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM reply_templates WHERE id = ?;", (template_id,))
            return cursor.rowcount > 0

    def import_templates(self, items: List[Dict[str, Any]]) -> int:
        """Nhập danh sách mẫu câu / sản phẩm hàng loạt."""
        imported_count = 0
        for it in items:
            name = (it.get("name") or "").strip()
            content = (it.get("content") or "").strip()
            if not name and not content:
                continue
            if not name and content:
                name = content[:30] + "..." if len(content) > 30 else content
            if not content and name:
                content = name

            self.create_template(
                name=name,
                content=content,
                product_url=it.get("product_url"),
                image_url=it.get("image_url"),
                local_image_path=it.get("local_image_path"),
                price=it.get("price"),
            )
            imported_count += 1
        return imported_count


class FacebookCommentService:
    """Tương tác Graph API để đồng bộ và phản hồi bình luận."""

    def __init__(self, fb_client: FacebookGraphClient, comment_repo: CommentCacheRepository):
        self.fb = fb_client
        self.repo = comment_repo

    def sync_comments_for_post(
        self,
        page_id: str,
        remote_post_id: str,
        page_token: str,
    ) -> List[Dict[str, Any]]:
        """Đồng bộ bình luận của một bài viết từ Graph API."""
        endpoint = f"/{remote_post_id}/comments"
        params = {
            "fields": "id,message,from,created_time,like_count,comment_count",
            "access_token": page_token,
            "limit": 50,
        }
        url = self.fb._url(endpoint)
        try:
            resp = self.fb.session.get(url, params=params, timeout=15.0)
            if resp.status_code != 200:
                logger.warning(f"Lỗi khi tải bình luận cho bài {remote_post_id}: {resp.text}")
                return []

            data = resp.json().get("data", [])
            synced = []
            for item in data:
                c_id = item.get("id")
                if c_id:
                    self.repo.upsert_comment(
                        page_id=page_id,
                        remote_comment_id=c_id,
                        post_id=remote_post_id,
                        metadata=item,
                    )
                    synced.append(item)
            return synced
        except Exception as e:
            logger.error(f"Ngoại lệ khi đồng bộ bình luận: {e}")
            return []

    def reply_to_comment(
        self,
        remote_comment_id: str,
        message: str,
        page_token: str,
    ) -> Optional[str]:
        """Trả lời bình luận với tư cách Page."""
        endpoint = f"/{remote_comment_id}/comments"
        url = self.fb._url(endpoint)
        try:
            resp = self.fb.session.post(
                url,
                data={"message": message, "access_token": page_token},
                timeout=15.0,
            )
            if resp.status_code == 200:
                return resp.json().get("id")
            logger.warning(f"Lỗi trả lời bình luận {remote_comment_id}: {resp.text}")
            return None
        except Exception as e:
            logger.error(f"Ngoại lệ khi trả lời bình luận: {e}")
            return None

    def hide_comment(
        self,
        remote_comment_id: str,
        is_hidden: bool,
        page_token: str,
    ) -> bool:
        """Ẩn hoặc bỏ ẩn bình luận."""
        endpoint = f"/{remote_comment_id}"
        url = self.fb._url(endpoint)
        try:
            resp = self.fb.session.post(
                url,
                data={"is_hidden": "true" if is_hidden else "false", "access_token": page_token},
                timeout=10.0,
            )
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Ngoại lệ khi ẩn bình luận: {e}")
            return False
