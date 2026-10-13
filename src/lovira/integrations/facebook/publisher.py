"""
Lovira-Facebook Manager
Bộ điều phối Đăng bài Facebook Graph API (GraphPublishAdapter)
- Hỗ trợ đăng bài Text, Ảnh, Video chuẩn và Facebook Reels Publishing API (Section 6.2 & S8)
- Phân tách kết quả từng Page độc lập (AC-05)
- Thu thập Post ID, Video ID ngay khi nhận phản hồi để đối chiếu (AC-14)
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from src.lovira.domain.composer import ContentSnapshot, ContentType
from .client import FacebookGraphClient

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    success: bool
    post_id: Optional[str] = None
    video_id: Optional[str] = None
    upload_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: str = ""
    is_transient: bool = False  # Có thể retry hay không (AC-21)


class GraphPublishAdapter:
    """Hiện thực luồng đăng bài lên Facebook Graph API v21.0."""

    BASE_URL = "https://graph.facebook.com"
    API_VERSION = "v21.0"

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, endpoint: str) -> str:
        clean_endpoint = endpoint.lstrip("/")
        return f"{self.BASE_URL}/{self.API_VERSION}/{clean_endpoint}"

    def publish(
        self,
        page_token: str,
        snapshot: ContentSnapshot,
        facebook_page_id: Optional[str] = None,
    ) -> PublishResult:
        """Điều phối đăng nội dung tùy theo snapshot.content_type."""
        target_page_id = facebook_page_id or snapshot.page_id
        if snapshot.content_type == ContentType.TEXT:
            return self.publish_feed(page_token, target_page_id, snapshot.final_caption)
        elif snapshot.content_type == ContentType.PHOTO:
            return self.publish_photo(page_token, target_page_id, snapshot.final_caption, snapshot.media_path)
        elif snapshot.content_type == ContentType.VIDEO:
            return self.publish_video(page_token, target_page_id, snapshot.final_caption, snapshot.media_path)
        elif snapshot.content_type == ContentType.REELS:
            return self.publish_reels(page_token, target_page_id, snapshot.final_caption, snapshot.media_path)
        else:
            return PublishResult(
                success=False,
                error_message=f"Loại nội dung '{snapshot.content_type}' không được hỗ trợ.",
            )

    def publish_feed(self, page_token: str, page_id: str, message: str) -> PublishResult:
        """Đăng bài viết dạng văn bản lên Feed của Page."""
        url = self._url(f"/{page_id}/feed")
        payload = {
            "message": message,
            "access_token": page_token,
        }

        try:
            resp = self.session.post(url, data=payload, timeout=self.timeout)
            data = resp.json()

            if resp.status_code == 200 and "id" in data:
                return PublishResult(success=True, post_id=str(data["id"]))

            err = data.get("error", {})
            is_exp, is_rate, msg = FacebookGraphClient.parse_api_error(err)
            return PublishResult(
                success=False,
                error_code=str(err.get("code", "FB_ERROR")),
                error_message=msg,
                is_transient=is_rate,
            )
        except requests.RequestException as e:
            return PublishResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Lỗi mạng khi đăng bài: {e}",
                is_transient=True,
            )

    def publish_photo(self, page_token: str, page_id: str, caption: str, photo_path: Optional[str]) -> PublishResult:
        """Đăng ảnh lên Page."""
        if not photo_path or not os.path.exists(photo_path):
            return PublishResult(success=False, error_message="Không tìm thấy file ảnh đính kèm.")

        url = self._url(f"/{page_id}/photos")
        data = {
            "caption": caption,
            "access_token": page_token,
        }

        try:
            with open(photo_path, "rb") as f:
                files = {"source": f}
                resp = self.session.post(url, data=data, files=files, timeout=self.timeout)

            res_data = resp.json()
            if resp.status_code == 200 and "id" in res_data:
                return PublishResult(success=True, post_id=str(res_data["id"]))

            err = res_data.get("error", {})
            is_exp, is_rate, msg = FacebookGraphClient.parse_api_error(err)
            return PublishResult(
                success=False,
                error_code=str(err.get("code", "FB_ERROR")),
                error_message=msg,
                is_transient=is_rate,
            )
        except requests.RequestException as e:
            return PublishResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Lỗi mạng khi tải ảnh lên: {e}",
                is_transient=True,
            )

    def publish_video(self, page_token: str, page_id: str, description: str, video_path: Optional[str]) -> PublishResult:
        """Đăng video tiêu chuẩn lên Page (/videos)."""
        if not video_path or not os.path.exists(video_path):
            return PublishResult(success=False, error_message="Không tìm thấy file video.")

        url = self._url(f"/{page_id}/videos")
        data = {
            "description": description,
            "access_token": page_token,
        }

        try:
            with open(video_path, "rb") as f:
                files = {"source": f}
                resp = self.session.post(url, data=data, files=files, timeout=self.timeout)

            res_data = resp.json()
            if resp.status_code == 200 and "id" in res_data:
                vid_id = str(res_data["id"])
                return PublishResult(success=True, post_id=vid_id, video_id=vid_id)

            err = res_data.get("error", {})
            is_exp, is_rate, msg = FacebookGraphClient.parse_api_error(err)
            return PublishResult(
                success=False,
                error_code=str(err.get("code", "FB_ERROR")),
                error_message=msg,
                is_transient=is_rate,
            )
        except requests.RequestException as e:
            return PublishResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Lỗi mạng khi tải video lên: {e}",
                is_transient=True,
            )

    def publish_reels(self, page_token: str, page_id: str, description: str, video_path: Optional[str]) -> PublishResult:
        """
        Quy trình Đăng Facebook Reels 3 bước (Section 6.2 & S8):
        - Bước 1: Khởi tạo phiên upload (POST /{page_id}/video_reels upload_phase=start)
        - Bước 2: Tải binary video lên upload_url
        - Bước 3: Xuất bản Reels (POST /{page_id}/video_reels upload_phase=finish)
        """
        if not video_path or not os.path.exists(video_path):
            return PublishResult(success=False, error_message="Không tìm thấy file video cho Reels.")

        file_size = os.path.getsize(video_path)

        # BƯỚC 1: START UPLOAD SESSION
        init_url = self._url(f"/{page_id}/video_reels")
        init_payload = {
            "upload_phase": "start",
            "access_token": page_token,
        }

        try:
            init_resp = self.session.post(init_url, data=init_payload, timeout=self.timeout)
            init_data = init_resp.json()

            if init_resp.status_code != 200 or "video_id" not in init_data or "upload_url" not in init_data:
                err = init_data.get("error", {})
                is_exp, is_rate, msg = FacebookGraphClient.parse_api_error(err)
                return PublishResult(
                    success=False,
                    error_code=str(err.get("code", "REELS_START_FAILED")),
                    error_message=f"Khởi tạo Reels thất bại: {msg}",
                    is_transient=is_rate,
                )

            video_id = str(init_data["video_id"])
            upload_url = str(init_data["upload_url"])

            # BƯỚC 2: TRANSFER VIDEO BINARY
            headers = {
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(file_size),
            }

            with open(video_path, "rb") as vf:
                upload_resp = self.session.post(
                    upload_url,
                    headers=headers,
                    data=vf,
                    timeout=self.timeout * 2,
                )

            if upload_resp.status_code not in (200, 201):
                return PublishResult(
                    success=False,
                    video_id=video_id,
                    error_code="REELS_TRANSFER_FAILED",
                    error_message=f"Tải video lên Facebook Reels thất bại ({upload_resp.status_code}).",
                    is_transient=True,
                )

            # BƯỚC 3: FINISH & PUBLISH REELS
            finish_url = self._url(f"/{page_id}/video_reels")
            finish_payload = {
                "upload_phase": "finish",
                "access_token": page_token,
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
            }

            finish_resp = self.session.post(finish_url, data=finish_payload, timeout=self.timeout)
            finish_data = finish_resp.json()

            if finish_resp.status_code == 200 and finish_data.get("success", True):
                return PublishResult(
                    success=True,
                    post_id=video_id,
                    video_id=video_id,
                    upload_id=video_id,
                )

            err = finish_data.get("error", {})
            return PublishResult(
                success=False,
                video_id=video_id,
                error_code=str(err.get("code", "REELS_FINISH_FAILED")),
                error_message=f"Xuất bản Reels thất bại: {err.get('message', 'Không rõ nguyên nhân')}",
                is_transient=False,
            )

        except requests.RequestException as e:
            return PublishResult(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=f"Lỗi mạng khi đăng Reels: {e}",
                is_transient=True,
            )
