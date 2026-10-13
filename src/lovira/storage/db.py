"""
Lovira-Facebook Manager
Quản lý cơ sở dữ liệu SQLite cục bộ (DatabaseManager)
- Bật WAL (Write-Ahead Logging)
- Bật Foreign Keys
- Busy Timeout xử lý tranh chấp worker
- Đảm bảo đóng kết nối chuẩn xác trên Windows (tránh khóa file)
- SQLite Online Backup API phục vụ sao lưu nhất quán (AC-13, AC-22)
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


class DatabaseManager:
    """Quản trị kết nối và giao dịch SQLite cho ứng dụng Lovira."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Tạo kết nối SQLite mới với các thiết lập tối ưu. Người gọi chịu trách nhiệm đóng kết nối."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        # Thiết lập PRAGMAs bắt buộc theo đặc tả kỹ thuật
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def connection_scope(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager mở kết nối và luôn đóng kết nối khi hoàn tất."""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, conn: Optional[sqlite3.Connection] = None) -> Generator[sqlite3.Connection, None, None]:
        """Context manager quản lý giao dịch nguyên tử (commit khi thành công, rollback khi lỗi)."""
        owns_conn = False
        if conn is None:
            conn = self.get_connection()
            owns_conn = True

        try:
            with conn:
                yield conn
        finally:
            if owns_conn:
                conn.close()

    def backup_to(self, target_path: Path, pages: int = -1) -> None:
        """Sao lưu trực tuyến SQLite nhất quán, an toàn với WAL mode (AC-22)."""
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with self.connection_scope() as source_conn:
            target_conn = sqlite3.connect(str(target_path))
            try:
                # Thực hiện SQLite Online Backup
                source_conn.backup(target_conn, pages=pages)
            finally:
                target_conn.close()
