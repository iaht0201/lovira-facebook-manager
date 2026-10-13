"""Configuration package."""

from .paths import AppPaths, get_app_data_dir
from .settings import AppSettings

__all__ = ["AppPaths", "get_app_data_dir", "AppSettings"]
