"""
Lovira-Facebook Manager
Quản lý Nâng cấp Schema SQLite (Schema Migration Runner)
Đảm bảo kiểm soát phiên bản cấu trúc dữ liệu nguyên tử.
"""

import logging
from pathlib import Path
from typing import List, Tuple
from .db import DatabaseManager

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Thực thi các script migration theo thứ tự phiên bản."""

    def __init__(self, db_manager: DatabaseManager, migrations_dir: Path | None = None):
        self.db_manager = db_manager
        if migrations_dir is None:
            # Mặc định lấy từ thư mục migrations/local của project
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.migrations_dir = project_root / "migrations" / "local"
        else:
            self.migrations_dir = Path(migrations_dir)

    def init_migration_table(self) -> None:
        """Tạo bảng lưu vết migration nếu chưa có."""
        with self.db_manager.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
                );
            """)

    def get_applied_versions(self) -> List[int]:
        """Lấy danh sách các phiên bản đã được áp dụng."""
        self.init_migration_table()
        with self.db_manager.connection_scope() as conn:
            cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
            return [row["version"] for row in cursor.fetchall()]

    def discover_migrations(self) -> List[Tuple[int, str, Path]]:
        """Quét và sắp xếp các file .sql trong thư mục migrations."""
        if not self.migrations_dir.exists():
            return []

        migrations: List[Tuple[int, str, Path]] = []
        for file in sorted(self.migrations_dir.glob("*.sql")):
            parts = file.stem.split("_", 1)
            if parts and parts[0].isdigit():
                version = int(parts[0])
                name = parts[1] if len(parts) > 1 else file.stem
                migrations.append((version, name, file))
        return sorted(migrations, key=lambda x: x[0])

    def apply_all(self) -> int:
        """Áp dụng tất cả các migration còn thiếu. Trả về số lượng migration đã chạy."""
        self.init_migration_table()
        applied = set(self.get_applied_versions())
        available = self.discover_migrations()

        count = 0
        for version, name, file_path in available:
            if version not in applied:
                logger.info(f"Đang áp dụng migration {version:03d}_{name}...")
                sql_content = file_path.read_text(encoding="utf-8")
                with self.db_manager.transaction() as conn:
                    conn.executescript(sql_content)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                        (version, name),
                    )
                count += 1
                logger.info(f"Đã hoàn thành migration {version:03d}_{name}.")
        return count
