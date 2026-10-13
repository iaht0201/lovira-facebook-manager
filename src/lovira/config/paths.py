"""
Lovira-Facebook Manager
Quản lý đường dẫn dữ liệu hệ thống (Paths & Directories)
Tuân thủ chuẩn lưu trữ:
- Windows: %LOCALAPPDATA%/Lovira
- Linux: ~/.local/share/lovira (hoặc $XDG_DATA_HOME/lovira)
"""

import os
import sys
from pathlib import Path


def get_app_data_dir(app_name: str = "Lovira") -> Path:
    """Trả về thư mục dữ liệu người dùng cô lập cho ứng dụng."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data)
        else:
            base_dir = Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            base_dir = Path(xdg_data)
        else:
            base_dir = Path.home() / ".local" / "share"

    app_dir = base_dir / app_name
    return app_dir


class AppPaths:
    """Quản lý tập trung các thư mục và file dữ liệu của Lovira."""

    def __init__(self, base_dir: Path | None = None, profile: str = "default"):
        self.profile = profile
        if base_dir is None:
            self.root = get_app_data_dir() / "profiles" / profile
        else:
            self.root = Path(base_dir) / "profiles" / profile

        self.database_file = self.root / "lovira.db"
        self.config_dir = self.root / "config"
        self.vault_dir = self.root / "vault"
        self.media_dir = self.root / "media"
        self.downloads_dir = self.root / "downloads"
        self.thumbnails_dir = self.root / "thumbnails"
        self.logs_dir = self.root / "logs"
        self.backups_dir = self.root / "backups"
        self.lock_file = self.root / "lovira.lock"

    @property
    def db_path(self) -> Path:
        return self.database_file

    def ensure_directories(self) -> None:
        """Tạo đầy đủ các thư mục nếu chưa tồn tại."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
