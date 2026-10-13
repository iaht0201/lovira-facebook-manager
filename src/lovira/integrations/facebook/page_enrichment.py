"""Public Page details and conservative token diagnostics for Lovira.

Uses the FacebookGraphClient API version, but creates its own stateless HTTPS
requests so it is safe to call in a background QRunnable. API availability
and permissions vary by Meta app and Graph version.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class GraphRequestError(Exception):
    def __init__(self, message: str, *, code: Optional[int] = None, kind: str = "api"):
        super().__init__(message)
        self.code = code
        self.kind = kind


class PageEnrichmentClient:
    def __init__(self, fb_client):
        self.base = getattr(fb_client, "BASE_URL", "https://graph.facebook.com").rstrip("/")
        self.version = os.getenv("LOVIRA_FB_GRAPH_VERSION", "").strip() or getattr(fb_client, "api_version", "v21.0")
        self.timeout = min(float(getattr(fb_client, "timeout", 15)), 12.0)

    def _get(self, endpoint: str, token: str, **params) -> Dict[str, Any]:
        url = f"{self.base}/{self.version}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token.strip()}"},
                params=params,
                timeout=(5, self.timeout),
            )
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GraphRequestError("Không thể kết nối Facebook. Kiểm tra mạng và thử lại.", kind="network") from exc
        if not isinstance(data, dict):
            raise GraphRequestError("Facebook trả về dữ liệu không hợp lệ.", kind="network")
        if response.status_code >= 400 or data.get("error"):
            problem = data.get("error") or {}
            code = problem.get("code")
            try:
                code = int(code)
            except (ValueError, TypeError):
                code = None
            # NEVER send raw exception or Graph error's full text to a UI/logger:
            # Some errors echo sensitive request parameters.
            reason = {
                190: "Token đã hết hạn, không hợp lệ hoặc đã bị thu hồi.",
                10: "Facebook từ chối do thiếu quyền truy cập.",
                200: "Ứng dụng hoặc tài khoản không có quyền thực hiện yêu cầu.",
                4: "Facebook đang giới hạn tần suất truy cập.",
                17: "Facebook đang giới hạn tần suất truy cập.",
                32: "Facebook đang giới hạn tần suất truy cập.",
                613: "Facebook đang giới hạn tần suất truy cập.",
            }.get(code, "Yêu cầu Graph API bị từ chối (mã {}).".format(code or "không rõ"))
            raise GraphRequestError(reason, code=code, kind="api")
        return data

    def inspect_page_token(self, page_id: Optional[str], token: str,
                           tasks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Verify /me resolves to the intended PAGE; never guess privileges.

        Optional META app creds (LOVIRA_FB_APP_ID/LOVIRA_FB_APP_SECRET)
        enable /debug_token. Without them, expiry is genuinely unknown.
        """
        if not token or not token.strip():
            raise GraphRequestError("Vui lòng cung cấp Page Access Token.", kind="input")
        try:
            me = self._get("me", token, fields="id,name")
        except GraphRequestError as exc:
            # A network/rate error is NOT the same thing as token expiry.
            if exc.code == 190:
                return {"status": "token_expired", "is_valid": False,
                        "identity_verified": False, "error": str(exc),
                        "expires_at": None, "data_access_expires_at": None,
                        "scopes": [], "tasks": tasks or []}
            raise

        resolved_id = str(me.get("id", ""))
        if page_id and resolved_id != str(page_id):
            raise GraphRequestError(
                "Token không thuộc Page ID đã chọn. Không có dữ liệu nào bị ghi đè.", kind="identity"
            )
        if not resolved_id or not resolved_id.isdigit():
            raise GraphRequestError("Không đọc được Facebook Page ID từ token.", kind="identity")

        app_id = os.getenv("LOVIRA_FB_APP_ID", "").strip()
        app_secret = os.getenv("LOVIRA_FB_APP_SECRET", "").strip()
        scopes: List[str] = []
        expire: Optional[int] = None
        data_expire: Optional[int] = None
        token_type: Optional[str] = None
        if app_id and app_secret:
            try:
                debug = self._get("debug_token", f"{app_id}|{app_secret}", input_token=token).get("data", {})
                if debug.get("is_valid") is False:
                    return {"status": "token_expired", "is_valid": False,
                            "identity_verified": True, "error": "Facebook xác nhận token không hợp lệ.",
                            "expires_at": debug.get("expires_at"),
                            "data_access_expires_at": debug.get("data_access_expires_at"),
                            "scopes": [], "tasks": tasks or [], "type": debug.get("type")}
                token_type = debug.get("type")
                if token_type and str(token_type).upper() != "PAGE":
                    raise GraphRequestError(
                        "Đây không phải Page Access Token. Hãy sử dụng token của Fanpage.", kind="identity"
                    )
                scopes = list(debug.get("scopes") or [])
                expire = debug.get("expires_at")
                data_expire = debug.get("data_access_expires_at")
            except GraphRequestError as exc:
                if exc.kind == "identity":
                    raise
                # /me is verified; lack of debug access must NOT mark expired.
                pass

        if expire and int(expire) > 0:
            from datetime import datetime, timezone
            if int(expire) <= int(datetime.now(timezone.utc).timestamp()):
                return {"status": "token_expired", "is_valid": False,
                        "identity_verified": True, "expires_at": expire,
                        "data_access_expires_at": data_expire,
                        "scopes": scopes, "tasks": list(tasks or []),
                        "type": token_type or "PAGE", "error": "Token đã quá hạn."}

        assigned_tasks = list(tasks or [])
        caps = {str(t).upper() for t in assigned_tasks}
        permissions = {str(s).lower() for s in scopes}
        # Only a positive signal permits READY. The absence of audit data is
        # 'unverified', NOT a fabricated CREATE_CONTENT permission.
        can_post = ("CREATE_CONTENT" in caps or "pages_manage_posts" in permissions)
        if can_post:
            status = "ready"
        elif assigned_tasks or scopes:
            status = "insufficient_permissions"
        else:
            status = "unverified"
        return {
            "status": status,
            "is_valid": True,
            "identity_verified": True,
            "page_id": resolved_id,
            "name": str(me.get("name") or ""),
            "type": token_type or "PAGE (nhận diện bằng /me)",
            "expires_at": expire,
            "data_access_expires_at": data_expire,
            "scopes": scopes,
            "tasks": assigned_tasks,
            "error": "" if status == "ready" else (
                "Chưa xác minh được quyền đăng bài." if status == "unverified"
                else "Thiếu quyền pages_manage_posts hoặc tác vụ CREATE_CONTENT."
            ),
        }

    def fetch_public_info(self, page_id: str, token: str) -> Dict[str, Any]:
        """Fetch core first, then optional fields independently (best-effort).

        Missing/restricted fields remain None and render as '—' in the UI.
        """
        core_fields = "id,name,picture.type(large){url},category,link,username"
        try:
            core = self._get(page_id, token, fields=core_fields)
        except GraphRequestError:
            core = self._get(page_id, token, fields="id,name")
        if str(core.get("id")) != str(page_id):
            raise GraphRequestError("Facebook trả về Page ID khác. Đã từ chối cập nhật.", kind="identity")
        details: Dict[str, Any] = {
            "name": core.get("name"),
            "category": core.get("category"),
            "username": core.get("username"),
            "link": core.get("link") or f"https://www.facebook.com/{page_id}",
            "avatar_url": (core.get("picture") or {}).get("data", {}).get("url"),
        }
        # On an API version that rejects a single optional field, retry members
        # separately so follower data still shows when, say, cover is denied.
        for group in (
            ("followers_count", "fan_count"),
            ("about", "website", "phone"),
            ("cover", "verification_status"),
        ):
            try:
                details.update(self._get(page_id, token, fields=",".join(group)))
            except GraphRequestError as exc:
                if exc.code in (4, 17, 32, 613, 190) or exc.kind == "network":
                    break
                for field in group:
                    try:
                        details.update(self._get(page_id, token, fields=field))
                    except GraphRequestError:
                        continue
        cover = details.pop("cover", None)
        if isinstance(cover, dict):
            details["cover_url"] = cover.get("source")
        # Never persist Page access_token in metadata even if returned by API.
        allowed = {"name", "category", "username", "link", "avatar_url", "cover_url",
                   "followers_count", "fan_count", "about", "website", "phone", "verification_status"}
        return {k: v for k, v in details.items() if k in allowed}

    def scan_user_pages(self, user_token: str, limit_pages: int = 500) -> List[Dict[str, Any]]:
        """Paginate /me/accounts; no automatic persistence without selection."""
        found: List[Dict[str, Any]] = []
        after: Optional[str] = None
        seen = set()
        while len(found) < limit_pages:
            params = {"fields": "id,name,access_token,tasks,category,picture{url}", "limit": 100}
            if after:
                params["after"] = after
            data = self._get("me/accounts", user_token, **params)
            for item in data.get("data", []):
                pid = str(item.get("id", ""))
                if not pid or pid in seen or not item.get("access_token"):
                    continue
                seen.add(pid)
                found.append({"page_id": pid, "name": str(item.get("name") or pid),
                              "token": str(item["access_token"]), "tasks": item.get("tasks") or [],
                              "category": item.get("category", ""),
                              "avatar_url": (item.get("picture") or {}).get("data", {}).get("url", "")})
                if len(found) >= limit_pages:
                    break
            after_new = (data.get("paging") or {}).get("cursors", {}).get("after")
            if not after_new or after_new == after or not data.get("data"):
                break
            after = after_new
        return found
