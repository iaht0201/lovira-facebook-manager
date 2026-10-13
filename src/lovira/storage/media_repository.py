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
    ) -> str:
        """Thêm mới một tài sản media vào cơ sở dữ liệu."""
        asset_id = f"med_{uuid.uuid4().hex[:12]}"
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO media_assets (
                    id, source_platform, source_id, source_url, local_path,
                    checksum, duration, width, height, size_bytes,
                    thumbnail_path, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                ),
            )
        return asset_id

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
