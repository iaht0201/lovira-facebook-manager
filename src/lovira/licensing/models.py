"""
Lovira-Facebook Manager
Domain Models & Trạng thái cho Hệ thống License & Phiên
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional


class SessionState(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    ACTIVATING = "activating"
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    OFFLINE_LIMITED = "offline_limited"


class LicenseErrorCode(str, Enum):
    KEY_NOT_FOUND = "KEY_NOT_FOUND"
    KEY_EXPIRED = "KEY_EXPIRED"
    KEY_BLOCKED = "KEY_BLOCKED"
    MAX_SESSIONS_EXCEEDED = "MAX_SESSIONS_EXCEEDED"
    SESSION_REVOKED = "SESSION_REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    DEVICE_TRANSFER_REQUIRED = "DEVICE_TRANSFER_REQUIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    VERSION_OUTDATED = "VERSION_OUTDATED"


@dataclass
class LicenseSession:
    session_id: str
    generation: int
    session_token: str
    license_key_hint: str
    state: SessionState = SessionState.ACTIVE
    expires_at_utc: str = ""
    is_free_mode: bool = False
    config_version: int = 1
    features: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivationResult:
    success: bool
    session: Optional[LicenseSession] = None
    error_code: Optional[LicenseErrorCode] = None
    error_message: str = ""
    requires_transfer_confirmation: bool = False


@dataclass
class HeartbeatResult:
    success: bool
    is_revoked: bool = False
    is_expired: bool = False
    generation: int = 0
    new_expires_at_utc: str = ""
    error_code: Optional[LicenseErrorCode] = None
    error_message: str = ""
