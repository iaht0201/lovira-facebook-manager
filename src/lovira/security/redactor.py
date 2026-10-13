"""
Lovira-Facebook Manager
Bộ lọc che giấu thông tin nhạy cảm (Log & Data Redactor)
Đảm bảo token Facebook, JWT, license key, cookie không bao giờ xuất hiện trong log hoặc export (AC-32).
"""

import logging
import re
from typing import Any, Dict


class LogRedactor:
    """Xóa bỏ hoặc che các mẫu thông tin xác thực nhạy cảm."""

    PATTERNS = [
        # Facebook Graph API tokens (bắt đầu bằng EAA...)
        (re.compile(r"EAA[a-zA-Z0-9]{15,}", re.IGNORECASE), "EAA[REDACTED_FB_TOKEN]"),
        # JWT Token pattern
        (re.compile(r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"), "eyJ[REDACTED_JWT]"),
        # Bearer Authorization headers
        (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\.\-]+", re.IGNORECASE), r"\1[REDACTED]"),
        # License key format (VD: LOVI-XXXX-YYYY-ZZZZ)
        (re.compile(r"\b[A-Za-z0-9]{4,8}-[A-Za-z0-9]{4,8}-[A-Za-z0-9]{4,8}-[A-Za-z0-9]{4,8}\b"), "[REDACTED_KEY]"),
        # Cookie string headers (c_user=..., xs=...)
        (re.compile(r"(xs=[^;\s]+|c_user=[^;\s]+|datr=[^;\s]+)", re.IGNORECASE), "[REDACTED_COOKIE]"),
    ]

    SENSITIVE_KEYS = {
        "access_token",
        "page_access_token",
        "user_access_token",
        "session_token",
        "secret",
        "app_secret",
        "password",
        "license_key",
        "api_key",
        "authorization",
        "cookie",
    }

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Thay thế các chuỗi bí mật trong văn bản bằng chuỗi che giấu."""
        if not text or not isinstance(text, str):
            return text

        result = text
        for pattern, replacement in cls.PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo bản sao dict đã che giấu các trường nhạy cảm."""
        if not isinstance(data, dict):
            return data

        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            k_lower = k.lower()
            if any(sensitive in k_lower for sensitive in cls.SENSITIVE_KEYS):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, dict):
                cleaned[k] = cls.redact_dict(v)
            elif isinstance(v, list):
                cleaned[k] = [cls.redact_dict(item) if isinstance(item, dict) else (cls.redact_text(str(item)) if isinstance(item, str) else item) for item in v]
            elif isinstance(v, str):
                cleaned[k] = cls.redact_text(v)
            else:
                cleaned[k] = v
        return cleaned


class RedactingLogFilter(logging.Filter):
    """Logging Filter tự động che thông tin nhạy cảm trong mọi log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = LogRedactor.redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = LogRedactor.redact_dict(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    LogRedactor.redact_text(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
