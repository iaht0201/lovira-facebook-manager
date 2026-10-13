"""
Lovira-Facebook Manager
Màn hình Tổng quan Dashboard (OverviewWorkspaceView)
- Thống kê thời gian thực: Fanpage, Lịch đăng hôm nay, Kho video, Bản quyền (Section 4.1)
- Lối tắt thao tác nhanh (Tạo bài, Tải video, Thêm Page, Nhập Excel)
- Bảng nhật ký công việc đăng bài gần đây theo giờ Việt Nam
"""

from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QFrame,
)
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.domain.timezone import format_vn_display


class MetricCard(QFrame):
    """Thẻ thông số thống kê trực quan."""

    def __init__(self, icon: str, title: str, value: str, subtext: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size: 24px;")
        top_row.addWidget(lbl_icon)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #94A3B8;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.lbl_val = QLabel(value)
        self.lbl_val.setStyleSheet("font-size: 26px; font-weight: 700; color: #F8FAFC; margin-top: 4px;")
        layout.addWidget(self.lbl_val)

        self.lbl_sub = QLabel(subtext)
        self.lbl_sub.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(self.lbl_sub)

    def update_data(self, value: str, subtext: str) -> None:
        self.lbl_val.setText(value)
        self.lbl_sub.setText(subtext)


class OverviewWorkspaceView(QWidget):
    """Màn hình Tổng quan Dashboard."""

    quick_post_requested = Signal()
    download_video_requested = Signal()
    add_page_requested = Signal()
    bulk_import_requested = Signal()

    def __init__(
        self,
        db_manager: DatabaseManager,
        page_repo: PageRepository,
        media_repo: MediaRepository,
        queue_repo: PublishQueueRepository,
        license_client: LicenseClient,
        policy_manager: AccessPolicyManager,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.page_repo = page_repo
        self.media_repo = media_repo
        self.queue_repo = queue_repo
        self.license_client = license_client
        self.policy_manager = policy_manager

        self._init_ui()
        self.reload_dashboard_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        # 1. Header trên cùng
        header_row = QHBoxLayout()
        welcome_box = QVBoxLayout()
        welcome_box.setSpacing(4)
        title_lbl = QLabel("TỔNG QUAN HỆ THỐNG")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #818CF8; letter-spacing: 0.5px;")
        subtitle_lbl = QLabel("Quản lý Fanpage, video media, và lịch đăng Reels tự động theo giờ Việt Nam (UTC+7)")
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        welcome_box.addWidget(title_lbl)
        welcome_box.addWidget(subtitle_lbl)

        header_row.addLayout(welcome_box)
        header_row.addStretch()

        btn_refresh = QPushButton("🔄 Làm mới dữ liệu")
        btn_refresh.clicked.connect(self.reload_dashboard_data)
        header_row.addWidget(btn_refresh)
        layout.addLayout(header_row)

        # 2. Bốn Card thống kê
        cards_layout = QGridLayout()
        cards_layout.setSpacing(14)

        self.card_pages = MetricCard("📑", "FANPAGE ĐANG KẾT NỐI", "0", "Chưa có Fanpage nào")
        self.card_schedules = MetricCard("📅", "LỊCH ĐĂNG CHỜ XỬ LÝ", "0", "Hôm nay: 0 bài")
        self.card_media = MetricCard("🎬", "KHO VIDEO MEDIA", "0", "0 MB lưu trữ")
        self.card_status = MetricCard("🛡️", "TRẠNG THÁI BẢN QUYỀN", "Kiểm tra...", "Lease: 180s")

        cards_layout.addWidget(self.card_pages, 0, 0)
        cards_layout.addWidget(self.card_schedules, 0, 1)
        cards_layout.addWidget(self.card_media, 0, 2)
        cards_layout.addWidget(self.card_status, 0, 3)

        layout.addLayout(cards_layout)

        # 3. Lối tắt thao tác nhanh (Quick Action Bar)
        action_frame = QFrame()
        action_frame.setObjectName("cardFrame")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(12)

        lbl_quick = QLabel("⚡ Thao tác nhanh:")
        lbl_quick.setStyleSheet("font-weight: 700; color: #F8FAFC; font-size: 13px;")
        action_layout.addWidget(lbl_quick)

        btn_quick_post = QPushButton("➕ Tạo bài viết mới")
        btn_quick_post.setObjectName("primaryButton")
        btn_quick_post.clicked.connect(self.quick_post_requested.emit)
        action_layout.addWidget(btn_quick_post)

        btn_quick_download = QPushButton("📥 Tải video TikTok / Douyin")
        btn_quick_download.clicked.connect(self.download_video_requested.emit)
        action_layout.addWidget(btn_quick_download)

        btn_quick_page = QPushButton("📑 Thêm Fanpage mới")
        btn_quick_page.clicked.connect(self.add_page_requested.emit)
        action_layout.addWidget(btn_quick_page)

        btn_bulk_import = QPushButton("📊 Nhập Excel / CSV")
        btn_bulk_import.setObjectName("successButton")
        btn_bulk_import.clicked.connect(self.bulk_import_requested.emit)
        action_layout.addWidget(btn_bulk_import)

        action_layout.addStretch()
        layout.addWidget(action_frame)

        # 4. Bảng Các tác vụ đăng bài gần đây
        recent_frame = QFrame()
        recent_frame.setObjectName("cardFrame")
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(16, 14, 16, 14)
        recent_layout.setSpacing(10)

        recent_header = QHBoxLayout()
        lbl_recent = QLabel("📋 CÁC TÁC VỤ ĐĂNG BÀI GẦN ĐÂY")
        lbl_recent.setStyleSheet("font-size: 13px; font-weight: 700; color: #818CF8;")
        recent_header.addWidget(lbl_recent)
        recent_header.addStretch()
        recent_layout.addLayout(recent_header)

        self.table_recent = QTableWidget()
        self.table_recent.setColumnCount(5)
        self.table_recent.setHorizontalHeaderLabels([
            "Mã Tác vụ", "Page Đích", "Nội dung tóm tắt", "Giờ Đăng (Giờ VN)", "Trạng thái"
        ])
        self.table_recent.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_recent.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_recent.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        recent_layout.addWidget(self.table_recent)

        layout.addWidget(recent_frame)

    def reload_dashboard_data(self) -> None:
        """Đọc dữ liệu từ SQLite để cập nhật các card và bảng."""
        # 1. Thống kê Page
        pages = self.page_repo.list_pages()
        ready_pages = [p for p in pages if p.get("status") == "ready"]
        self.card_pages.update_data(
            value=str(len(pages)),
            subtext=f"{len(ready_pages)} Fanpage sẵn sàng hoạt động",
        )

        # 2. Thống kê Lịch đăng
        jobs = self.queue_repo.list_jobs(limit=100)
        pending_jobs = [j for j in jobs if j["state"] in ("scheduled_local", "queued", "uploading", "processing")]
        self.card_schedules.update_data(
            value=str(len(pending_jobs)),
            subtext=f"Tổng số {len(jobs)} tác vụ trong hàng đợi",
        )

        # 3. Thống kê Media
        assets = self.media_repo.list_media_assets(limit=500)
        total_bytes = sum(a.get("size_bytes", 0) or 0 for a in assets)
        size_mb = total_bytes / (1024 * 1024)
        self.card_media.update_data(
            value=str(len(assets)),
            subtext=f"{size_mb:.1f} MB lưu trữ trên máy",
        )

        # 4. Thống kê License
        if not self.policy_manager.config.license_required:
            self.card_status.update_data("Miễn phí", "Chế độ mở tự do toàn hệ thống")
        elif self.license_client.is_active:
            self.card_status.update_data("Đã kích hoạt", f"Session: {self.license_client.current_session.session_id[:8]}...")
        else:
            self.card_status.update_data("Chưa có Key", "Vui lòng nhập License Key")

        # 5. Cập nhật Bảng tác vụ gần đây (tối đa 10 dòng)
        recent_jobs = jobs[:10]
        self.table_recent.setRowCount(len(recent_jobs))

        state_labels = {
            "scheduled_local": "📅 Đã lưu lịch",
            "queued": "⏳ Đang chờ",
            "uploading": "📤 Đang upload",
            "processing": "⚙️ FB đang xử lý",
            "published": "✅ Đã đăng thành công",
            "missed": "⚠️ Lỡ lịch",
            "paused": "⏸️ Tạm dừng",
            "failed_retryable": "🔄 Chờ thử lại",
            "failed_final": "❌ Lỗi",
            "unknown": "❓ Cần đối chiếu",
        }

        for row, job in enumerate(recent_jobs):
            self.table_recent.setItem(row, 0, QTableWidgetItem(job["id"][:12]))
            self.table_recent.setItem(row, 1, QTableWidgetItem(job.get("page_name") or job.get("page_id", "")))

            # Caption tóm tắt từ snapshot
            caption = job.get("snapshot_caption", "")
            short_caption = (caption[:40] + "...") if len(caption) > 40 else caption
            self.table_recent.setItem(row, 2, QTableWidgetItem(short_caption or "(Video Reels)"))

            # Giờ VN
            sched_utc = job.get("scheduled_at_utc")
            if sched_utc:
                vn_str = format_vn_display(sched_utc)
            else:
                vn_str = "Đăng ngay"
            self.table_recent.setItem(row, 3, QTableWidgetItem(vn_str))

            st = job.get("state", "unknown")
            self.table_recent.setItem(row, 4, QTableWidgetItem(state_labels.get(st, st)))
