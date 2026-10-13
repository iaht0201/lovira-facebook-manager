"""
Lovira-Facebook Manager
Khôi phục Sự cố, Xử lý Trạng thái Unknown & Backoff Retry (RecoveryManager)
- Khôi phục các tác vụ mồ côi (orphaned jobs) khi crash hoặc mất điện (AC-14)
- Tránh đăng bài trùng lặp qua quy trình đối chiếu trạng thái (Reconciliation)
- Thuật toán Exponential Backoff có Jitter khi gặp Rate Limit hoặc lỗi mạng (AC-21)
"""

import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Quản lý khôi phục sau sự cố và tính toán nhịp retry."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        queue_repo: PublishQueueRepository,
        page_repo: PageRepository,
        fb_client: FacebookGraphClient,
    ):
        self.db = db_manager
        self.queue = queue_repo
        self.page_repo = page_repo
        self.fb_client = fb_client

    @staticmethod
    def calculate_backoff_delay(
        attempt_count: int,
        base_delay_seconds: float = 30.0,
        max_delay_seconds: float = 1800.0,  # Tối đa 30 phút
    ) -> float:
        """
        Tính thời gian chờ thử lại Exponential Backoff kèm Jitter ngẫu nhiên (AC-21).
        Công thức: min(max_delay, base_delay * 2^(attempt - 1)) + jitter
        """
        exp_delay = min(max_delay_seconds, base_delay_seconds * (2 ** max(0, attempt_count - 1)))
        # Jitter ngẫu nhiên từ 10% đến 30% thời gian delay
        jitter = random.uniform(exp_delay * 0.1, exp_delay * 0.3)
        return exp_delay + jitter

    def recover_orphaned_jobs(self) -> int:
        """
        Quét khi ứng dụng khởi động lại:
        Chuyển các tác vụ đang treo ('publishing', 'uploading') quá hạn lease thành 'unknown' (AC-14).
        """
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE publish_jobs
                SET state = 'unknown',
                    blocked_reason = 'Ứng dụng bị dừng đột ngột trong lúc gửi. Cần đối chiếu trạng thái để tránh đăng trùng.',
                    worker_lease_until = NULL,
                    updated_at = datetime('now', 'utc')
                WHERE state IN ('publishing', 'uploading')
                  AND (worker_lease_until IS NULL OR worker_lease_until < ?);
                """,
                (now_str,),
            )
            count = cursor.rowcount
            if count > 0:
                logger.warning(f"Đã phát hiện và chuyển {count} tác vụ bị gián đoạn sang trạng thái 'unknown' (AC-14).")
            return count

    def reconcile_job(self, job_id: str) -> Tuple[bool, str]:
        """
        Đối chiếu trạng thái của tác vụ 'unknown' với Facebook:
        - Nếu tìm thấy post_id / video_id đã tồn tại -> Chuyển sang 'published'
        - Nếu chắc chắn chưa đăng -> Chuyển sang 'failed_retryable' để thử lại
        """
        job = self.queue.get_job(job_id)
        if not job:
            return False, "Không tìm thấy tác vụ."

        page_id = job["page_id"]
        page_token = self.page_repo.get_page_token(page_id)
        if not page_token:
            return False, "Không tìm thấy token của Page để đối chiếu."

        # Kiểm tra lần thử gần nhất trong publish_attempts
        with self.db.connection_scope() as conn:
            cursor = conn.execute(
                "SELECT * FROM publish_attempts WHERE job_id = ? ORDER BY started_at DESC LIMIT 1;",
                (job_id,),
            )
            last_attempt = cursor.fetchone()

        candidate_id = job.get("remote_scheduled_id") or (last_attempt["post_id"] if last_attempt else None)

        if candidate_id:
            # Truy vấn kiểm tra ID bài viết trên Facebook
            url = self.fb_client._url(f"/{candidate_id}")
            try:
                resp = self.fb_client.session.get(url, params={"access_token": page_token}, timeout=10.0)
                if resp.status_code == 200:
                    # Bài viết thực sự đã tồn tại trên Facebook!
                    self.queue.update_job_outcome(
                        job_id=job_id,
                        state="published",
                        post_id=candidate_id,
                    )
                    return True, "Đối chiếu thành công: Bài viết đã xuất hiện trên Facebook."
            except Exception:
                pass

        # Chưa thể xác minh chắc chắn
        return False, "Chưa xác minh được trạng thái trên Facebook. Vui lòng kiểm tra Fanpage trước khi thử lại."
