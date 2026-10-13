from datetime import datetime, timezone, timedelta
from src.lovira.licensing.models import SessionState, LicenseSession
from src.lovira.licensing.policy import RemoteAppConfig, AccessPolicyManager


def test_offline_always_allowed_actions():
    # AC-27, AC-43: Soạn nháp, xem media, sao lưu luôn được phép dù không có license hoặc offline
    policy = AccessPolicyManager()

    allowed, _ = policy.evaluate_action("compose_drafts", session=None, is_online=False)
    assert allowed is True

    allowed, _ = policy.evaluate_action("save_draft", session=None, is_online=False)
    assert allowed is True

    allowed, _ = policy.evaluate_action("view_local_data", session=None, is_online=False)
    assert allowed is True

    allowed, _ = policy.evaluate_action("export_backup", session=None, is_online=False)
    assert allowed is True


def test_offline_blocks_publish_even_if_attempted():
    # AC-26: Khi mất kết nối tới dịch vụ license, KHÔNG tự ý cho phép publish mới
    policy = AccessPolicyManager()
    session = LicenseSession(
        session_id="sess_1",
        generation=1,
        session_token="tok_1",
        license_key_hint="1111",
        state=SessionState.ACTIVE,
    )

    allowed, msg = policy.evaluate_action("publish_post", session=session, is_online=False)
    assert allowed is False
    assert "Không thể xác thực quyền trực tuyến" in msg


def test_free_mode_and_admin_reenabling_license():
    # AC-36, AC-40:
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    free_config = RemoteAppConfig(
        license_required=False,
        free_features={"view_local_data": True, "compose_drafts": True, "download_video": True, "publish_post": False},
        expires_at_utc=future_time,
    )
    policy = AccessPolicyManager(free_config)

    # Trong free mode, download_video được bật
    allowed, _ = policy.evaluate_action("download_video", session=None, is_online=True)
    assert allowed is True

    # Nhưng publish_post không nằm trong free_features -> bị chặn
    allowed, msg = policy.evaluate_action("publish_post", session=None, is_online=True)
    assert allowed is False

    # Admin bật lại license_required = True (AC-27, AC-40)
    paid_config = RemoteAppConfig(
        license_required=True,
        expires_at_utc=future_time,
    )
    policy.update_config(paid_config)

    # Khi đó download_video mà không có session active -> bị chặn
    allowed, msg = policy.evaluate_action("download_video", session=None, is_online=True)
    assert allowed is False
    assert "Yêu cầu kích hoạt License Key" in msg


def test_expired_cached_config_rejected():
    # AC-36: Cấu hình miễn phí đã hết hạn trong quá khứ không thể dùng để mở khóa
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    expired_free_config = RemoteAppConfig(
        license_required=False,
        free_features={"download_video": True},
        expires_at_utc=past_time,
    )
    policy = AccessPolicyManager(expired_free_config)

    allowed, msg = policy.evaluate_action("download_video", session=None, is_online=True)
    assert allowed is False
    assert "hết hạn" in msg
