import subprocess
import tempfile
from pathlib import Path

from src.lovira.media.processor import MediaProcessor


def test_calculate_sha256():
    with tempfile.TemporaryDirectory() as tmpdir:
        sample_file = Path(tmpdir) / "sample.txt"
        sample_file.write_bytes(b"Lovira Media Test Content 12345")

        checksum = MediaProcessor.calculate_sha256(sample_file)
        assert len(checksum) == 64
        # SHA-256 của chuỗi trên
        import hashlib
        expected = hashlib.sha256(b"Lovira Media Test Content 12345").hexdigest()
        assert checksum == expected


def test_ffmpeg_inspect_and_thumbnail_real():
    processor = MediaProcessor()
    assert processor.ffmpeg_exe is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "synth_video.mp4"
        thumb_path = Path(tmpdir) / "thumb.jpg"

        # Tạo 1 video MP4 2 giây giả lập bằng lavfi testsrc của ffmpeg
        create_cmd = [
            processor.ffmpeg_exe,
            "-f", "lavfi",
            "-i", "testsrc=duration=2:size=320x240:rate=30",
            "-pix_fmt", "yuv420p",
            "-y",
            str(video_path),
        ]
        res = subprocess.run(create_cmd, capture_output=True)
        assert res.returncode == 0
        assert video_path.exists()

        # 1. Inspect video
        info = processor.inspect_video(video_path)
        assert info.width == 320
        assert info.height == 240
        assert 1.8 <= info.duration <= 2.2
        assert info.size_bytes > 0
        assert len(info.checksum) == 64

        # 2. Generate thumbnail
        generated_thumb = processor.generate_thumbnail(video_path, thumb_path, at_second=0.5)
        assert generated_thumb.exists()
        assert generated_thumb.stat().st_size > 0
