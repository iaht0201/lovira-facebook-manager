"""
Snapshot capture utility for UX-12: Settings 2.0 & Activity Log 2.0.
Captures mockups matching 07_cai_dat.png and 10_nhat_ky.png.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.licensing.client import LicenseClient, OfflineFallbackLicenseBackend
from src.lovira.ui.views.settings_workspace import SettingsWorkspaceView
from src.lovira.ui.views.activity_workspace import ActivityWorkspaceView
from src.lovira.ui.design.theme_manager import ThemeManager


def capture_snapshots():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_snapshot", "-platform", "offscreen"])

    ThemeManager.get_instance().apply_theme(app)

    db_path = project_root / "test_snapshot_ux12.db"
    if db_path.exists():
        db_path.unlink()

    db = DatabaseManager(db_path)
    runner = MigrationRunner(db)
    runner.apply_all()

    backend = OfflineFallbackLicenseBackend()
    license_client = LicenseClient(backend, "DEV-8F92-A74B-91C0", "FP-LOVIRA-PRO")

    out_dir = project_root / "docs" / "redesign_screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Chụp Settings Workspace 2.0
    view_settings = SettingsWorkspaceView(db_manager=db, license_client=license_client)
    view_settings.resize(1180, 800)
    view_settings.show()
    app.processEvents()

    settings_path = out_dir / "07_settings_v2.png"
    pix_settings = view_settings.grab()
    pix_settings.save(str(settings_path), "PNG")
    print(f"Settings snapshot saved to {settings_path} ({settings_path.stat().st_size} bytes)")
    view_settings.close()

    # 2. Chụp Activity Workspace 2.0
    view_activity = ActivityWorkspaceView(db_manager=db)
    view_activity.resize(1180, 720)
    view_activity.show()
    app.processEvents()

    activity_path = out_dir / "10_activity_v2.png"
    pix_activity = view_activity.grab()
    pix_activity.save(str(activity_path), "PNG")
    print(f"Activity snapshot saved to {activity_path} ({activity_path.stat().st_size} bytes)")
    view_activity.close()

    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    capture_snapshots()
