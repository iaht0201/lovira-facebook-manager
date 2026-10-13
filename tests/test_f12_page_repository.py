import tempfile
from pathlib import Path

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository


def test_page_crud_and_secret_vault_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        vault_dir = Path(tmpdir) / "vault"
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        vault = SecretVault(fallback_vault_dir=vault_dir)
        repo = PageRepository(db, vault)

        # 1. Tạo nhóm Page
        group_id = repo.create_page_group("Thời trang Nữ", "#EC4899")
        groups = repo.list_page_groups()
        assert len(groups) == 1
        assert groups[0]["name"] == "Thời trang Nữ"

        # 2. Thêm Page
        page_id = repo.upsert_page(
            facebook_page_id="1009988",
            name="Lovira Boutique",
            group_id=group_id,
            status="ready",
        )
        assert page_id.startswith("page_")

        # 3. Lưu token an toàn vào SecretVault
        token_ref = repo.save_page_token(
            page_id=page_id,
            raw_token="EAABvery_secret_token_value_123",
            tasks=["CREATE_CONTENT", "MANAGE"],
        )
        assert token_ref == f"fb_token_{page_id}"

        # Kiểm tra token trong DB chỉ là token_ref, KHÔNG phải token thô
        with db.connection_scope() as conn:
            cur = conn.execute("SELECT token_ref FROM account_page_links WHERE page_id = ?;", (page_id,))
            row = cur.fetchone()
            assert row["token_ref"] == token_ref
            assert "EAABvery_secret" not in row["token_ref"]

        # 4. Đọc token từ repo
        retrieved_token = repo.get_page_token(page_id)
        assert retrieved_token == "EAABvery_secret_token_value_123"

        # 5. List pages
        pages = repo.list_pages(group_id=group_id)
        assert len(pages) == 1
        assert pages[0]["name"] == "Lovira Boutique"
        assert pages[0]["group_name"] == "Thời trang Nữ"
        assert "CREATE_CONTENT" in pages[0]["granted_tasks"]


def test_unlink_page_with_schedules():
    # AC-11: Gỡ Page có lịch local và remote -> Hiển thị tác động; không mất ID đối chiếu trước khi xử lý xong
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        vault = SecretVault(fallback_vault_dir=Path(tmpdir))
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        repo = PageRepository(db, vault)

        page_id = repo.upsert_page("9999", "Page Co Lich")
        repo.save_page_token(page_id, "EAABtoken9999")

        # Tạo 1 lịch local và 1 lịch remote đã gửi lên FB
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
                VALUES ('job-local', 'b-1', 'req-1', ?, '{}', 'scheduled_local', '2026-10-20T13:30:00Z');
                """,
                (page_id,),
            )
            conn.execute(
                """
                INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, schedule_mode, remote_scheduled_id, scheduled_at_utc)
                VALUES ('job-remote', 'b-2', 'req-2', ?, '{}', 'scheduled_remote', 'remote', 'fb_post_id_777', '2026-10-20T15:30:00Z');
                """,
                (page_id,),
            )

        # Kiểm tra audit
        sched = repo.check_page_schedules(page_id)
        assert sched["local_count"] == 1
        assert sched["remote_count"] == 1
        assert sched["remote_jobs"][0]["remote_scheduled_id"] == "fb_post_id_777"

        # Gỡ không force -> BỊ TỪ CHỐI (AC-11)
        ok, msg = repo.unlink_page(page_id, force=False)
        assert ok is False
        assert "1 lịch trên máy và 1 lịch đã gửi Facebook" in msg

        # Gỡ với force=True -> THÀNH CÔNG
        ok_force, _ = repo.unlink_page(page_id, force=True)
        assert ok_force is True
        assert len(repo.list_pages()) == 0
        assert repo.get_page_token(page_id) is None
