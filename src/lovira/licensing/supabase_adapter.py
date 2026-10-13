"""
Lovira-Facebook Manager
Supabase REST & RPC Backend Adapter (SupabaseAdapter)
Kết nối an toàn tới Supabase sử dụng Anon Publishable Key và các RPC nguyên tử (Section 14).
"""

import hashlib
import json
import logging
from typing import Tuple, Optional
import requests
from .models import (
    SessionState,
    LicenseErrorCode,
    LicenseSession,
    ActivationResult,
    HeartbeatResult,
)
from .client import LicenseBackendProtocol

logger = logging.getLogger(__name__)


class SupabaseAdapter(LicenseBackendProtocol):
    """Hiện thực LicenseBackendProtocol kết nối tới Supabase qua REST/RPC."""

    def __init__(self, supabase_url: str, anon_key: str, timeout: float = 10.0):
        self.supabase_url = supabase_url.rstrip("/")
        self.anon_key = anon_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
        })

    def _hash_key(self, raw_key: str) -> str:
        """Băm License Key bằng SHA-256 trước khi gửi qua mạng."""
        return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

    def activate(
        self,
        key: str,
        device_id: str,
        fingerprint: str,
        app_version: str,
        force_transfer: bool,
    ) -> ActivationResult:
        """Gọi hàm activate_license_rpc trên Supabase."""
        url = f"{self.supabase_url}/rest/v1/rpc/activate_license_rpc"
        payload = {
            "p_key_digest": self._hash_key(key),
            "p_install_id": device_id,
            "p_fingerprint": fingerprint,
            "p_os_name": "Windows/Linux",
            "p_app_version": app_version,
            "p_force_transfer": force_transfer,
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                logger.error(f"Lỗi phản hồi Supabase activate: {resp.status_code} - {resp.text}")
                return ActivationResult(
                    success=False,
                    error_code=LicenseErrorCode.NETWORK_ERROR,
                    error_message=f"Lỗi kết nối máy chủ ({resp.status_code}).",
                )

            data = resp.json()
            if not data.get("success"):
                err_code_str = data.get("error_code", "KEY_NOT_FOUND")
                try:
                    err_code = LicenseErrorCode(err_code_str)
                except ValueError:
                    err_code = LicenseErrorCode.KEY_NOT_FOUND

                return ActivationResult(
                    success=False,
                    error_code=err_code,
                    error_message=data.get("message", "Kích hoạt thất bại."),
                    requires_transfer_confirmation=data.get("requires_transfer_confirmation", False),
                )

            session = LicenseSession(
                session_id=str(data["session_id"]),
                generation=int(data["generation"]),
                session_token=str(data["session_token"]),
                license_key_hint=str(data.get("license_key_hint", key[-4:])),
                state=SessionState.ACTIVE,
                expires_at_utc=data.get("expires_at", ""),
                config_version=int(data.get("config_version", 1)),
            )
            return ActivationResult(success=True, session=session)

        except requests.RequestException as e:
            logger.error(f"Lỗi mạng khi kết nối Supabase: {e}")
            return ActivationResult(
                success=False,
                error_code=LicenseErrorCode.NETWORK_ERROR,
                error_message="Không thể kết nối tới máy chủ kích hoạt. Vui lòng kiểm tra mạng.",
            )

    def heartbeat(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        device_id: str,
    ) -> HeartbeatResult:
        """Gọi hàm heartbeat_session_rpc trên Supabase."""
        url = f"{self.supabase_url}/rest/v1/rpc/heartbeat_session_rpc"
        payload = {
            "p_session_id": session_id,
            "p_generation": generation,
            "p_token_digest": hashlib.sha256(session_token.encode("utf-8")).hexdigest(),
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                return HeartbeatResult(
                    success=False,
                    error_code=LicenseErrorCode.NETWORK_ERROR,
                    error_message="Không thể kết nối máy chủ heartbeat.",
                )

            data = resp.json()
            if not data.get("success"):
                return HeartbeatResult(
                    success=False,
                    is_revoked=data.get("is_revoked", False),
                    is_expired=data.get("is_expired", False),
                    generation=generation,
                    error_code=LicenseErrorCode.SESSION_REVOKED if data.get("is_revoked") else LicenseErrorCode.SESSION_EXPIRED,
                    error_message=data.get("message", "Phiên không còn hiệu lực."),
                )

            return HeartbeatResult(
                success=True,
                generation=int(data.get("generation", generation)),
                new_expires_at_utc=data.get("new_expires_at", ""),
            )

        except requests.RequestException as e:
            return HeartbeatResult(
                success=False,
                error_code=LicenseErrorCode.NETWORK_ERROR,
                error_message=f"Lỗi mạng heartbeat: {e}",
            )

    def authorize(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        action: str,
    ) -> Tuple[bool, str]:
        """Xác thực quyền online trước các tác vụ nhạy cảm."""
        hb = self.heartbeat(session_id, generation, session_token, "")
        if hb.success:
            return True, "Cấp quyền thành công."
        if hb.is_revoked:
            return False, "Phiên đã bị thu hồi bởi thiết bị khác."
        if hb.is_expired:
            return False, "Bản quyền đã hết hạn."
        return False, hb.error_message or "Không thể xác thực quyền."

    def logout(self, session_id: str, session_token: str) -> bool:
        """Đăng xuất phiên."""
        return True
