from unittest.mock import patch, MagicMock
from src.lovira.integrations.facebook.client import FacebookGraphClient


def test_inspect_user_token_with_multiple_pages():
    # AC-02: Thêm một kết nối có nhiều Page -> Hiện đúng Page được cấp quyền, chọn kết nối không bị ghi đè chéo
    client = FacebookGraphClient()

    # Giả lập /me trả về user info
    me_resp = MagicMock()
    me_resp.status_code = 200
    me_resp.json.return_value = {
        "id": "user_1001",
        "name": "Nguyen Van A",
    }

    # Giả lập /me/accounts trả về 2 fanpage độc lập
    accounts_resp = MagicMock()
    accounts_resp.status_code = 200
    accounts_resp.json.return_value = {
        "data": [
            {
                "id": "page_2001",
                "name": "Lovira Fashion",
                "access_token": "EAABpage_token_2001",
                "tasks": ["CREATE_CONTENT", "MANAGE"],
                "category": "Clothing Store",
            },
            {
                "id": "page_2002",
                "name": "Lovira Beauty",
                "access_token": "EAABpage_token_2002",
                "tasks": ["CREATE_CONTENT", "MODERATE"],
                "category": "Beauty",
            },
        ]
    }

    def mock_get(url, params=None, **kwargs):
        if "/me/accounts" in url:
            return accounts_resp
        if "/me" in url:
            return me_resp
        raise ValueError(f"Unexpected url: {url}")

    with patch.object(client.session, "get", side_effect=mock_get):
        token_info = client.inspect_token("EAABuser_token_valid")

        assert token_info.is_valid is True
        assert token_info.token_type == "USER"
        assert token_info.id == "user_1001"
        assert token_info.name == "Nguyen Van A"
        assert len(token_info.pages) == 2

        # Kiểm tra token và ID của từng Page không bị lẫn lộn
        p1 = token_info.pages[0]
        p2 = token_info.pages[1]
        assert p1.page_id == "page_2001"
        assert p1.access_token == "EAABpage_token_2001"
        assert "CREATE_CONTENT" in p1.tasks

        assert p2.page_id == "page_2002"
        assert p2.access_token == "EAABpage_token_2002"


def test_inspect_page_token_directly():
    # AC-03: Nhập Page token -> Không tự gán thông tin tài khoản hoặc Page khác chưa được cấp quyền
    client = FacebookGraphClient()

    me_resp = MagicMock()
    me_resp.status_code = 200
    me_resp.json.return_value = {
        "id": "page_3001",
        "name": "Direct Page Only",
    }

    accounts_resp = MagicMock()
    accounts_resp.status_code = 200
    accounts_resp.json.return_value = {"data": []}

    page_info_resp = MagicMock()
    page_info_resp.status_code = 200
    page_info_resp.json.return_value = {
        "id": "page_3001",
        "name": "Direct Page Only",
        "category": "App",
        "tasks": ["CREATE_CONTENT"],
    }

    def mock_get(url, params=None, **kwargs):
        if "/me/accounts" in url:
            return accounts_resp
        if "/me" in url:
            return me_resp
        if "/page_3001" in url:
            return page_info_resp
        raise ValueError(f"Unexpected url: {url}")

    with patch.object(client.session, "get", side_effect=mock_get):
        token_info = client.inspect_token("EAABpage_token_direct")

        assert token_info.is_valid is True
        assert token_info.token_type == "PAGE"
        assert token_info.id == "page_3001"
        assert len(token_info.pages) == 1
        assert token_info.pages[0].page_id == "page_3001"


def test_parse_api_error_codes():
    # AC-20: Token hết hạn (code 190)
    is_exp, is_rate, msg = FacebookGraphClient.parse_api_error({"code": 190, "message": "Session has expired"})
    assert is_exp is True
    assert is_rate is False
    assert "cần kết nối lại" in msg

    # AC-21: Rate limit (code 32)
    is_exp, is_rate, msg = FacebookGraphClient.parse_api_error({"code": 32, "message": "Rate limit exceeded"})
    assert is_exp is False
    assert is_rate is True
    assert "Rate Limit" in msg

    # Thiếu quyền (code 200)
    is_exp, is_rate, msg = FacebookGraphClient.parse_api_error({"code": 200, "message": "Permission denied"})
    assert is_exp is False
    assert is_rate is False
    assert "chưa có quyền đăng" in msg
