"""
Lovira-Facebook Manager
Bộ xử lý Media & Tích hợp FFmpeg/ffprobe (MediaProcessor)
- Tính checksum SHA-256 stream an toàn
- Trích xuất thông số kỹ thuật video (duration, width, height, codec)
- Trích xuất thumbnail khung hình làm ảnh đại diện (BR-05, AC-04, AC-42)
- Tuyệt đối dùng subprocess với danh sách đối số, không dùng shell=True (Section 8.3)
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VideoFileInfo:
    file_path: Path
    checksum: str
    size_bytes: int
    duration: float
    width: Optional[int] = None
    height: Optional[int] = None
    codec_name: Optional[str] = None


class MediaProcessor:
    """Xử lý phân tích và tạo thumbnail cho video media."""

    def __init__(self, ffmpeg_exe: Optional[str] = None):
        self.ffmpeg_exe = ffmpeg_exe or self._find_ffmpeg()

    @staticmethod
    def _find_ffmpeg() -> str:
        """Tự động tìm kiếm ffmpeg binary (ưu tiên imageio-ffmpeg bundle, sau đó tới system PATH)."""
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                return exe
        except Exception:
            pass

        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        raise RuntimeError("Không tìm thấy executable của FFmpeg trong hệ thống.")

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """Tính mã băm SHA-256 stream theo từng khối 64KB (không nạp toàn bộ file vào RAM)."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    def inspect_video(self, file_path: Path) -> VideoFileInfo:
        """Kiểm tra và trích xuất thông số video qua FFmpeg."""
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"File video không tồn tại: {file_path}")

        size_bytes = file_path.stat().st_size
        checksum = self.calculate_sha256(file_path)

        duration = 0.0
        width = None
        height = None
        codec = None

        # Chạy ffmpeg -i <file> để đọc metadata từ stderr
        cmd = [self.ffmpeg_exe, "-hide_banner", "-i", str(file_path)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=15,
            )
            output = result.stderr

            # Bóc tách Duration: 00:00:45.20
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
            if dur_match:
                hours = int(dur_match.group(1))
                minutes = int(dur_match.group(2))
                seconds = float(dur_match.group(3))
                duration = hours * 3600 + minutes * 60 + seconds

            # Bóc tách Video Stream info: Video: h264, yuv420p, 1080x1920
            vid_match = re.search(r"Stream #\d+:\d+.*Video:\s*([a-zA-Z0-9_\-]+).*,\s*(\d+)x(\d+)", output)
            if vid_match:
                codec = vid_match.group(1)
                width = int(vid_match.group(2))
                height = int(vid_match.group(3))

        except Exception as e:
            logger.warning(f"Không thể đọc chi tiết video bằng ffmpeg: {e}")

        return VideoFileInfo(
            file_path=file_path,
            checksum=checksum,
            size_bytes=size_bytes,
            duration=duration,
            width=width,
            height=height,
            codec_name=codec,
        )

    def generate_thumbnail(
        self,
        video_path: Path,
        output_thumbnail_path: Path,
        at_second: float = 3.0,
    ) -> Path:
        """Trích xuất 1 frame làm ảnh thumbnail JPEG đại diện cho video (mặc định tại giây thứ 3)."""
        video_path = Path(video_path).resolve()
        output_thumbnail_path = Path(output_thumbnail_path).resolve()
        output_thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

        target_sec = max(0.0, at_second)
        # Nếu video ngắn hơn thời điểm yêu cầu, tự động lấy ở điểm giữa
        try:
            probe = self.inspect_video(video_path)
            if probe.duration > 0 and probe.duration <= target_sec:
                target_sec = max(0.0, probe.duration / 2.0)
        except Exception:
            pass

        cmd = [
            self.ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", f"{target_sec:.2f}",
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            "-y",
            str(output_thumbnail_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.returncode != 0 or not output_thumbnail_path.exists():
            raise RuntimeError(f"Tạo thumbnail thất bại: {result.stderr}")

        return output_thumbnail_path

    def extract_thumbnail(
        self,
        video_path: Path,
        output_thumbnail_path: Path,
        timestamp_sec: float = 3.0,
    ) -> Path:
        """Trích xuất 1 frame làm ảnh thumbnail JPEG tại timestamp_sec (mặc định giây thứ 3)."""
        return self.generate_thumbnail(video_path, output_thumbnail_path, at_second=timestamp_sec)
