"""
Lovira Workspace 2.0 — Hot Reload Dev Runner (dev.py)
Chế độ phát triển Hot Reload tự động:
- Theo dõi mọi thay đổi trong thư mục src/
- Tự động đóng và khởi động lại app ngay lập tức mỗi khi bạn bấm Ctrl + S lưu file
- Tích hợp Debounce tránh reload nhiều lần khi editor lưu file
"""

import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class AppReloader(FileSystemEventHandler):
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.process: subprocess.Popen | None = None
        self.last_reload_time = 0.0
        self.debounce_seconds = 0.4
        self.restart_app()

    def restart_app(self) -> None:
        """Đóng tiến trình app cũ và khởi chạy tiến trình mới."""
        if self.process is not None and self.process.poll() is None:
            print("🛑 Đang đóng phiên bản cũ...")
            try:
                self.process.terminate()
                self.process.wait(timeout=1.5)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
                except Exception:
                    pass

        # Đợi giải phóng lock file nếu cần
        time.sleep(0.15)

        print("\n🚀 Đang khởi động Lovira Workspace 2.0 (Hot Reload Enabled)...")
        print("💡 Gợi ý: Hãy sửa code hoặc CSS rồi bấm Ctrl + S, app sẽ tự động reload ngay!\n")
        
        self.process = subprocess.Popen(
            [sys.executable, "-m", "src.lovira.app"],
            cwd=str(self.target_dir),
        )

    def on_modified(self, event):
        self._handle_event(event)

    def on_created(self, event):
        self._handle_event(event)

    def _handle_event(self, event):
        # Bỏ qua thư mục và các file tạm thời
        if event.is_directory:
            return

        src_path = str(event.src_path)
        if not src_path.endswith(".py"):
            return

        if "__pycache__" in src_path or ".git" in src_path:
            return

        now = time.time()
        if now - self.last_reload_time < self.debounce_seconds:
            return

        self.last_reload_time = now
        relative_path = Path(src_path).name
        print(f"\n🔄 Phát hiện thay đổi trong [{relative_path}] -> Đang nạp lại ứng dụng...")
        self.restart_app()

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


def main():
    root_dir = Path(__file__).resolve().parent
    src_dir = root_dir / "src"

    if not src_dir.exists():
        print(f"Lỗi: Không tìm thấy thư mục {src_dir}")
        sys.exit(1)

    print("=" * 65)
    print("✨ LOVIRA WORKSPACE 2.0 — HOT RELOAD DEV SERVER ✨")
    print(f"📁 Giám sát thư mục: {src_dir}")
    print("=" * 65)

    handler = AppReloader(root_dir)
    observer = Observer()
    observer.schedule(handler, str(src_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(0.5)
            # Nếu người dùng tự bấm X đóng app, dev.py vẫn đợi lần lưu file tiếp theo để bật lại
            if handler.process and handler.process.poll() is not None:
                # App đã đóng thủ công
                pass
    except KeyboardInterrupt:
        print("\n👋 Đang dừng Dev Server...")
    finally:
        observer.stop()
        observer.join()
        handler.stop()
        print("Đã thoát.")


if __name__ == "__main__":
    main()
