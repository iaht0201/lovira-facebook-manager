"""
Lovira-Facebook Manager
Quản lý Kho Tài nguyên Media & Kiểm tra Tham chiếu (MediaRepository)
- Lưu trữ, truy vấn, tìm kiếm media_assets
- Kiểm tra tính toàn vẹn và audit tham chiếu với drafts & publish_jobs (AC-12, AC-42)
- Ngăn chặn xóa file media đang được lịch hẹn giờ chờ đăng tham chiếu
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from .db import DatabaseManager


class MediaRepository:
    """Quản lý bảng media_assets và các mối quan hệ tham chiếu dữ liệu."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Đảm bảo các cột title, hashtags, target_page_id, caption, first_comment tồn tại trong bảng media_assets."""
        try:
            with self.db.transaction() as conn:
                cursor = conn.execute("PRAGMA table_info(media_assets);")
                columns = [row[1] for row in cursor.fetchall()]
                if columns:
                    if "title" not in columns:
                        conn.execute("ALTER TABLE media_assets ADD COLUMN title TEXT;")
                    if "hashtags" not in columns:
                        conn.execute("ALTER TABLE media_assets ADD COLUMN hashtags TEXT;")
                    if "target_page_id" not in columns:
                        conn.execute("ALTER TABLE media_assets ADD COLUMN target_page_id TEXT;")
                    if "caption" not in columns:
                        conn.execute("ALTER TABLE media_assets ADD COLUMN caption TEXT;")
                    if "first_comment" not in columns:
                        conn.execute("ALTER TABLE media_assets ADD COLUMN first_comment TEXT;")
        except Exception:
            pass

    def add_media_asset(
        self,
        local_path: Path,
        checksum: str,
        size_bytes: int,
        duration: float,
        source_platform: str = "local",
        source_id: Optional[str] = None,
        source_url: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        thumbnail_path: Optional[Path] = None,
        tags: Optional[str] = None,
        title: Optional[str] = None,
        hashtags: Optional[str] = None,
        target_page_id: Optional[str] = None,
    ) -> str:
        """Thêm mới một tài sản media vào cơ sở dữ liệu."""
        asset_id = f"med_{uuid.uuid4().hex[:12]}"
        self._ensure_columns()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO media_assets (
                    id, source_platform, source_id, source_url, local_path,
                    checksum, duration, width, height, size_bytes,
                    thumbnail_path, tags, title, hashtags, target_page_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    asset_id,
                    source_platform,
                    source_id,
                    source_url,
                    str(local_path),
                    checksum,
                    duration,
                    width,
                    height,
                    size_bytes,
                    str(thumbnail_path) if thumbnail_path else None,
                    tags,
                    title,
                    hashtags,
                    target_page_id,
                ),
            )
        return asset_id

    def update_target_page(self, asset_id: str, page_id: Optional[str]) -> None:
        """Cập nhật Fanpage đích gán cho video."""
        self._ensure_columns()
        with self.db.transaction() as conn:
            conn.execute("UPDATE media_assets SET target_page_id = ? WHERE id = ?;", (page_id, asset_id))

    def update_metadata(
        self,
        asset_id: str,
        title: Optional[str] = None,
        hashtags: Optional[str] = None,
        caption: Optional[str] = None,
        first_comment: Optional[str] = None,
        target_page_id: Optional[str] = None,
    ) -> None:
        """Cập nhật tiêu đề, hashtags, caption, bình luận và fanpage đích cho video."""
        self._ensure_columns()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE media_assets 
                SET title = COALESCE(?, title), 
                    hashtags = COALESCE(?, hashtags),
                    caption = COALESCE(?, caption),
                    first_comment = COALESCE(?, first_comment),
                    target_page_id = COALESCE(?, target_page_id)
                WHERE id = ?;
                """,
                (title, hashtags, caption, first_comment, target_page_id, asset_id),
            )

    def update_asset_full_metadata(
        self,
        asset_id: str,
        title: str = "",
        caption: str = "",
        hashtags: str = "",
        first_comment: str = "",
        target_page_id: Optional[str] = None,
    ) -> None:
        """Cập nhật toàn diện thông tin chỉnh sửa video từ hộp thoại."""
        self._ensure_columns()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE media_assets
                SET title = ?,
                    caption = ?,
                    hashtags = ?,
                    first_comment = ?,
                    target_page_id = ?
                WHERE id = ?;
                """,
                (title, caption, hashtags, first_comment, target_page_id, asset_id),
            )

    def get_media_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một media asset."""
        with self.db.connection_scope() as conn:
            cursor = conn.execute("SELECT * FROM media_assets WHERE id = ?;", (asset_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_media_assets(
        self,
        platform: Optional[str] = None,
        search_term: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Liệt kê danh sách media assets có hỗ trợ lọc và tìm kiếm."""
        query = "SELECT * FROM media_assets WHERE 1=1"
        params: List[Any] = []

        if platform:
            query += " AND source_platform = ?"
            params.append(platform)

        if search_term:
            query += " AND (local_path LIKE ? OR tags LIKE ? OR source_url LIKE ?)"
            wildcard = f"%{search_term}%"
            params.extend([wildcard, wildcard, wildcard])

        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def check_media_references(self, asset_id: str) -> Dict[str, Any]:
        """
        Kiểm tra xem media này có đang được sử dụng bởi drafts hoặc publish_jobs không (AC-12).
        Trả về số lượng nháp và số lượng lịch đăng đang chờ.
        """
        draft_count = 0
        active_job_count = 0
        active_jobs: List[Dict[str, Any]] = []

        with self.db.connection_scope() as conn:
            # 1. Kiểm tra drafts
            cur_drafts = conn.execute("SELECT id, title, media_refs FROM drafts;")
            for row in cur_drafts.fetchall():
                refs = row["media_refs"]
                if refs:
                    try:
                        ref_list = json.loads(refs)
                        if isinstance(ref_list, list) and asset_id in ref_list:
                            draft_count += 1
                    except json.JSONDecodeError:
                        pass

            # 2. Kiểm tra publish_jobs đang ở trạng thái chờ xử lý ('scheduled_local', 'queued', 'uploading', 'processing')
            active_states = ("scheduled_local", "queued", "uploading", "processing")
            placeholders = ",".join("?" for _ in active_states)
            query_jobs = f"""
                SELECT id, batch_id, page_id, state, scheduled_at_utc, content_snapshot
                FROM publish_jobs
                WHERE state IN ({placeholders});
            """
            cur_jobs = conn.execute(query_jobs, active_states)
            for row in cur_jobs.fetchall():
                snap = row["content_snapshot"]
                if snap:
                    try:
                        snap_data = json.loads(snap)
                        media_ids = snap_data.get("media_ids", [])
                        if asset_id in media_ids or snap_data.get("primary_media_id") == asset_id:
                            active_job_count += 1
                            active_jobs.append({
                                "job_id": row["id"],
                                "batch_id": row["batch_id"],
                                "page_id": row["page_id"],
                                "state": row["state"],
                                "scheduled_at_utc": row["scheduled_at_utc"],
                            })
                    except json.JSONDecodeError:
                        pass

        return {
            "asset_id": asset_id,
            "draft_count": draft_count,
            "active_job_count": active_job_count,
            "active_jobs": active_jobs,
        }

    def delete_media_asset(self, asset_id: str, force: bool = False, remove_file: bool = False) -> Tuple[bool, str]:
        """
        Xóa media asset khỏi hệ thống (AC-12):
        Nếu có active_jobs và force=False -> Từ chối xóa và cảnh báo rõ số lượng lịch bị ảnh hưởng.
        """
        asset = self.get_media_asset(asset_id)
        if not asset:
            return False, "Không tìm thấy media asset cần xóa."

        refs = self.check_media_references(asset_id)
        if refs["active_job_count"] > 0 and not force:
            return (
                False,
                f"Không thể xóa media này vì đang có {refs['active_job_count']} lịch đăng đang chờ thực hiện. "
                f"Vui lòng hủy hoặc thay đổi các lịch liên quan trước.",
            )

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM media_assets WHERE id = ?;", (asset_id,))

        if remove_file:
            try:
                local_file = Path(asset["local_path"])
                if local_file.exists():
                    local_file.unlink()
            except OSError as e:
                return True, f"Đã xóa bản ghi media nhưng không thể xóa file vật lý: {e}"

        return True, "Đã xóa media asset thành công."

    @staticmethod
    def _empty_usage_dict() -> Dict[str, Any]:
        return {
            "draft_count": 0,
            "scheduled_jobs": [],
            "published_jobs": [],
            "failed_jobs": [],
            "other_jobs": [],
        }

    def get_media_usage_summary(
        self, asset_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Lấy thông tin tổng hợp sử dụng (bài đăng, lịch, lỗi) cho danh sách media_ids.
        Hỗ trợ phân biệt trạng thái hiển thị của từng media trong Thư viện Media.
        """
        results: Dict[str, Dict[str, Any]] = {}
        target_set = set(asset_ids) if asset_ids else None

        active_states = {"scheduled_local", "queued", "uploading", "processing", "publishing"}
        published_states = {"published", "completed", "success"}
        failed_states = {"failed", "dead_letter", "error"}

        with self.db.connection_scope() as conn:
            # 1. Quét drafts
            try:
                cur_drafts = conn.execute("SELECT id, title, media_refs FROM drafts;")
                for row in cur_drafts.fetchall():
                    refs = row["media_refs"]
                    if refs:
                        try:
                            ref_list = json.loads(refs)
                            if isinstance(ref_list, list):
                                for aid in ref_list:
                                    if target_set is None or aid in target_set:
                                        if aid not in results:
                                            results[aid] = self._empty_usage_dict()
                                        results[aid]["draft_count"] += 1
                        except (json.JSONDecodeError, TypeError):
                            pass
            except Exception:
                pass

            # 2. Quét publish_jobs
            try:
                cur_jobs = conn.execute("""
                    SELECT pj.id, pj.batch_id, pj.page_id, pj.state, pj.scheduled_at_utc, pj.content_snapshot,
                           p.name AS page_name
                    FROM publish_jobs pj
                    LEFT JOIN pages p ON pj.page_id = p.id;
                """)
                for row in cur_jobs.fetchall():
                    snap = row["content_snapshot"]
                    if not snap:
                        continue
                    try:
                        snap_data = json.loads(snap)
                        media_ids = set()
                        if snap_data.get("primary_media_id"):
                            media_ids.add(snap_data["primary_media_id"])
                        for m in snap_data.get("media_ids", []):
                            media_ids.add(m)

                        for aid in media_ids:
                            if target_set is not None and aid not in target_set:
                                continue
                            if aid not in results:
                                results[aid] = self._empty_usage_dict()

                            job_info = {
                                "job_id": row["id"],
                                "batch_id": row["batch_id"],
                                "page_id": row["page_id"],
                                "page_name": row["page_name"] or row["page_id"],
                                "state": row["state"],
                                "scheduled_at_utc": row["scheduled_at_utc"],
                            }
                            st = row["state"]
                            if st in active_states:
                                results[aid]["scheduled_jobs"].append(job_info)
                            elif st in published_states:
                                results[aid]["published_jobs"].append(job_info)
                            elif st in failed_states:
                                results[aid]["failed_jobs"].append(job_info)
                            else:
                                results[aid]["other_jobs"].append(job_info)
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception:
                pass

        return results
