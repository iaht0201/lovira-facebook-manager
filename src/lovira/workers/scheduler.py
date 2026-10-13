"""
Lovira-Facebook Manager
Dịch vụ Lập lịch Local theo Giờ Việt Nam & Quản lý Hàng đợi Worker (LocalSchedulerService)
- Quét hàng đợi SQLite bền vững (Section 9.4)
- KHÔNG giữ transaction mở trong lúc gọi mạng (Section 9.4)
- Xử lý lỡ lịch khi máy ngủ hoặc tắt qua giờ đăng (`missed`) (AC-17)
- Kiểm tra điều kiện tiên quyết trước publish (License, Token, Media checksum) (AC-44)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.domain.composer import ContentSnapshot
from src.lovira.integrations.facebook.publisher import GraphPublishAdapter, PublishResult
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.licensing.models import LicenseSession

logger = logging.getLogger(__name__)


class LocalSchedulerService:
    """Quản lý quét, phân phối và thực thi các công việc đăng bài trong SQLite."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        queue_repo: PublishQueueRepository,
        page_repo: PageRepository,
        media_repo: MediaRepository,
        publisher: GraphPublishAdapter,
        policy_manager: AccessPolicyManager,
    ):
        self.db = db_manager
        self.queue = queue_repo
        self.page_repo = page_repo
        self.media_repo = media_repo
        self.publisher = publisher
        self.policy = policy_manager

    def poll_and_process_jobs(
        self,
        worker_id: str = "worker_main",
        max_drift_seconds: int = 900,  # 15 phút
        session: Optional[LicenseSession] = None,
        is_online: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Quét và xử lý các tác vụ đến giờ chạy:
        1. Xử lý tác vụ lỡ lịch (AC-17).
        2. Claim các tác vụ hợp lệ (ngắn gọn trong transaction để nhả khóa ngay).
        3. Thực hiện gọi mạng hoàn toàn ngoài transaction (Section 9.4).
        4. Cập nhật kết quả vào database.
        """
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        results: List[Dict[str, Any]] = []

        # BƯỚC 1: Quét và xử lý lỡ lịch hoặc claim tác vụ (Transaction ngắn)
        claimed_jobs: List[Tuple[str, str, ContentSnapshot, str]] = []  # (job_id, page_id, snapshot, page_token)

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, page_id, content_snapshot, state, scheduled_at_utc, revision
                FROM publish_jobs
                WHERE state IN ('scheduled_local', 'queued')
                  AND scheduled_at_utc <= ?
                  AND (worker_lease_until IS NULL OR worker_lease_until < ?)
                ORDER BY scheduled_at_utc ASC;
                """,
                (now_str, now_str),
            )
            due_jobs = [dict(row) for row in cursor.fetchall()]

            for job in due_jobs:
                job_id = job["id"]
                page_id = job["page_id"]
                sched_utc_str = job["scheduled_at_utc"]

                # Kiểm tra lỡ lịch (AC-17)
                try:
                    sched_time = datetime.fromisoformat(sched_utc_str.replace("Z", "+00:00"))
                    drift_seconds = (now - sched_time).total_seconds()
                except Exception:
                    drift_seconds = 0.0

                if drift_seconds > max_drift_seconds:
                    logger.warning(f"Tác vụ {job_id} đã bị lỡ lịch ({drift_seconds:.0f}s quá hạn khi máy tắt/ngủ).")
                    conn.execute(
                        """
                        UPDATE publish_jobs
                        SET state = 'missed',
                            blocked_reason = 'Máy tắt hoặc ngủ qua giờ hẹn',
                            updated_at = datetime('now', 'utc')
                        WHERE id = ?;
                        """,
                        (job_id,),
                    )
                    results.append({"job_id": job_id, "state": "missed", "reason": "drift_exceeded"})
                    continue

                # Kiểm tra quyền License trực tuyến (AC-28, AC-44)
                allowed, reason = self.policy.evaluate_action("publish_post", session=session, is_online=is_online)
                if not allowed:
                    logger.warning(f"Tác vụ {job_id} bị tạm dừng do quyền License: {reason}")
                    conn.execute(
                        """
                        UPDATE publish_jobs
                        SET state = 'paused',
                            blocked_reason = ?,
                            updated_at = datetime('now', 'utc')
                        WHERE id = ?;
                        """,
                        (reason, job_id),
                    )
                    results.append({"job_id": job_id, "state": "paused", "reason": reason})
                    continue

                # Phân tích snapshot
                try:
                    snapshot = ContentSnapshot.from_json(job["content_snapshot"])
                except Exception:
                    conn.execute(
                        "UPDATE publish_jobs SET state = 'failed_final', last_error_code = 'CORRUPT_SNAPSHOT' WHERE id = ?;",
                        (job_id,),
                    )
                    results.append({"job_id": job_id, "state": "failed_final", "reason": "corrupt_snapshot"})
                    continue

                # Kiểm tra file media nếu có (AC-42, AC-44)
                if snapshot.media_path:
                    media_file = Path(snapshot.media_path)
                    if not media_file.exists():
                        conn.execute(
                            """
                            UPDATE publish_jobs
                            SET state = 'failed_final',
                                blocked_reason = 'Không tìm thấy file video/media trên đĩa',
                                last_error_code = 'MEDIA_MISSING'
                            WHERE id = ?;
                            """,
                            (job_id,),
                        )
                        results.append({"job_id": job_id, "state": "failed_final", "reason": "media_missing"})
                        continue

                # Lấy Page Token từ SecretVault
                page_token = self.page_repo.get_page_token(page_id)
                if not page_token:
                    conn.execute(
                        """
                        UPDATE publish_jobs
                        SET state = 'failed_final',
                            blocked_reason = 'Page này cần kết nối lại (Thiếu Token)',
                            last_error_code = 'TOKEN_MISSING'
                        WHERE id = ?;
                        """,
                        (job_id,),
                    )
                    results.append({"job_id": job_id, "state": "failed_final", "reason": "token_missing"})
                    continue

                # Khóa lease ngắn gọn
                lease_until = (now + timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
                conn.execute(
                    "UPDATE publish_jobs SET state = 'publishing', worker_lease_until = ? WHERE id = ?;",
                    (lease_until, job_id),
                )
                claimed_jobs.append((job_id, page_id, snapshot, page_token))

        # BƯỚC 2: Gọi mạng NGOÀI transaction (Section 9.4)
        for job_id, page_id, snapshot, page_token in claimed_jobs:
            pub_result = self.publisher.publish(page_token, snapshot)

            if pub_result.success:
                self.queue.update_job_outcome(
                    job_id=job_id,
                    state="published",
                    post_id=pub_result.post_id,
                )
                self.queue.record_attempt(
                    job_id=job_id,
                    attempt_no=1,
                    outcome="success",
                    post_id=pub_result.post_id,
                    video_id=pub_result.video_id,
                )
                results.append({"job_id": job_id, "state": "published", "post_id": pub_result.post_id})
            else:
                new_state = "failed_retryable" if pub_result.is_transient else "failed_final"
                self.queue.update_job_outcome(
                    job_id=job_id,
                    state=new_state,
                    last_error_code=pub_result.error_code,
                )
                self.queue.record_attempt(
                    job_id=job_id,
                    attempt_no=1,
                    outcome=new_state,
                    error_detail=pub_result.error_message,
                )
                results.append({
                    "job_id": job_id,
                    "state": new_state,
                    "error_code": pub_result.error_code,
                    "error_message": pub_result.error_message,
                })

        return results

    def start(self, poll_interval_seconds: float = 15.0) -> None:
        """Bắt đầu chạy luồng scheduler ngầm."""
        if getattr(self, "_is_running", False):
            return
        self._is_running = True
        self._is_paused = False
        self._poll_interval = poll_interval_seconds

        def _worker_loop():
            import time
            while getattr(self, "_is_running", False):
                if not getattr(self, "_is_paused", False):
                    try:
                        self.poll_and_process_jobs()
                    except Exception as e:
                        logger.error(f"Lỗi trong vòng lặp scheduler: {e}")
                time.sleep(self._poll_interval)

        import threading
        self._thread = threading.Thread(target=_worker_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Dừng scheduler ngầm."""
        self._is_running = False

    def pause_queue(self) -> None:
        """Tạm dừng quét hàng đợi."""
        self._is_paused = True

    def resume_queue(self) -> None:
        """Tiếp tục quét hàng đợi."""
        self._is_paused = False
