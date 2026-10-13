"""
Lovira-Facebook Manager
Script Đóng gói Ứng dụng Desktop (Packaging & Build Script)
Hỗ trợ cả PyInstaller và Nuitka (Section 17.2, Reference S15)
- Windows x64: Tạo Lovira-Facebook-Manager.exe độc lập
- Linux x64: Tạo standalone binary có bundle font, ffmpeg và thư viện C runtime
"""

import sys
import subprocess
from pathlib import Path


def build_with_pyinstaller(project_root: Path, output_dir: Path) -> int:
    """Đóng gói bằng PyInstaller."""
    entrypoint = project_root / "src" / "lovira" / "app.py"
    migrations_dir = project_root / "migrations" / "local"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=Lovira-Facebook-Manager",
        "--onedir",
        "--windowed",
        f"--add-data={migrations_dir};migrations/local" if sys.platform == "win32" else f"--add-data={migrations_dir}:migrations/local",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=yt_dlp",
        "--hidden-import=imageio_ffmpeg",
        f"--distpath={output_dir / 'dist'}",
        f"--workpath={output_dir / 'build'}",
        str(entrypoint),
    ]

    print(f"Bắt đầu đóng gói PyInstaller: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    print("=== LOVIRA-FACEBOOK MANAGER BUILD SCRIPT ===")
    print(f"Hệ điều hành: {sys.platform}")
    print(f"Thư mục nguồn: {project_root}")
    print(f"Thư mục đầu ra: {dist_dir}")

    # Kiểm tra xem PyInstaller đã cài chưa
    try:
        import PyInstaller
        code = build_with_pyinstaller(project_root, project_root)
        if code == 0:
            print("Đóng gói thành công!")
        else:
            print(f"Đóng gói kết thúc với mã lỗi: {code}")
    except ImportError:
        print("Chưa cài đặt PyInstaller trong môi trường hiện tại.")
        print("Để đóng gói, chạy: pip install pyinstaller && python packaging/build_desktop.py")


if __name__ == "__main__":
    main()
