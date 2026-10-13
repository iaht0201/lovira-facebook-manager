"""
Snapshot capture utility for UX-11: Comments Workspace 2.0.
Captures mockup matching 06_binh_luan.png.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Đảm bảo đường dẫn import
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.comment_repository import CommentCacheRepository, ReplyTemplateRepository
from src.lovira.security.vault import SecretVault
from src.lovira.ui.views.comments_workspace import CommentsWorkspaceView
from src.lovira.ui.design.theme_manager import ThemeManager


def capture_snapshot():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_snapshot", "-platform", "offscreen"])

    ThemeManager.get_instance().apply_theme(app)


    # DB tạm thời để chụp ảnh trực quan
    db_path = project_root / "test_snapshot_comments.db"
    if db_path.exists():
        db_path.unlink()

    db = DatabaseManager(db_path)
    runner = MigrationRunner(db)
    runner.apply_all()

    vault = SecretVault(db)
    page_repo = PageRepository(db, vault)
    comment_repo = CommentCacheRepository(db)
    reply_repo = ReplyTemplateRepository(db)

    # Dữ liệu demo sinh động
    p1 = page_repo.upsert_page("fb_page_01", "Lovira Fashion Store", status="ready")
    p2 = page_repo.upsert_page("fb_page_02", "Lovira Skincare Official", status="ready")

    # Mẫu câu
    reply_repo.create_template("Báo giá & Size", "Chào bạn, mẫu này shop còn size S, M, L nha! Giá niêm yết 350.000đ, miễn phí vận chuyển hôm nay ạ.")
    reply_repo.create_template("Tư vấn da", "Chào bạn, loại serum này cực kỳ phù hợp cho da dầu mụn ạ. Shop đã gửi phác đồ sử dụng qua inbox nhé!")

    # Comments
    c1 = comment_repo.upsert_comment(
        page_id=p1,
        remote_comment_id="c_101",
        post_id="post_reels_01",
        metadata={
            "from": {"name": "Nguyễn Thùy Linh", "id": "u_101"},
            "message": "Váy này có kèm thắt lưng không shop ơi? Cho mình xin size L với ạ!",
            "created_time": "2026-10-13T10:15:00+00:00",
            "comment_count": 0,
            "is_hidden": False,
        },
    )

    c2 = comment_repo.upsert_comment(
        page_id=p1,
        remote_comment_id="c_102",
        post_id="post_reels_01",
        metadata={
            "from": {"name": "Hoàng Minh Tuấn", "id": "u_102"},
            "message": "Chất vải có co giãn không ạ, mình cao 1m75 nặng 68kg mặc vừa size nào?",
            "created_time": "2026-10-13T09:40:00+00:00",
            "comment_count": 1,
            "is_hidden": False,
        },
    )

    c3 = comment_repo.upsert_comment(
        page_id=p2,
        remote_comment_id="c_103",
        post_id="post_video_02",
        metadata={
            "from": {"name": "Phạm Mai Anh", "id": "u_103"},
            "message": "Dùng được 2 tuần thấy da sáng mịn hơn hẳn, 10 sao cho shop!",
            "created_time": "2026-10-13T08:20:00+00:00",
            "comment_count": 0,
            "is_hidden": False,
        },
    )

    view = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )
    view.resize(1180, 720)
    view.show()

    # Chọn hàng đầu tiên để hiển thị chi tiết bên phải
    view.reload_comments()
    view.table_comments.selectRow(0)
    view._on_comment_selected(0, 0)
    view.input_reply.setPlainText("Chào bạn Linh, mẫu váy này có kèm sẵn thắt lưng da cao cấp cùng tông nhé ạ. Shop đang nhắn tin cho bạn đây!")

    app.processEvents()

    out_dir = project_root / "docs" / "redesign_screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "06_comments_v2.png"

    pixmap = view.grab()
    pixmap.save(str(out_path), "PNG")
    print(f"Snapshot saved successfully to {out_path} ({out_path.stat().st_size} bytes)")

    # Dọn dẹp
    view.close()
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass



if __name__ == "__main__":
    capture_snapshot()
