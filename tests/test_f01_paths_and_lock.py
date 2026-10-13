import tempfile
from pathlib import Path
import pytest

from src.lovira.config.paths import AppPaths
from src.lovira.app_lock import SingleInstanceLock


def test_app_paths_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = AppPaths(base_dir=Path(tmpdir), profile="test_profile")
        assert not paths.root.exists()
        paths.ensure_directories()
        assert paths.root.exists()
        assert paths.media_dir.exists()
        assert paths.downloads_dir.exists()
        assert paths.thumbnails_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.backups_dir.exists()


def test_single_instance_lock_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_file = Path(tmpdir) / "app.lock"

        # Instance 1 acquires
        lock1 = SingleInstanceLock(lock_file)
        assert lock1.acquire() is True
        assert lock1.is_locked is True

        # Instance 2 tries to acquire same lock -> must fail (AC-16)
        lock2 = SingleInstanceLock(lock_file)
        assert lock2.acquire() is False
        assert lock2.is_locked is False

        # Instance 1 releases
        lock1.release()
        assert lock1.is_locked is False

        # Instance 2 can now acquire
        assert lock2.acquire() is True
        assert lock2.is_locked is True
        lock2.release()


def test_single_instance_lock_context_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_file = Path(tmpdir) / "app.lock"

        with SingleInstanceLock(lock_file) as lock1:
            assert lock1.is_locked is True
            # Attempting to acquire again raises RuntimeError
            with pytest.raises(RuntimeError):
                with SingleInstanceLock(lock_file):
                    pass

        # Outside context, lock is released and can be acquired again
        with SingleInstanceLock(lock_file) as lock3:
            assert lock3.is_locked is True
