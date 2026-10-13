"""
Lovira-Facebook Manager
License & Session Client (LicenseClient)
Quản lý vòng đời phiên người dùng và tương tác với dịch vụ backend (AC-23, AC-24, AC-37, AC-38, AC-39).
"""

import logging
from typing import Optional, Protocol, Tuple, Dict, Any
from .models import (
    SessionState,
    LicenseErrorCode,
    LicenseSession,
    ActivationResult,
    HeartbeatResult,
)

logger = logging.getLogger(__name__)


class LicenseBackendProtocol(Protocol):
    """Giao thức kết nối tới Backend Supabase / License Server."""

    def activate(
        self,
        key: str,
        device_id: str,
        fingerprint: str,
        app_version: str,
        force_transfer: bool,
    ) -> ActivationResult:
        ...

    def heartbeat(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        device_id: str,
    ) -> HeartbeatResult:
        ...

    def authorize(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        action: str,
    ) -> Tuple[bool, str]:
        ...

    def logout(self, session_id: str, session_token: str) -> bool:
        ...


class OfflineFallbackLicenseBackend:
    """
    Backend dự phòng an toàn khi chưa cấu hình máy chủ Supabase thực tế.
    Trả về kết quả rõ ràng (fail-closed) thay vì dùng MagicMock trong production.
    """

    def __init__(self, message: str = "Chưa cấu hình máy chủ bản quyền Supabase. Ứng dụng đang chạy ở chế độ Offline/Cục bộ."):
        self.message = message

    def activate(
        self,
        key: str,
        device_id: str,
        fingerprint: str,
        app_version: str,
        force_transfer: bool,
    ) -> ActivationResult:
        return ActivationResult(
            success=False,
            error_code=LicenseErrorCode.NETWORK_ERROR,
            error_message=self.message,
        )

    def heartbeat(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        device_id: str,
    ) -> HeartbeatResult:
        return HeartbeatResult(
            success=False,
            is_revoked=False,
            is_expired=True,
            error_message=self.message,
        )

    def authorize(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        action: str,
    ) -> Tuple[bool, str]:
        return False, self.message

    def logout(self, session_id: str, session_token: str) -> bool:
        return True


class LicenseClient:
    """Quản lý trạng thái phiên bản quyền và bảo vệ quyền thực thi."""

    def __init__(
        self,
        backend: LicenseBackendProtocol,
        device_id: str,
        fingerprint: str,
        app_version: str = "0.1.0",
    ):
        self.backend = backend
        self.device_id = device_id
        self.fingerprint = fingerprint
        self.app_version = app_version
        self.current_session: Optional[LicenseSession] = None

    @property
    def is_active(self) -> bool:
        """Kiểm tra phiên hiện tại có đang hợp lệ và hoạt động không."""
        return (
            self.current_session is not None
            and self.current_session.state == SessionState.ACTIVE
        )

    def activate_key(self, key: str, force_transfer: bool = False) -> ActivationResult:
        """Kích hoạt License Key."""
        clean_key = key.strip()
        result = self.backend.activate(
            key=clean_key,
            device_id=self.device_id,
            fingerprint=self.fingerprint,
            app_version=self.app_version,
            force_transfer=force_transfer,
        )

        if result.success and result.session:
            self.current_session = result.session
            logger.info(
                f"Kích hoạt thành công phiên {self.current_session.session_id} (thế hệ {self.current_session.generation})."
            )
        return result

    def send_heartbeat(self) -> HeartbeatResult:
        """Gửi heartbeat định kỳ để gia hạn lease và kiểm tra thu hồi phiên."""
        if not self.current_session:
            return HeartbeatResult(
                success=False,
                is_revoked=True,
                error_code=LicenseErrorCode.SESSION_REVOKED,
                error_message="Không có phiên nào đang hoạt động.",
            )

        sent_session_id = self.current_session.session_id
        sent_generation = self.current_session.generation

        # Nếu phiên đã bị thu hồi hoặc hết hạn, không tự động hồi sinh
        if self.current_session.state in (SessionState.REVOKED, SessionState.EXPIRED, SessionState.UNAUTHENTICATED):
            return HeartbeatResult(
                success=False,
                is_revoked=True,
                generation=sent_generation,
                error_code=LicenseErrorCode.SESSION_REVOKED,
                error_message="Phiên đã bị thu hồi hoặc đã kết thúc.",
            )

        result = self.backend.heartbeat(
            session_id=sent_session_id,
            generation=sent_generation,
            session_token=self.current_session.session_token,
            device_id=self.device_id,
        )

        # Kiểm tra chống race condition: nếu phiên đã thay đổi trong lúc chờ mạng, bỏ qua phản hồi cũ (AC-38)
        if (
            not self.current_session
            or self.current_session.session_id != sent_session_id
            or self.current_session.generation != sent_generation
        ):
            logger.warning("Bỏ qua phản hồi heartbeat trễ từ một thế hệ phiên cũ.")
            return result

        if result.is_revoked:
            self.current_session.state = SessionState.REVOKED
            logger.warning(f"Phiên {sent_session_id} đã bị máy khác thay thế hoặc bị thu hồi trên server (AC-24).")
        elif result.is_expired:
            self.current_session.state = SessionState.EXPIRED
            logger.warning(f"Phiên {sent_session_id} đã hết hạn.")
        elif result.success:
            self.current_session.expires_at_utc = result.new_expires_at_utc

        return result

    def authorize_action(self, action: str) -> Tuple[bool, str]:
        """
        Kiểm tra quyền trực tiếp trước các hành động gây thay đổi (Publish, Upload, etc.).
        Tuân thủ ma trận quyền offline (AC-26, AC-28).
        """
        if not self.is_active or not self.current_session:
            return False, "Không có phiên license hợp lệ. Vui lòng kích hoạt bản quyền."

        # Kiểm tra online qua backend trước thao tác nhạy cảm
        return self.backend.authorize(
            session_id=self.current_session.session_id,
            generation=self.current_session.generation,
            session_token=self.current_session.session_token,
            action=action,
        )

    def logout(self) -> bool:
        """Đăng xuất và thu hồi phiên trên server."""
        if not self.current_session:
            return True

        session_id = self.current_session.session_id
        session_token = self.current_session.session_token

        # Đánh dấu trạng thái client trước
        self.current_session.state = SessionState.UNAUTHENTICATED
        self.current_session = None

        try:
            return self.backend.logout(session_id, session_token)
        except Exception:
            return True
