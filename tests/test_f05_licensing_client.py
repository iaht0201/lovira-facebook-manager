import tempfile
from pathlib import Path
from typing import Dict, Tuple

from src.lovira.licensing.models import (
    SessionState,
    LicenseErrorCode,
    LicenseSession,
    ActivationResult,
    HeartbeatResult,
)
from src.lovira.licensing.fingerprint import get_or_create_device_id, get_device_fingerprint
from src.lovira.licensing.client import LicenseClient, LicenseBackendProtocol


class MockSupabaseLicenseServer(LicenseBackendProtocol):
    """Mô phỏng server Supabase với logic transaction nguyên tử phía server (Section 11 & 14)."""

    def __init__(self):
        # Database giả lập server
        self.licenses = {
            "LOVI-TEST-KEY-1111": {
                "status": "active",
                "expires_at_utc": "2026-12-31T23:59:59Z",
                "active_session": None, # (session_id, device_id, generation, token)
            }
        }
        self.session_generation_counter = 0

    def activate(
        self,
        key: str,
        device_id: str,
        fingerprint: str,
        app_version: str,
        force_transfer: bool,
    ) -> ActivationResult:
        lic = self.licenses.get(key)
        if not lic or lic["status"] != "active":
            return ActivationResult(success=False, error_code=LicenseErrorCode.KEY_NOT_FOUND, error_message="Key không tồn tại")

        current_active = lic["active_session"]
        if current_active is not None and current_active["device_id"] != device_id and not force_transfer:
            # Yêu cầu xác nhận chuyển máy (AC-37)
            return ActivationResult(
                success=False,
                error_code=LicenseErrorCode.DEVICE_TRANSFER_REQUIRED,
                error_message="Key đang được sử dụng trên máy khác.",
                requires_transfer_confirmation=True,
            )

        # Cấp phiên mới, tăng generation, thu hồi phiên cũ
        self.session_generation_counter += 1
        new_session_id = f"sess_{self.session_generation_counter}"
        generation = self.session_generation_counter
        session_token = f"tok_{new_session_id}"

        lic["active_session"] = {
            "session_id": new_session_id,
            "device_id": device_id,
            "generation": generation,
            "session_token": session_token,
            "revoked": False,
        }

        session = LicenseSession(
            session_id=new_session_id,
            generation=generation,
            session_token=session_token,
            license_key_hint=key[-4:],
            state=SessionState.ACTIVE,
            expires_at_utc=lic["expires_at_utc"],
        )
        return ActivationResult(success=True, session=session)

    def heartbeat(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        device_id: str,
    ) -> HeartbeatResult:
        for lic in self.licenses.values():
            active = lic.get("active_session")
            if active and active["session_id"] == session_id:
                # Kiểm tra generation và trạng thái thu hồi
                if active["generation"] != generation or active["revoked"]:
                    return HeartbeatResult(
                        success=False,
                        is_revoked=True,
                        generation=generation,
                        error_code=LicenseErrorCode.SESSION_REVOKED,
                        error_message="Phiên đã bị thu hồi bởi máy khác.",
                    )
                return HeartbeatResult(
                    success=True,
                    generation=generation,
                    new_expires_at_utc=lic["expires_at_utc"],
                )

        # Nếu không tìm thấy phiên trong active session
        return HeartbeatResult(
            success=False,
            is_revoked=True,
            generation=generation,
            error_code=LicenseErrorCode.SESSION_REVOKED,
            error_message="Phiên không tồn tại hoặc đã bị thu hồi.",
        )

    def authorize(
        self,
        session_id: str,
        generation: int,
        session_token: str,
        action: str,
    ) -> Tuple[bool, str]:
        for lic in self.licenses.values():
            active = lic.get("active_session")
            if active and active["session_id"] == session_id:
                if active["generation"] == generation and not active["revoked"]:
                    return True, "Cấp quyền thành công"
        return False, "Phiên không hợp lệ hoặc đã bị thu hồi."

    def logout(self, session_id: str, session_token: str) -> bool:
        for lic in self.licenses.values():
            active = lic.get("active_session")
            if active and active["session_id"] == session_id:
                active["revoked"] = True
                lic["active_session"] = None
                return True
        return False


def test_device_fingerprint():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir)
        dev_id1 = get_or_create_device_id(storage_path)
        assert dev_id1.startswith("dev_")

        # Gọi lần 2 trên cùng thư mục phải đọc lại ID cũ
        dev_id2 = get_or_create_device_id(storage_path)
        assert dev_id1 == dev_id2

        fp = get_device_fingerprint(dev_id1)
        assert len(fp) == 32


def test_device_transfer_and_revocation():
    server = MockSupabaseLicenseServer()
    key = "LOVI-TEST-KEY-1111"

    # Máy A kích hoạt key
    client_a = LicenseClient(server, device_id="device_A", fingerprint="fp_A")
    res_a = client_a.activate_key(key)
    assert res_a.success is True
    assert client_a.is_active is True
    assert client_a.current_session.generation == 1

    # Kiểm tra quyền Máy A
    allowed, _ = client_a.authorize_action("publish_post")
    assert allowed is True

    # Máy B thử kích hoạt cùng key mà không force transfer -> Yêu cầu xác nhận (AC-37)
    client_b = LicenseClient(server, device_id="device_B", fingerprint="fp_B")
    res_b_dry = client_b.activate_key(key, force_transfer=False)
    assert res_b_dry.success is False
    assert res_b_dry.requires_transfer_confirmation is True

    # Máy B xác nhận chuyển máy -> Cấp phiên mới, thế hệ tăng lên 2 (AC-23)
    res_b = client_b.activate_key(key, force_transfer=True)
    assert res_b.success is True
    assert client_b.is_active is True
    assert client_b.current_session.generation == 2

    # Máy A gửi heartbeat -> Nhận tin phiên bị thu hồi (AC-24)
    hb_a = client_a.send_heartbeat()
    assert hb_a.is_revoked is True
    assert client_a.is_active is False
    assert client_a.current_session.state == SessionState.REVOKED

    # Máy A bị chặn authorize (AC-31)
    allowed_a, msg_a = client_a.authorize_action("publish_post")
    assert allowed_a is False

    # Máy A gửi heartbeat lần nữa -> Không tự động cướp lại phiên của Máy B (AC-37)
    hb_a_again = client_a.send_heartbeat()
    assert hb_a_again.is_revoked is True
    assert client_b.is_active is True
    allowed_b, _ = client_b.authorize_action("publish_post")
    assert allowed_b is True


def test_delayed_heartbeat_dropped_after_logout():
    server = MockSupabaseLicenseServer()
    key = "LOVI-TEST-KEY-1111"
    client = LicenseClient(server, device_id="device_A", fingerprint="fp_A")
    client.activate_key(key)
    assert client.is_active is True

    # Client đăng xuất (AC-38)
    client.logout()
    assert client.is_active is False
    assert client.current_session is None

    # Giả lập heartbeat chậm về sau khi logout
    hb_res = client.send_heartbeat()
    assert hb_res.success is False
    assert client.is_active is False
