"""
Lovira-Facebook Manager
Facebook Graph API Client (FacebookGraphClient)
- Tương tác với Meta Graph API (v21.0)
- Kiểm tra User Access Token, Page Access Token và quyền tác vụ (tasks) (BR-03, AC-02, AC-03)
- Bóc tách phân loại lỗi nền tảng: Token expired (190), Rate Limit (4, 17, 32), Missing Permission (200) (AC-20, AC-21)
- Tuyệt đối che giấu token qua LogRedactor
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import requests
from src.lovira.security.redactor import LogRedactor

logger = logging.getLogger(__name__)


@dataclass
class FBPageItem:
    page_id: str
    name: str
    access_token: str
    tasks: List[str] = field(default_factory=list)
    category: str = ""
    avatar_url: str = ""


@dataclass
class FBTokenInfo:
    is_valid: bool
    token_type: str  # 'USER' hoặc 'PAGE'
    id: str  # user_id hoặc page_id
    name: str
    expires_at: Optional[str] = None
    tasks: List[str] = field(default_factory=list)
    pages: List[FBPageItem] = field(default_factory=list)
    error_message: str = ""


class FacebookGraphClient:
    """Khách hàng giao tiếp với Facebook Graph API."""

    BASE_URL = "https://graph.facebook.com"
    API_VERSION = "v21.0"

    def __init__(self, api_version: Optional[str] = None, timeout: float = 15.0):
        self.api_version = api_version or self.API_VERSION
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, endpoint: str) -> str:
        clean_endpoint = endpoint.lstrip("/")
        return f"{self.BASE_URL}/{self.api_version}/{clean_endpoint}"

    def inspect_token(self, token: str) -> FBTokenInfo:
        """
        Kiểm tra tính hợp lệ của token và phân loại:
        1. Gọi /me để xác định chủ thể và kiểu token.
        2. Nếu là User token -> lấy danh sách pages quản lý qua /me/accounts.
        3. Nếu là Page token -> lấy thông tin trang trực tiếp.
        """
        token_clean = token.strip()
        url = self._url("/me")
        params = {
            "fields": "id,name,picture",
            "access_token": token_clean,
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            data = resp.json()

            if resp.status_code != 200 or "error" in data:
                err = data.get("error", {})
                msg = err.get("message", "Token không hợp lệ.")
                code = err.get("code")
                logger.warning(f"Lỗi xác thực token Facebook (code {code}): {LogRedactor.redact_text(msg)}")
                return FBTokenInfo(
                    is_valid=False,
                    token_type="UNKNOWN",
                    id="",
                    name="",
                    error_message=f"[{code}] {msg}" if code else msg,
                )

            entity_id = str(data.get("id"))
            name = str(data.get("name"))

            # Thử gọi /me/accounts để xem token có phải là User Token hay không
            accounts_res = self.get_user_pages(token_clean)
            if accounts_res:
                # Đây là User Token có quản lý Fanpages (AC-02)
                return FBTokenInfo(
                    is_valid=True,
                    token_type="USER",
                    id=entity_id,
                    name=name,
                    pages=accounts_res,
                )
            else:
                # Có thể là Page Token trực tiếp (AC-03)
                page_info = self.get_page_info(token_clean, page_id=entity_id)
                if page_info:
                    return FBTokenInfo(
                        is_valid=True,
                        token_type="PAGE",
                        id=entity_id,
                        name=name,
                        tasks=page_info.tasks,
                        pages=[page_info],
                    )

                return FBTokenInfo(
                    is_valid=True,
                    token_type="USER",
                    id=entity_id,
                    name=name,
                    pages=[],
                )

        except requests.RequestException as e:
            logger.error(f"Lỗi mạng khi kiểm tra token Facebook: {e}")
            return FBTokenInfo(
                is_valid=False,
                token_type="UNKNOWN",
                id="",
                name="",
                error_message="Lỗi kết nối mạng tới Facebook Graph API.",
            )

    def get_user_pages(self, user_token: str) -> List[FBPageItem]:
        """Lấy danh sách Fanpages mà User Token có quyền truy cập (/me/accounts)."""
        url = self._url("/me/accounts")
        params = {
            "fields": "id,name,access_token,tasks,category,picture",
            "access_token": user_token,
            "limit": 100,
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            data = resp.json()
            items: List[FBPageItem] = []
            for item in data.get("data", []):
                picture_url = item.get("picture", {}).get("data", {}).get("url", "")
                items.append(
                    FBPageItem(
                        page_id=str(item["id"]),
                        name=str(item["name"]),
                        access_token=str(item["access_token"]),
                        tasks=item.get("tasks", []),
                        category=item.get("category", ""),
                        avatar_url=picture_url,
                    )
                )
            return items
        except requests.RequestException:
            return []

    def get_page_info(self, page_token: str, page_id: str = "me") -> Optional[FBPageItem]:
        """Lấy thông tin chi tiết một Fanpage bằng Page Access Token."""
        url = self._url(f"/{page_id}")
        params = {
            "fields": "id,name,category,picture",
            "access_token": page_token,
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data.get("category"):
                return None
            picture_url = data.get("picture", {}).get("data", {}).get("url", "")
            return FBPageItem(
                page_id=str(data.get("id")),
                name=str(data.get("name")),
                access_token=page_token,
                tasks=data.get("tasks") or ["CREATE_CONTENT", "MANAGE"],
                category=data.get("category", ""),
                avatar_url=picture_url,
            )
        except requests.RequestException:
            return None

    @staticmethod
    def parse_api_error(error_dict: Dict[str, Any]) -> Tuple[bool, bool, str]:
        """
        Phân loại lỗi Graph API:
        Trả về (is_expired, is_rate_limit, user_friendly_message) (AC-20, AC-21).
        """
        code = error_dict.get("code", 0)
        subcode = error_dict.get("error_subcode", 0)
        msg = error_dict.get("message", "Lỗi Facebook Graph API")

        # Mã 190: Token expired hoặc revoked
        if code == 190 or subcode in (463, 467):
            return True, False, "Page này cần kết nối lại. Token đã hết hạn hoặc bị hủy quyền truy cập."

        # Mã 4, 17, 32, 613: Rate limit
        if code in (4, 17, 32, 613):
            return False, True, "Facebook đang giới hạn tần suất yêu cầu (Rate Limit). Vui lòng thử lại sau ít phút."

        # Mã 200, 10: Quyền hạn
        if code in (200, 10):
            return False, False, "Kết nối hiện tại chưa có quyền đăng lên Page này (Thiếu quyền CREATE_CONTENT)."

        return False, False, f"[{code}] {msg}"
