from unittest.mock import patch, MagicMock
from src.lovira.licensing.supabase_adapter import SupabaseAdapter
from src.lovira.licensing.models import LicenseErrorCode


def test_supabase_adapter_activate_success():
    adapter = SupabaseAdapter(supabase_url="https://xyz.supabase.co", anon_key="test-anon-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "session_id": "sess-uuid-1234",
        "generation": 1,
        "session_token": "token-hex-5678",
        "license_key_hint": "8888",
        "expires_at": "2026-12-31T23:59:59Z",
        "config_version": 2,
    }

    with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
        res = adapter.activate(
            key="LOVI-TEST-8888",
            device_id="dev-1",
            fingerprint="fp-1",
            app_version="0.1.0",
            force_transfer=False,
        )

        assert res.success is True
        assert res.session is not None
        assert res.session.session_id == "sess-uuid-1234"
        assert res.session.generation == 1
        assert res.session.license_key_hint == "8888"

        # Check call arguments
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "activate_license_rpc" in args[0]
        payload = kwargs["json"]
        assert payload["p_install_id"] == "dev-1"
        assert payload["p_force_transfer"] is False


def test_supabase_adapter_device_transfer_required():
    adapter = SupabaseAdapter(supabase_url="https://xyz.supabase.co", anon_key="test-anon-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": False,
        "error_code": "DEVICE_TRANSFER_REQUIRED",
        "message": "Key đang hoạt động trên máy khác.",
        "requires_transfer_confirmation": True,
    }

    with patch.object(adapter.session, "post", return_value=mock_resp):
        res = adapter.activate(
            key="LOVI-TEST-8888",
            device_id="dev-2",
            fingerprint="fp-2",
            app_version="0.1.0",
            force_transfer=False,
        )

        assert res.success is False
        assert res.error_code == LicenseErrorCode.DEVICE_TRANSFER_REQUIRED
        assert res.requires_transfer_confirmation is True


def test_supabase_adapter_heartbeat_revoked():
    adapter = SupabaseAdapter(supabase_url="https://xyz.supabase.co", anon_key="test-anon-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": False,
        "is_revoked": True,
        "message": "Phiên đã bị thu hồi.",
    }

    with patch.object(adapter.session, "post", return_value=mock_resp):
        hb = adapter.heartbeat(
            session_id="sess-1",
            generation=1,
            session_token="token-1",
            device_id="dev-1",
        )

        assert hb.success is False
        assert hb.is_revoked is True
        assert hb.error_code == LicenseErrorCode.SESSION_REVOKED
