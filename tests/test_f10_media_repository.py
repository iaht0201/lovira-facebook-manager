import json
import tempfile
from pathlib import Path

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository


def test_media_repository_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        repo = MediaRepository(db)

        # 1. Thêm media
        asset_id = repo.add_media_asset(
            local_path=Path(tmpdir) / "video1.mp4",
            checksum="abc123sha256",
            size_bytes=1048576,
            duration=30.5,
            source_platform="douyin",
            source_url="https://douyin.com/video/1",
            tags="cooking, food",
        )
        assert asset_id.startswith("med_")

        # 2. Đọc lại
        asset = repo.get_media_asset(asset_id)
        assert asset is not None
        assert asset["checksum"] == "abc123sha256"
        assert asset["source_platform"] == "douyin"

        # 3. List & Search
        results = repo.list_media_assets(platform="douyin", search_term="cooking")
        assert len(results) == 1
        assert results[0]["id"] == asset_id


def test_media_references_and_delete_protection():
    # AC-12: Xóa media được lịch chờ tham chiếu -> Chỉ rõ công việc bị ảnh hưởng và yêu cầu lựa chọn
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        repo = MediaRepository(db)

        # Tạo Page mẫu
        with db.transaction() as conn:
            conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p-1', '101', 'Page Test');")

        # Tạo media
        asset_id = repo.add_media_asset(
            local_path=Path(tmpdir) / "sample.mp4",
            checksum="hash123",
            size_bytes=2048,
            duration=15.0,
        )

        # Tạo 1 lịch đăng tham chiếu media này
        snapshot = json.dumps({"media_ids": [asset_id], "caption": "Hello world"})
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO publish_jobs (
                    id, batch_id, client_request_id, page_id, content_snapshot,
                    state, scheduled_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("job-1", "b-1", "req-1", "p-1", snapshot, "scheduled_local", "2026-10-20T13:30:00Z"),
            )

        # Kiểm tra tham chiếu
        refs = repo.check_media_references(asset_id)
        assert refs["active_job_count"] == 1
        assert refs["active_jobs"][0]["job_id"] == "job-1"

        # Xóa không force -> BỊ TỪ CHỐI (AC-12)
        success, msg = repo.delete_media_asset(asset_id, force=False)
        assert success is False
        assert "1 lịch đăng đang chờ" in msg

        # Xóa với force=True -> THÀNH CÔNG
        success_force, _ = repo.delete_media_asset(asset_id, force=True)
        assert success_force is True
        assert repo.get_media_asset(asset_id) is None
