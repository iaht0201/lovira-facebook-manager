"""
Lovira-Facebook Manager
Cấu hình mặc định ứng dụng
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class AppSettings:
    app_name: str = "Lovira-Facebook Manager"
    app_version: str = "0.1.0"
    business_timezone: str = "Asia/Ho_Chi_Minh"
    default_heartbeat_interval: int = 60
    default_session_ttl: int = 180
    max_concurrent_downloads: int = 2
    max_concurrent_uploads: int = 1
    max_concurrent_transcodes: int = 1
    extra: Dict[str, Any] = field(default_factory=dict)
