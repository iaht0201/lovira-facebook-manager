import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner


def test_migrations_and_schema_initialization():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "lovira_test.db"
        db_manager = DatabaseManager(db_path)

        runner = MigrationRunner(db_manager)
        applied_count = runner.apply_all()
        assert applied_count >= 1

        # Check idempotency
        assert runner.apply_all() == 0

        # Verify tables exist
        with db_manager.connection_scope() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in cursor.fetchall()}

            expected_tables = {
                "schema_migrations",
                "facebook_accounts",
                "page_groups",
                "pages",
                "account_page_links",
                "secret_refs",
                "media_assets",
                "download_jobs",
                "drafts",
                "draft_targets",
                "publish_jobs",
                "publish_attempts",
                "job_events",
                "posts_cache",
                "comments_cache",
                "reply_templates",
                "app_settings",
                "license_state",
            }
            assert expected_tables.issubset(tables)


def test_sqlite_pragmas_and_foreign_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "lovira_test.db"
        db_manager = DatabaseManager(db_path)
        runner = MigrationRunner(db_manager)
        runner.apply_all()

        with db_manager.connection_scope() as conn:
            # Check journal mode is WAL
            cursor = conn.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode.lower() == "wal"

            # Check foreign keys is ON
            cursor = conn.execute("PRAGMA foreign_keys;")
            fk_on = cursor.fetchone()[0]
            assert fk_on == 1

        # Test foreign key enforcement
        with pytest.raises(sqlite3.IntegrityError):
            with db_manager.transaction() as conn:
                # draft_targets requires valid draft_id and page_id
                conn.execute(
                    "INSERT INTO draft_targets (id, draft_id, page_id) VALUES (?, ?, ?);",
                    ("dt-1", "nonexistent-draft", "nonexistent-page"),
                )


def test_sqlite_online_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "lovira_primary.db"
        backup_path = Path(tmpdir) / "lovira_backup.db"

        db_manager = DatabaseManager(db_path)
        runner = MigrationRunner(db_manager)
        runner.apply_all()

        # Insert some test data
        with db_manager.transaction() as conn:
            conn.execute(
                "INSERT INTO page_groups (id, name, color) VALUES (?, ?, ?);",
                ("group-1", "Fashion Pages", "#10B981"),
            )

        # Perform online backup
        db_manager.backup_to(backup_path)

        # Verify backup contains the exact row
        backup_manager = DatabaseManager(backup_path)
        with backup_manager.connection_scope() as conn:
            cursor = conn.execute("SELECT name, color FROM page_groups WHERE id = 'group-1';")
            row = cursor.fetchone()
            assert row is not None
            assert row["name"] == "Fashion Pages"
            assert row["color"] == "#10B981"
