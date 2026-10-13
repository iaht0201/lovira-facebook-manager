"""
Lovira-Facebook Manager
Quản lý khóa đơn tiến trình (Single Instance Lock)
Đảm bảo chỉ có một instance sở hữu hàng đợi và SQLite profile cùng một thời điểm (AC-16).
"""

import os
import sys
from pathlib import Path
from typing import Optional


class SingleInstanceLock:
    """Khóa tiến trình độc quyền cho một profile."""

    def __init__(self, lock_file_path: Path):
        self.lock_file_path = Path(lock_file_path)
        self._file_handle: Optional[int] = None
        self._is_locked = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def acquire(self) -> bool:
        """Thử chiếm quyền khóa độc quyền. Trả về True nếu thành công, False nếu đã có instance khác chạy."""
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                import msvcrt
                # Mở hoặc tạo file lock
                flags = os.O_RDWR | os.O_CREAT
                self._file_handle = os.open(str(self.lock_file_path), flags)
                # Thử khóa 1 byte đầu tiên ở chế độ không chặn (LK_NBLCK)
                msvcrt.locking(self._file_handle, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                flags = os.O_RDWR | os.O_CREAT
                self._file_handle = os.open(str(self.lock_file_path), flags)
                fcntl.flock(self._file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Ghi PID hiện tại vào file để dễ chẩn đoán
            os.ftruncate(self._file_handle, 0)
            os.write(self._file_handle, f"{os.getpid()}\n".encode("utf-8"))
            self._is_locked = True
            return True
        except (OSError, IOError, BlockingIOError):
            if self._file_handle is not None:
                try:
                    os.close(self._file_handle)
                except OSError:
                    pass
                self._file_handle = None
            self._is_locked = False
            return False

    def release(self) -> None:
        """Giải phóng khóa khi thoát ứng dụng."""
        if not self._is_locked or self._file_handle is None:
            return

        try:
            if sys.platform == "win32":
                import msvcrt
                try:
                    os.lseek(self._file_handle, 0, os.SEEK_SET)
                    msvcrt.locking(self._file_handle, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(self._file_handle, fcntl.LOCK_UN)
                except OSError:
                    pass

            os.close(self._file_handle)
        except OSError:
            pass
        finally:
            self._file_handle = None
            self._is_locked = False
            try:
                if self.lock_file_path.exists():
                    self.lock_file_path.unlink()
            except OSError:
                pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Hồ sơ '{self.lock_file_path.parent.name}' đang được một phiên Lovira khác sử dụng.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
