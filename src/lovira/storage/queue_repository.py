"""
Lovira-Facebook Manager
Quản lý Hàng đợi Đăng bài Nguyên tử (PublishQueueRepository)
- Xử lý giao dịch nguyên tử SQLite cho từng nhóm bài đăng đa Page
- Chống tạo trùng lặp tác vụ khi người dùng bấm đúp bằng client_request_id (AC-15)
- Ghi nhận trạng thái độc lập từng Page (AC-05, AC-14)
"""

import json
import uuid
from typing import List, Optional, Dict, Any
from .db import DatabaseManager
from src.lovira.domain.composer import ContentSnapshot, ScheduleMode


class PublishQueueRepository:
    """Quản lý các bảng publish_jobs, publish_attempts, job_events."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def enqueue_batch(
        self,
        client_request_id: str,
        snapshots: List[ContentSnapshot],
    ) -> List[str]:
        """
        Đưa một nhóm ContentSnapshot vào hàng đợi publish_jobs trong 1 transaction nguyên tử:
        - Nếu client_request_id đã tồn tại -> Trả về danh sách job_id cũ, KHÔNG tạo trùng (AC-15).
        - Mỗi snapshot tạo 1 publish_job độc lập cho Page tương ứng (Section 7.2).
        """
        if not snapshots:
            return []

        with self.db.transaction() as conn:
            # 1. Kiểm tra client_request_id chống bấm đúp
            cursor = conn.execute(
                "SELECT id FROM publish_jobs WHERE client_request_id = ? ORDER BY created_at ASC;",
                (client_request_id,),
            )
            existing_jobs = [row["id"] for row in cursor.fetchall()]
            if existing_jobs:
                return existing_jobs

            job_ids: List[str] = []
            for snap in snapshots:
                job_id = f"job_{uuid.uuid4().hex[:12]}"
                initial_state = "scheduled_local" if snap.schedule_mode == ScheduleMode.LOCAL and snap.scheduled_at_utc else "queued"

                conn.execute(
                    """
                    INSERT INTO publish_jobs (
                        id, batch_id, client_request_id, page_id, content_snapshot,
                        revision, state, schedule_mode, scheduled_at_utc, timezone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        job_id,
                        snap.batch_id,
                        client_request_id,
                        snap.page_id,
                        snap.to_json(),
                        snap.revision,
                        initial_state,
                        snap.schedule_mode.value,
                        snap.scheduled_at_utc,
                        snap.timezone,
                    ),
                )
                job_ids.append(job_id)

            return job_ids

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một publish_job."""
        with self.db.connection_scope() as conn:
            cursor = conn.execute("SELECT * FROM publish_jobs WHERE id = ?;", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_jobs_by_batch(self, batch_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách các jobs thuộc cùng một batch."""
        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                "SELECT * FROM publish_jobs WHERE batch_id = ? ORDER BY page_id ASC;",
                (batch_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_jobs(self, limit: int = 100, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các publish_jobs kèm tên page và snapshot tóm tắt."""
        query = """
            SELECT j.id, j.batch_id, j.page_id, p.name as page_name, j.content_snapshot,
                   j.state, j.scheduled_at_utc, j.blocked_reason, j.last_error_code, j.created_at
            FROM publish_jobs j
            LEFT JOIN pages p ON j.page_id = p.id
        """
        params: List[Any] = []
        if state:
            query += " WHERE j.state = ?"
            params.append(state)
        query += " ORDER BY j.created_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, tuple(params))
            results = []
            for r in cursor.fetchall():
                d = dict(r)
                d["snapshot_caption"] = ""
                if d.get("content_snapshot"):
                    try:
                        snap = json.loads(d["content_snapshot"])
                        d["snapshot_caption"] = snap.get("caption") or snap.get("final_caption", "")
                    except Exception:
                        pass
                results.append(d)
            return results

    def update_job_outcome(
        self,
        job_id: str,
        state: str,
        post_id: Optional[str] = None,
        remote_scheduled_id: Optional[str] = None,
        last_error_code: Optional[str] = None,
    ) -> None:
        """Cập nhật trạng thái và lưu ID bài viết/video Facebook (AC-14)."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE publish_jobs
                SET state = ?,
                    remote_scheduled_id = COALESCE(?, remote_scheduled_id),
                    last_error_code = ?,
                    updated_at = datetime('now', 'utc')
                WHERE id = ?;
                """,
                (state, remote_scheduled_id or post_id, last_error_code, job_id),
            )

    def record_attempt(
        self,
        job_id: str,
        attempt_no: int,
        outcome: str,
        upload_id: Optional[str] = None,
        video_id: Optional[str] = None,
        post_id: Optional[str] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        """Lưu lịch sử một lần thử đăng để đối chiếu trước khi retry (Section 7.3, AC-14)."""
        attempt_id = f"att_{uuid.uuid4().hex[:10]}"
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO publish_attempts (
                    id, job_id, attempt_no, upload_id, video_id, post_id,
                    started_at, ended_at, outcome, error_detail
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'utc'), datetime('now', 'utc'), ?, ?);
                """,
                (attempt_id, job_id, attempt_no, upload_id, video_id, post_id, outcome, error_detail),
            )
            # Tăng attempt_count của job
            conn.execute(
                "UPDATE publish_jobs SET attempt_count = attempt_count + 1 WHERE id = ?;",
                (job_id,),
            )
