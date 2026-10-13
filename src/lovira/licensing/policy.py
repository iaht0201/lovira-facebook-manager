"""
Lovira-Facebook Manager
Chính sách Bản quyền, Công tắc Miễn phí & Phân quyền Offline (Policy Manager)
Tuân thủ Ma trận phân quyền Section 11.7 & Cấu hình Supabase Section 12.2
(AC-26, AC-27, AC-28, AC-36, AC-40, AC-43)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from .models import SessionState, LicenseSession


@dataclass
class ContactInfo:
    support_name: str = "Lovira Support"
    hotline: str = "0988-xxx-xxx"
    zalo: str = "https://zalo.me/lovira"
    email: str = "support@lovira.vn"
    website: str = "https://lovira.vn"
    purchase_notice: str = "Liên hệ chủ sản phẩm để nhận License Key trải nghiệm đầy đủ tính năng."


@dataclass
class RemoteAppConfig:
    license_required: bool = True
    max_active_sessions_global: Optional[int] = None
    free_features: Dict[str, bool] = field(
        default_factory=lambda: {
            "view_local_data": True,
            "compose_drafts": True,
            "export_backup": True,
            "download_video": False,
            "publish_post": False,
            "publish_reels": False,
            "sync_facebook": False,
        }
    )
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    maintenance_mode: bool = False
    maintenance_message: str = "Hệ thống đang bảo trì. Vui lòng quay lại sau."
    contact_info: ContactInfo = field(default_factory=ContactInfo)
    min_app_version: str = "0.1.0"
    config_version: int = 1
    issued_at_utc: str = ""
    expires_at_utc: str = ""  # Cache TTL cho config

    def is_cache_expired(self) -> bool:
        """Kiểm tra cấu hình đã hết hạn chưa (AC-36)."""
        if not self.expires_at_utc:
            return True
        try:
            exp = datetime.fromisoformat(self.expires_at_utc.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > exp
        except Exception:
            return True


class AccessPolicyManager:
    """Quản lý thực thi ma trận quyền dựa trên phiên và cấu hình từ xa."""

    OFFLINE_ALWAYS_ALLOWED = {
        "view_local_data",
        "compose_drafts",
        "save_draft",
        "export_backup",
        "cancel_local_job",
        "play_downloaded_media",
    }

    ONLINE_ACTION_REQUIRES_LICENSE = {
        "download_video",
        "sync_facebook",
        "publish_post",
        "publish_reels",
        "post_comment",
    }

    def __init__(self, config: Optional[RemoteAppConfig] = None):
        self.config = config or RemoteAppConfig()

    def update_config(self, new_config: RemoteAppConfig) -> None:
        self.config = new_config

    def evaluate_action(
        self,
        action: str,
        session: Optional[LicenseSession],
        is_online: bool = True,
    ) -> Tuple[bool, str]:
        """
        Đánh giá xem hành động có được phép thực hiện không:
        1. Hành động local luôn được phép dù offline hay hết hạn (AC-27, AC-43).
        2. Nếu đang bảo trì -> chặn.
        3. Nếu cấu hình offline hết hạn và không kết nối được -> không tự mở miễn phí (AC-26, AC-36).
        4. Trong chế độ miễn phí (`license_required=False`), kiểm tra `free_features`.
        5. Trong chế độ trả phí (`license_required=True`), bắt buộc phải có phiên active hợp lệ (AC-28, AC-40).
        """
        # 1. Các hành động local bảo vệ dữ liệu người dùng
        if action in self.OFFLINE_ALWAYS_ALLOWED:
            return True, "Thao tác cục bộ được phép."

        # 2. Chế độ bảo trì hệ thống
        if self.config.maintenance_mode:
            return False, f"Hệ thống đang bảo trì: {self.config.maintenance_message}"

        # 3. Khi mất kết nối hoặc không xác thực được
        if not is_online:
            # AC-26: Không tự mở miễn phí khi mất mạng tới server
            return False, "Không thể xác thực quyền trực tuyến. Thao tác này yêu cầu kết nối mạng và phiên bản quyền hợp lệ."

        # 4. Khi cache config đã quá hạn mà không cập nhật được mới
        if self.config.is_cache_expired():
            return False, "Cấu hình bản quyền đã hết hạn. Vui lòng kết nối máy chủ để cập nhật."

        # 5. Chế độ miễn phí
        if not self.config.license_required:
            is_feature_allowed = self.config.free_features.get(action, False)
            if is_feature_allowed:
                return True, "Được phép trong chế độ dùng miễn phí."
            return False, f"Tính năng '{action}' không khả dụng trong gói miễn phí."

        # 6. Chế độ yêu cầu license
        if session is None or session.state != SessionState.ACTIVE:
            return False, "Yêu cầu kích hoạt License Key để thực hiện thao tác này."

        return True, "Thao tác được cấp quyền."
