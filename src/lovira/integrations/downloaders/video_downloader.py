"""
Lovira-Facebook Manager
Adapter Tải Video từ Douyin, TikTok, Bilibili (VideoDownloader)
Tích hợp yt-dlp với chuẩn hóa metadata, báo tiến độ mượt mà, hỗ trợ hủy tải và phân loại lỗi nguồn (BR-05, AC-04).
"""

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Any
import yt_dlp

logger = logging.getLogger(__name__)


class SupportedPlatform(str, Enum):
    DOUYIN = "douyin"
    TIKTOK = "tiktok"
    BILIBILI = "bilibili"
    GENERIC = "generic"


class DownloadErrorCode(str, Enum):
    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PRIVATE_VIDEO = "PRIVATE_VIDEO"
    VIDEO_DELETED = "VIDEO_DELETED"
    NETWORK_ERROR = "NETWORK_ERROR"
    DISK_FULL = "DISK_FULL"
    EXTRACTOR_FAILED = "EXTRACTOR_FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class VideoMetadata:
    source_url: str
    source_platform: SupportedPlatform
    video_id: str
    title: str
    thumbnail_url: str
    duration: float
    uploader: str
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class DownloadProgress:
    status: str  # 'downloading', 'finished', 'cancelled', 'error'
    percent: float  # 0.0 -> 100.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_bytes_sec: float = 0.0
    eta_seconds: Optional[int] = None


class DownloadCancelledException(Exception):
    """Ném ra khi người dùng chủ động bấm Hủy tải."""
    pass


class VideoDownloader:
    """Điều phối trích xuất thông tin và tải video an toàn ngoài luồng UI."""

    @staticmethod
    def detect_platform(url: str) -> SupportedPlatform:
        """Nhận diện nền tảng từ URL."""
        clean_url = url.lower()
        if "douyin.com" in clean_url or "iesdouyin.com" in clean_url:
            return SupportedPlatform.DOUYIN
        if "tiktok.com" in clean_url:
            return SupportedPlatform.TIKTOK
        if "bilibili.com" in clean_url or "b23.tv" in clean_url:
            return SupportedPlatform.BILIBILI
        return SupportedPlatform.GENERIC

    @classmethod
    def map_error(cls, error_msg: str) -> DownloadErrorCode:
        """Phân loại lỗi từ thông điệp của yt-dlp."""
        msg = error_msg.lower()
        if "login" in msg or "sign in" in msg or "authentication" in msg:
            return DownloadErrorCode.LOGIN_REQUIRED
        if "private" in msg or "not available" in msg:
            return DownloadErrorCode.PRIVATE_VIDEO
        if "deleted" in msg or "removed" in msg:
            return DownloadErrorCode.VIDEO_DELETED
        if "no space left on device" in msg or "disk full" in msg:
            return DownloadErrorCode.DISK_FULL
        if "network" in msg or "connection" in msg or "timed out" in msg:
            return DownloadErrorCode.NETWORK_ERROR
        if "unsupported url" in msg:
            return DownloadErrorCode.UNSUPPORTED_PLATFORM
        return DownloadErrorCode.EXTRACTOR_FAILED

    def extract_metadata(self, url: str) -> VideoMetadata:
        """Trích xuất thông tin metadata video mà không tải dữ liệu media."""
        platform = self.detect_platform(url)

        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise RuntimeError("Không thể trích xuất metadata từ URL này.")

                video_id = str(info.get("id", "unknown"))
                title = str(info.get("title") or f"Video {video_id}")
                thumbnail_url = str(info.get("thumbnail") or "")
                duration = float(info.get("duration") or 0.0)
                uploader = str(info.get("uploader") or info.get("uploader_id") or "Unknown")
                width = info.get("width")
                height = info.get("height")

                return VideoMetadata(
                    source_url=url,
                    source_platform=platform,
                    video_id=video_id,
                    title=title,
                    thumbnail_url=thumbnail_url,
                    duration=duration,
                    uploader=uploader,
                    width=width,
                    height=height,
                )
        except Exception as e:
            err_code = self.map_error(str(e))
            logger.error(f"Lỗi khi lấy thông tin video: {err_code} - {e}")
            raise RuntimeError(f"[{err_code.value}] {str(e)}") from e

    def download(
        self,
        url: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Path:
        """
        Tải video về đĩa:
        - Lưu vào file tạm `.downloading`
        - Cập nhật tiến độ qua progress_callback
        - Kiểm tra cờ is_cancelled để dừng kịp thời
        - Trả về đường dẫn file `.mp4` hoàn chỉnh
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Định dạng template file tạm
        temp_template = str(output_dir / "%(id)s_%(epoch)s.%(ext)s")
        downloaded_file_holder: list[str] = []

        def ydl_progress_hook(d: Dict[str, Any]) -> None:
            if is_cancelled and is_cancelled():
                raise DownloadCancelledException("Người dùng đã hủy quá trình tải.")

            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                speed = d.get("speed") or 0.0
                eta = d.get("eta")

                percent = (downloaded / total * 100.0) if total > 0 else 0.0
                if progress_callback:
                    progress_callback(
                        DownloadProgress(
                            status="downloading",
                            percent=min(99.9, percent),
                            downloaded_bytes=downloaded,
                            total_bytes=total,
                            speed_bytes_sec=speed,
                            eta_seconds=eta,
                        )
                    )
            elif status == "finished":
                filename = d.get("filename")
                if filename:
                    downloaded_file_holder.append(filename)
                if progress_callback:
                    progress_callback(
                        DownloadProgress(
                            status="finished",
                            percent=100.0,
                        )
                    )

        ydl_opts: Dict[str, Any] = {
            "outtmpl": temp_template,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [ydl_progress_hook],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                target_path = Path(ydl.prepare_filename(info))
                # yt-dlp có thể merge sang .mp4
                if not target_path.exists():
                    mp4_candidate = target_path.with_suffix(".mp4")
                    if mp4_candidate.exists():
                        target_path = mp4_candidate

                if not target_path.exists():
                    raise FileNotFoundError(f"Không tìm thấy file sau khi tải: {target_path}")

                return target_path

        except DownloadCancelledException:
            logger.info("Quá trình tải đã bị người dùng hủy.")
            raise
        except Exception as e:
            err_code = self.map_error(str(e))
            logger.error(f"Lỗi tải video: {err_code} - {e}")
            raise RuntimeError(f"[{err_code.value}] {str(e)}") from e
