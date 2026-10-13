"""
Script chụp ảnh màn hình giao diện Schedule Workspace 2.0 (UX-08).
Lưu tại: docs/redesign_screenshots/04_schedule_v2.png
"""

import sys
import json
from pathlib import Path

# Thêm project root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.ui.views.schedule_workspace import ScheduleWorkspaceView
from src.lovira.ui.design.theme_manager import ThemeManager


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(["lovira_snapshot"])
    app.setFont(QFont("Segoe UI", 10))

    # DB tạm
    db_path = Path("tmp_schedule_snap.db")
    if db_path.exists():
        db_path.unlink()

    db_manager = DatabaseManager(db_path)
    runner = MigrationRunner(db_manager)
    runner.apply_all()

    # Dữ liệu mẫu phong phú
    with db_manager.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p1', 'fb_p1', 'Lovira Fashion Boutique');")
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p2', 'fb_p2', 'Lovira Cosmetics Official');")
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p3', 'fb_p3', 'Gia Dụng Thông Minh Lovira');")

        sample_jobs = [
            (
                "job_local_01", "p1",
                json.dumps({"final_caption": "Bộ sưu tập Đông - Xuân 2026: Phong cách thanh lịch và ấm áp #fashion #lovira"}),
                "scheduled_local", "2026-10-25T19:00:00Z", None, None
            ),
            (
                "job_remote_02", "p1",
                json.dumps({"final_caption": "Reels Viral: 5 cách phối đồ hack dáng cực đỉnh cho nàng công sở"}),
                "scheduled_remote", "2026-10-26T20:30:00Z", None, None
            ),
            (
                "job_pub_03", "p2",
                json.dumps({"final_caption": "Son kem lì Lovira Matte Red phiên bản giới hạn đón lễ hội #cosmetics"}),
                "published", "2026-10-20T12:00:00Z", None, None
            ),
            (
                "job_queue_04", "p3",
                json.dumps({"final_caption": "Top 3 robot hút bụi lau nhà tự động bán chạy nhất tháng 10"}),
                "queued", "2026-10-27T08:00:00Z", None, None
            ),
            (
                "job_err_05", "p2",
                json.dumps({"final_caption": "Serum phục hồi tái tạo màng da B5 Hyaluronic Acid"}),
                "failed_retryable", "2026-10-21T03:00:00Z", "Network timeout during upload", "ERR_NET_TIMEOUT"
            ),
            (
                "job_missed_06", "p1",
                json.dumps({"final_caption": "Flash Sale Giờ Vàng: Giảm 50% tất cả váy dạ hội"}),
                "missed", "2026-10-15T17:00:00Z", "Máy tính ngoại tuyến khi đến giờ đăng", "ERR_MACHINE_OFFLINE"
            ),
            (
                "job_unknown_07", "p3",
                json.dumps({"final_caption": "Chảo chống dính vân đá đáy từ cao cấp size 28cm"}),
                "unknown", "2026-10-22T05:00:00Z", "Mất kết nối giữa chừng cần đối chiếu", "ERR_UNKNOWN_STATE"
            ),
        ]

        for idx, (j_id, p_id, snap, st, sched_time, reason, err_code) in enumerate(sample_jobs):
            conn.execute(
                """
                INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc, blocked_reason, last_error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (j_id, f"batch_{idx}", f"req_{idx}", p_id, snap, st, sched_time, reason, err_code)
            )

    queue = PublishQueueRepository(db_manager)
    view = ScheduleWorkspaceView(db_manager=db_manager, queue_repo=queue)

    theme_mgr = ThemeManager.get_instance()
    theme_mgr.apply_theme(app)
    view.resize(1180, 740)
    view.show()
    app.processEvents()

    # Lưu snapshot
    out_dir = Path("docs/redesign_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "04_schedule_v2.png"

    pixmap = view.grab()
    pixmap.save(str(out_path), "PNG")
    print(f"Snapshot saved to: {out_path} ({out_path.stat().st_size} bytes)")

    if db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    main()
