import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault
from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
from src.lovira.integrations.facebook.publisher import GraphPublishAdapter, PublishResult
from src.lovira.licensing.policy import AccessPolicyManager, RemoteAppConfig
from src.lovira.licensing.models import LicenseSession, SessionState
from src.lovira.workers.scheduler import LocalSchedulerService


def setup_scheduler_env(tmpdir: Path):
    db_path = tmpdir / "test.db"
    vault_dir = tmpdir / "vault"
    db = DatabaseManager(db_path)
    MigrationRunner(db).apply_all()
    vault = SecretVault(fallback_vault_dir=vault_dir)

    queue = PublishQueueRepository(db)
    page_repo = PageRepository(db, vault)
    media_repo = MediaRepository(db)
    publisher = GraphPublishAdapter()
    policy = AccessPolicyManager(RemoteAppConfig(license_required=True, expires_at_utc="2026-12-31T23:59:59Z"))

    scheduler = LocalSchedulerService(
        db_manager=db,
        queue_repo=queue,
        page_repo=page_repo,
        media_repo=media_repo,
        publisher=publisher,
        policy_manager=policy,
    )
    return db, queue, page_repo, scheduler


def test_scheduler_due_and_published():
    with tempfile.TemporaryDirectory() as tmpdir:
        db, queue, page_repo, scheduler = setup_scheduler_env(Path(tmpdir))

        # 1. Tạo Page & Token
        page_id = page_repo.upsert_page("1001", "Page Scheduler Test")
        page_repo.save_page_token(page_id, "EAABvalid_token_123")

        # 2. Tạo Job đến giờ đăng (1 phút trước)
        due_utc = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = ContentSnapshot(
            batch_id="b-due",
            page_id=page_id,
            content_type=ContentType.TEXT,
            final_caption="Hello from Scheduler!",
            scheduled_at_utc=due_utc,
            schedule_mode=ScheduleMode.LOCAL,
        )
        job_ids = queue.enqueue_batch("req-due-1", [snapshot])
        assert len(job_ids) == 1
        job_id = job_ids[0]

        # 3. Phiên license hợp lệ
        valid_session = LicenseSession(
            session_id="sess_ok",
            generation=1,
            session_token="tok_ok",
            license_key_hint="1234",
            state=SessionState.ACTIVE,
        )

        # Mock publisher thành công
        with patch.object(scheduler.publisher, "publish", return_value=PublishResult(success=True, post_id="fb_post_999")) as mock_pub:
            results = scheduler.poll_and_process_jobs(session=valid_session, is_online=True)

            assert len(results) == 1
            assert results[0]["state"] == "published"
            assert results[0]["post_id"] == "fb_post_999"

            # Kiểm tra facebook_page_id thật ("1001") được truyền vào publisher
            assert mock_pub.call_args.kwargs.get("facebook_page_id") == "1001"

            job = queue.get_job(job_id)
            assert job["state"] == "published"
            assert job["remote_scheduled_id"] == "fb_post_999"


def test_scheduler_machine_sleep_missed_schedule():
    # AC-17: Máy ngủ qua giờ đăng -> Đánh dấu lỡ lịch theo chính sách, không tự đăng dồn
    with tempfile.TemporaryDirectory() as tmpdir:
        db, queue, page_repo, scheduler = setup_scheduler_env(Path(tmpdir))

        page_id = page_repo.upsert_page("1002", "Page Sleep Test")
        page_repo.save_page_token(page_id, "EAABtoken")

        # Job bị trôi 3 giờ trước (> max_drift_seconds 900s) do máy tắt
        missed_utc = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = ContentSnapshot(
            batch_id="b-missed",
            page_id=page_id,
            content_type=ContentType.TEXT,
            final_caption="Caption Missed",
            scheduled_at_utc=missed_utc,
        )
        job_ids = queue.enqueue_batch("req-missed", [snapshot])
        job_id = job_ids[0]

        # Quét hàng đợi -> Phải đánh dấu 'missed' (AC-17)
        results = scheduler.poll_and_process_jobs(max_drift_seconds=900)
        assert len(results) == 1
        assert results[0]["state"] == "missed"

        job = queue.get_job(job_id)
        assert job["state"] == "missed"
        assert "Máy tắt hoặc ngủ qua giờ hẹn" in job["blocked_reason"]


def test_scheduler_license_expired_pauses_job():
    # AC-28, AC-44: Hết hạn license -> Tạm dừng tác vụ, không xuất bản
    with tempfile.TemporaryDirectory() as tmpdir:
        db, queue, page_repo, scheduler = setup_scheduler_env(Path(tmpdir))

        page_id = page_repo.upsert_page("1003", "Page Pause Test")
        page_repo.save_page_token(page_id, "EAABtoken")

        due_utc = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = ContentSnapshot(
            batch_id="b-pause",
            page_id=page_id,
            content_type=ContentType.TEXT,
            final_caption="Will pause",
            scheduled_at_utc=due_utc,
        )
        job_ids = queue.enqueue_batch("req-pause", [snapshot])
        job_id = job_ids[0]

        # Chạy mà KHÔNG có session active
        results = scheduler.poll_and_process_jobs(session=None, is_online=True)
        assert len(results) == 1
        assert results[0]["state"] == "paused"

        job = queue.get_job(job_id)
        assert job["state"] == "paused"
        assert "License" in job["blocked_reason"]
