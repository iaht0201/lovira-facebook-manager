"""Licensing package."""

from .models import (
    SessionState,
    LicenseErrorCode,
    LicenseSession,
    ActivationResult,
    HeartbeatResult,
)
from .fingerprint import get_or_create_device_id, get_device_fingerprint
from .client import LicenseClient, LicenseBackendProtocol
from .policy import RemoteAppConfig, ContactInfo, AccessPolicyManager

__all__ = [
    "SessionState",
    "LicenseErrorCode",
    "LicenseSession",
    "ActivationResult",
    "HeartbeatResult",
    "get_or_create_device_id",
    "get_device_fingerprint",
    "LicenseClient",
    "LicenseBackendProtocol",
    "RemoteAppConfig",
    "ContactInfo",
    "AccessPolicyManager",
]
