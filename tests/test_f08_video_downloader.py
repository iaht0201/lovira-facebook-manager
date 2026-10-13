import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
import yt_dlp

from src.lovira.integrations.downloaders.video_downloader import (
    SupportedPlatform,
    DownloadErrorCode,
    DownloadCancelledException,
    VideoDownloader,
)


def test_detect_platform():
    assert VideoDownloader.detect_platform("https://www.douyin.com/video/7123456789") == SupportedPlatform.DOUYIN
    assert VideoDownloader.detect_platform("https://v.douyin.com/iABCxyz/") == SupportedPlatform.DOUYIN
    assert VideoDownloader.detect_platform("https://www.tiktok.com/@creator/video/12345678") == SupportedPlatform.TIKTOK
    assert VideoDownloader.detect_platform("https://www.bilibili.com/video/BV1xx411c7mD") == SupportedPlatform.BILIBILI
    assert VideoDownloader.detect_platform("https://b23.tv/xyz123") == SupportedPlatform.BILIBILI
    assert VideoDownloader.detect_platform("https://example.com/video.mp4") == SupportedPlatform.GENERIC


def test_map_error():
    assert VideoDownloader.map_error("This video requires login to view.") == DownloadErrorCode.LOGIN_REQUIRED
    assert VideoDownloader.map_error("Video is private or unavailable.") == DownloadErrorCode.PRIVATE_VIDEO
    assert VideoDownloader.map_error("Video has been removed by author.") == DownloadErrorCode.VIDEO_DELETED
    assert VideoDownloader.map_error("No space left on device while writing.") == DownloadErrorCode.DISK_FULL
    assert VideoDownloader.map_error("Connection timed out on network read.") == DownloadErrorCode.NETWORK_ERROR


def test_extract_metadata_mocked():
    downloader = VideoDownloader()

    mock_info = {
        "id": "7123456",
        "title": "Douyin Cooking Video",
        "thumbnail": "https://p3.douyinpic.com/thumb.jpg",
        "duration": 45.2,
        "uploader": "Chef Zhang",
        "width": 1080,
        "height": 1920,
    }

    with patch.object(yt_dlp.YoutubeDL, "extract_info", return_value=mock_info):
        meta = downloader.extract_metadata("https://www.douyin.com/video/7123456")

        assert meta.source_platform == SupportedPlatform.DOUYIN
        assert meta.video_id == "7123456"
        assert meta.title == "Douyin Cooking Video"
        assert meta.duration == 45.2
        assert meta.thumbnail_url == "https://p3.douyinpic.com/thumb.jpg"
        assert meta.width == 1080
        assert meta.height == 1920


def test_download_cancellation():
    downloader = VideoDownloader()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        with patch.object(yt_dlp.YoutubeDL, "extract_info", side_effect=DownloadCancelledException("Cancelled")):
            with pytest.raises(DownloadCancelledException):
                downloader.download(
                    url="https://www.tiktok.com/@user/video/123",
                    output_dir=output_dir,
                    is_cancelled=lambda: True,
                )
