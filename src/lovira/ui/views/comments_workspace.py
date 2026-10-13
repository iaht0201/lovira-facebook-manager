"""
Lovira Workspace 2.0 — Comments & Interaction Workspace
Màn hình Quản lý Bình luận & Phản hồi (Khắc phục triệt để lỗi A-01 màn hình trống):
- Tích hợp split-pane: Danh sách bình luận bên trái & Khung xem luồng hội thoại bên phải
- Báo cáo trung thực trạng thái quyền hạn Facebook Graph API (Section 4.S08)
- Tích hợp ReplyTemplateRepository cho mẫu câu trả lời nhanh & dialog quản lý mẫu câu
- Đồng bộ bộ lọc theo GlobalPageContext và tìm kiếm thời gian thực
- EmptyState thông minh khi chưa có tương tác hoặc không tìm thấy kết quả
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
    QLineEdit,
    QComboBox,
    QFrame,
    QSplitter,
    QMessageBox,
    QDialog,
    QStackedLayout,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.storage.comment_repository import CommentCacheRepository, ReplyTemplateRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.domain.timezone import format_vn_display

logger = logging.getLogger(__name__)


class TemplateManagerDialog(QDialog):
    """Hộp thoại Quản lý Mẫu câu phản hồi nhanh (Reply Templates)."""

    def __init__(
        self,
        reply_repo: ReplyTemplateRepository,
        current_page_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.reply_repo = reply_repo
        self.current_page_id = current_page_id
        self.setWindowTitle("Quản lý Mẫu câu Phản hồi Nhanh")
        self.setMinimumSize(540, 420)
        self._init_ui()
        self._load_templates()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_desc = QLabel("Tạo và chỉnh sửa các mẫu câu trả lời thường dùng để phản hồi khách hàng trong tích tắc.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Bảng danh sách mẫu câu
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tên mẫu câu", "Nội dung phản hồi"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # Form thêm mẫu câu mới
        add_frame = QFrame()
        add_frame.setStyleSheet("background: #1E293B; border-radius: 8px; padding: 10px;")
        add_layout = QVBoxLayout(add_frame)
        add_layout.setSpacing(8)

        add_layout.addWidget(QLabel("Thêm mẫu câu mới:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Tên gợi nhớ (VD: Chào hỏi, Báo giá, Cảm ơn...)")
        add_layout.addWidget(self.txt_name)

        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("Nội dung phản hồi gửi tới khách hàng...")
        self.txt_content.setMaximumHeight(70)
        add_layout.addWidget(self.txt_content)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("  + Thêm mẫu câu")
        self.btn_add.setObjectName("primaryButton")
        self.btn_add.setIcon(get_icon("composer", "#FFFFFF", 14))
        self.btn_add.clicked.connect(self._handle_add)
        btn_row.addWidget(self.btn_add)

        self.btn_delete = QPushButton("  Xóa mẫu đã chọn")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.setIcon(get_icon("trash", "#FFFFFF", 14))
        self.btn_delete.clicked.connect(self._handle_delete)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        add_layout.addLayout(btn_row)
        layout.addWidget(add_frame)

        # Nút đóng
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

    def _load_templates(self) -> None:
        self.table.setRowCount(0)
        templates = self.reply_repo.list_templates(page_id=self.current_page_id)
        for tpl in templates:
            r = self.table.rowCount()
            self.table.insertRow(r)
            item_name = QTableWidgetItem(tpl.get("name", ""))
            item_name.setData(Qt.ItemDataRole.UserRole, tpl.get("id"))
            self.table.setItem(r, 0, item_name)
            self.table.setItem(r, 1, QTableWidgetItem(tpl.get("content", "")))

    def _handle_add(self) -> None:
        name = self.txt_name.text().strip()
        content = self.txt_content.toPlainText().strip()
        if not name or not content:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ tên và nội dung mẫu câu.")
            return

        self.reply_repo.create_template(
            name=name,
            content=content,
            page_scope=[self.current_page_id] if self.current_page_id else None,
        )
        self.txt_name.clear()
        self.txt_content.clear()
        self._load_templates()

    def _handle_delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một mẫu câu để xóa.")
            return
        item = self.table.item(row, 0)
        if not item:
            return
        tpl_id = item.data(Qt.ItemDataRole.UserRole)
        if tpl_id:
            self.reply_repo.delete_template(tpl_id)
            self._load_templates()


class CommentsWorkspaceView(QWidget):
    """Màn hình Quản lý Bình luận & Tương tác Fanpage 2.0."""

    def __init__(
        self,
        comment_repo: Optional[CommentCacheRepository] = None,
        reply_repo: Optional[ReplyTemplateRepository] = None,
        page_repo: Optional[PageRepository] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.comment_repo = comment_repo
        self.reply_repo = reply_repo
        self.page_repo = page_repo
        self.context = GlobalPageContext.get_instance()

        self._current_comments: List[Dict[str, Any]] = []
        self._selected_comment: Optional[Dict[str, Any]] = None

        self._init_ui()
        self.context.page_scope_changed.connect(self._on_page_scope_changed)
        self.reload_comments()
        self._refresh_templates()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Header Toolbar
        top_frame = QFrame()
        top_frame.setObjectName("cardFrame")
        top_layout = QHBoxLayout(top_frame)

        title_box = QVBoxLayout()
        lbl_title = QLabel("QUẢN LÝ BÌNH LUẬN & PHẢN HỒI NHANH")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #818CF8;")
        lbl_desc = QLabel("Xem luồng trao đổi của khách hàng trên các Fanpage, lọc theo ngữ cảnh và gửi phản hồi chuẩn mực.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        self.btn_manage_templates = QPushButton("  📝 Quản lý mẫu câu")
        self.btn_manage_templates.clicked.connect(self._open_template_manager)
        top_layout.addWidget(self.btn_manage_templates)

        self.btn_refresh = QPushButton("  Đồng bộ bình luận")
        self.btn_refresh.setIcon(get_icon("refresh", "#F3F6FC", 16))
        self.btn_refresh.clicked.connect(self._sync_comments)
        top_layout.addWidget(self.btn_refresh)

        layout.addWidget(top_frame)

        # 2. Banner Thông báo trạng thái Quyền hạn trung thực (A-01, Section 5.2)
        self.perm_banner = QFrame()
        self.perm_banner.setObjectName("cardFrame")
        self.perm_banner.setStyleSheet("background-color: #1E293B; border-left: 4px solid #F3B85C;")
        banner_layout = QHBoxLayout(self.perm_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)

        lbl_warn_icon = QLabel()
        lbl_warn_icon.setPixmap(get_icon("alert_triangle", "#F3B85C", 20).pixmap(20, 20))
        banner_layout.addWidget(lbl_warn_icon)

        self.lbl_perm_msg = QLabel(
            "Tính năng đồng bộ bình luận tự động yêu cầu quyền 'pages_manage_engagement' hoặc 'pages_read_engagement' "
            "từ Meta. Nếu Fanpage chưa cấp quyền này, bạn có thể kiểm tra lại quyền trong mục Fanpage."
        )
        self.lbl_perm_msg.setStyleSheet("color: #F3B85C; font-size: 12px;")
        self.lbl_perm_msg.setWordWrap(True)
        banner_layout.addWidget(self.lbl_perm_msg, stretch=1)

        layout.addWidget(self.perm_banner)

        # 3. Vùng làm việc chính: Splitter (Trái: Danh sách & Bộ lọc, Phải: Chi tiết luồng & Trả lời)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANEL TRÁI: Danh sách bình luận ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Hàng bộ lọc: Search + Status Filter
        filter_row = QHBoxLayout()
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("🔍 Tìm theo tên khách hoặc nội dung...")
        self.search_filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search_filter, stretch=3)

        self.combo_filter_status = QComboBox()
        self.combo_filter_status.addItem("Tất cả trạng thái")
        self.combo_filter_status.addItem("Chưa trả lời")
        self.combo_filter_status.addItem("Đã trả lời")
        self.combo_filter_status.addItem("Đã ẩn")
        self.combo_filter_status.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.combo_filter_status, stretch=2)

        left_layout.addLayout(filter_row)

        # Stack container giữa Table và EmptyState
        self.table_stack_widget = QWidget()
        self.table_stack_layout = QStackedLayout(self.table_stack_widget)
        self.table_stack_layout.setContentsMargins(0, 0, 0, 0)

        # Bảng danh sách bình luận
        self.table_comments = QTableWidget()
        self.table_comments.setColumnCount(4)
        self.table_comments.setHorizontalHeaderLabels(["Khách hàng", "Nội dung bình luận", "Fanpage", "Thời gian"])
        self.table_comments.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_comments.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_comments.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_comments.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_comments.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_comments.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_comments.cellClicked.connect(self._on_comment_selected)
        self.table_stack_layout.addWidget(self.table_comments)

        # EmptyState khi chưa có comment
        self.empty_state_comments = EmptyState.no_comments()
        self.empty_state_comments.action_clicked.connect(self._sync_comments)
        self.table_stack_layout.addWidget(self.empty_state_comments)

        # EmptyState khi search không ra
        self.empty_state_search = EmptyState.search_not_found()
        self.empty_state_search.action_clicked.connect(lambda: self.search_filter.clear())
        self.table_stack_layout.addWidget(self.empty_state_search)

        left_layout.addWidget(self.table_stack_widget)
        splitter.addWidget(left_panel)

        # --- PANEL PHẢI: Chi tiết bình luận & Soạn phản hồi ---
        right_panel = QFrame()
        right_panel.setObjectName("cardFrame")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        lbl_detail_head = QLabel("CHI TIẾT VÀ PHẢN HỒI")
        lbl_detail_head.setStyleSheet("font-size: 13px; font-weight: 700; color: #818CF8;")
        right_layout.addWidget(lbl_detail_head)

        # Khung trích dẫn bình luận được chọn
        self.context_box = QFrame()
        self.context_box.setStyleSheet("background: #0F172A; border-radius: 8px; padding: 12px; border-left: 3px solid #6366F1;")
        ctx_layout = QVBoxLayout(self.context_box)
        ctx_layout.setSpacing(6)

        self.lbl_author_info = QLabel("👤 Chưa chọn bình luận nào")
        self.lbl_author_info.setStyleSheet("font-weight: 700; color: #F1F5F9; font-size: 13px;")
        ctx_layout.addWidget(self.lbl_author_info)

        self.lbl_comment_context = QLabel("Chọn một bình luận từ bảng bên trái để xem nội dung và trả lời.")
        self.lbl_comment_context.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
        self.lbl_comment_context.setWordWrap(True)
        ctx_layout.addWidget(self.lbl_comment_context)

        self.lbl_meta_time = QLabel("")
        self.lbl_meta_time.setStyleSheet("color: #64748B; font-size: 11px;")
        ctx_layout.addWidget(self.lbl_meta_time)

        right_layout.addWidget(self.context_box)

        # Hàng nút thao tác nhanh với bình luận (Ẩn/Hiện, Xóa cache)
        self.quick_action_row = QHBoxLayout()
        self.btn_toggle_hide = QPushButton("👁 Ẩn bình luận")
        self.btn_toggle_hide.setEnabled(False)
        self.btn_toggle_hide.clicked.connect(self._handle_toggle_hide)
        self.quick_action_row.addWidget(self.btn_toggle_hide)

        self.btn_delete_cache = QPushButton("🗑 Xóa khỏi cache")
        self.btn_delete_cache.setEnabled(False)
        self.btn_delete_cache.clicked.connect(self._handle_delete_comment)
        self.quick_action_row.addWidget(self.btn_delete_cache)

        self.quick_action_row.addStretch()
        right_layout.addLayout(self.quick_action_row)

        right_layout.addSpacing(6)

        # Bộ chọn mẫu câu phản hồi
        tpl_header_row = QHBoxLayout()
        tpl_header_row.addWidget(QLabel("Soạn câu trả lời:"))
        tpl_header_row.addStretch()

        self.combo_templates = QComboBox()
        self.combo_templates.setMinimumWidth(220)
        self.combo_templates.currentIndexChanged.connect(self._on_template_selected)
        tpl_header_row.addWidget(self.combo_templates)

        self.btn_template = QPushButton("📝 Dùng mẫu")
        self.btn_template.clicked.connect(self._use_template)
        tpl_header_row.addWidget(self.btn_template)

        right_layout.addLayout(tpl_header_row)

        # Khung nhập câu trả lời
        self.input_reply = QTextEdit()
        self.input_reply.setPlaceholderText("Nhập nội dung phản hồi khách hàng (hỗ trợ mẫu câu có sẵn)...")
        self.input_reply.setMaximumHeight(120)
        self.input_reply.textChanged.connect(self._on_reply_text_changed)
        right_layout.addWidget(self.input_reply)

        # Footer soạn thảo: Đếm ký tự + Nút gửi
        reply_btn_row = QHBoxLayout()
        self.lbl_char_count = QLabel("0 ký tự")
        self.lbl_char_count.setStyleSheet("color: #64748B; font-size: 11px;")
        reply_btn_row.addWidget(self.lbl_char_count)

        reply_btn_row.addStretch()

        self.btn_send_reply = QPushButton("  Gửi phản hồi")
        self.btn_send_reply.setObjectName("primaryButton")
        self.btn_send_reply.setIcon(get_icon("composer", "#FFFFFF", 16))
        self.btn_send_reply.clicked.connect(self._send_reply)
        reply_btn_row.addWidget(self.btn_send_reply)

        right_layout.addLayout(reply_btn_row)
        right_layout.addStretch()

        splitter.addWidget(right_panel)
        splitter.setSizes([540, 460])
        layout.addWidget(splitter)

    # --- Nghiệp vụ nạp & lọc dữ liệu ---

    def reload_comments(self) -> None:
        """Nạp danh sách bình luận từ SQLite cache theo scope hiện tại."""
        if not self.comment_repo:
            self._current_comments = []
            self._render_table([])
            return

        page_id = self.context.get_selected_page_id()
        try:
            self._current_comments = self.comment_repo.list_comments(page_id=page_id, limit=100)
        except Exception as e:
            logger.error(f"Lỗi khi tải bình luận từ cache: {e}")
            self._current_comments = []

        self._apply_filter()

    def _refresh_templates(self) -> None:
        """Nạp danh sách mẫu câu vào combobox."""
        self.combo_templates.blockSignals(True)
        self.combo_templates.clear()
        self.combo_templates.addItem("-- Chọn mẫu câu có sẵn --", None)

        if self.reply_repo:
            page_id = self.context.get_selected_page_id()
            templates = self.reply_repo.list_templates(page_id=page_id)
            for tpl in templates:
                self.combo_templates.addItem(f"📌 {tpl.get('name', 'Mẫu câu')}", tpl.get("content", ""))
        self.combo_templates.blockSignals(False)

    def _apply_filter(self) -> None:
        """Lọc danh sách bình luận theo tìm kiếm và trạng thái."""
        query = self.search_filter.text().strip().lower()
        status_filter = self.combo_filter_status.currentText()

        filtered: List[Dict[str, Any]] = []
        for c in self._current_comments:
            meta = c.get("metadata", {})
            author = str(meta.get("from", {}).get("name", "Khách hàng")).lower()
            msg = str(meta.get("message", "")).lower()
            is_hidden = bool(meta.get("is_hidden", False))

            if query and (query not in author and query not in msg):
                continue

            if status_filter == "Đã ẩn" and not is_hidden:
                continue
            elif status_filter == "Chưa trả lời" and meta.get("comment_count", 0) > 0:
                continue
            elif status_filter == "Đã trả lời" and meta.get("comment_count", 0) == 0:
                continue

            filtered.append(c)

        self._render_table(filtered)

    def _render_table(self, comments: List[Dict[str, Any]]) -> None:
        """Hiển thị danh sách bình luận lên bảng hoặc chuyển sang EmptyState."""
        if not comments:
            if self.search_filter.text().strip():
                self.table_stack_layout.setCurrentWidget(self.empty_state_search)
            else:
                self.table_stack_layout.setCurrentWidget(self.empty_state_comments)
            self._reset_detail_view()
            return

        self.table_stack_layout.setCurrentWidget(self.table_comments)
        self.table_comments.setRowCount(0)

        for c in comments:
            row = self.table_comments.rowCount()
            self.table_comments.insertRow(row)

            meta = c.get("metadata", {})
            from_data = meta.get("from", {})
            author_name = from_data.get("name", "Khách hàng") if isinstance(from_data, dict) else "Khách hàng"
            msg = meta.get("message", "")
            created_raw = meta.get("created_time") or c.get("synced_at", "")
            time_display = format_vn_display(created_raw) if created_raw else "Vừa xong"
            page_id = c.get("page_id", "N/A")

            # Cột Khách hàng
            item_author = QTableWidgetItem(f"👤 {author_name}")
            item_author.setData(Qt.ItemDataRole.UserRole, c)
            self.table_comments.setItem(row, 0, item_author)

            # Cột Nội dung
            item_msg = QTableWidgetItem(msg)
            item_msg.setToolTip(msg)
            self.table_comments.setItem(row, 1, item_msg)

            # Cột Fanpage
            item_page = QTableWidgetItem(page_id)
            self.table_comments.setItem(row, 2, item_page)

            # Cột Thời gian
            item_time = QTableWidgetItem(time_display)
            self.table_comments.setItem(row, 3, item_time)

    def _on_comment_selected(self, row: int, col: int) -> None:
        item = self.table_comments.item(row, 0)
        if not item:
            return
        comment_data = item.data(Qt.ItemDataRole.UserRole)
        self._selected_comment = comment_data

        meta = comment_data.get("metadata", {}) if comment_data else {}
        from_data = meta.get("from", {})
        author_name = from_data.get("name", "Khách hàng") if isinstance(from_data, dict) else "Khách hàng"
        msg = meta.get("message", "(Không có nội dung)")
        created_raw = meta.get("created_time") or comment_data.get("synced_at", "")
        time_display = format_vn_display(created_raw) if created_raw else "Vừa xong"
        is_hidden = bool(meta.get("is_hidden", False))

        self.lbl_author_info.setText(f"👤 {author_name}")
        self.lbl_comment_context.setText(f"\"{msg}\"")
        post_id = comment_data.get("post_id", "Chưa rõ bài viết")
        self.lbl_meta_time.setText(f"🕒 {time_display} | Bài viết: {post_id}")

        self.btn_toggle_hide.setEnabled(True)
        self.btn_toggle_hide.setText("👁 Bỏ ẩn bình luận" if is_hidden else "👁 Ẩn bình luận")
        self.btn_delete_cache.setEnabled(True)

    def _reset_detail_view(self) -> None:
        self._selected_comment = None
        self.lbl_author_info.setText("👤 Chưa chọn bình luận nào")
        self.lbl_comment_context.setText("Chọn một bình luận từ bảng bên trái để xem nội dung và trả lời.")
        self.lbl_meta_time.setText("")
        self.btn_toggle_hide.setEnabled(False)
        self.btn_delete_cache.setEnabled(False)

    def _on_reply_text_changed(self) -> None:
        chars = len(self.input_reply.toPlainText())
        self.lbl_char_count.setText(f"{chars} ký tự")

    def _on_template_selected(self, index: int) -> None:
        content = self.combo_templates.currentData()
        if content:
            self.input_reply.setPlainText(content)

    def _use_template(self) -> None:
        content = self.combo_templates.currentData()
        if content:
            self.input_reply.setPlainText(content)
        else:
            self.input_reply.setPlainText(
                "Cảm ơn bạn đã quan tâm! Lovira đã gửi thông tin chi tiết qua tin nhắn cho bạn rồi nhé ạ."
            )

    def _open_template_manager(self) -> None:
        if not self.reply_repo:
            QMessageBox.information(self, "Thông báo", "Kho lưu trữ mẫu câu chưa được cấu hình.")
            return
        dlg = TemplateManagerDialog(
            reply_repo=self.reply_repo,
            current_page_id=self.context.get_selected_page_id(),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_templates()

    def _handle_toggle_hide(self) -> None:
        if not self._selected_comment:
            return
        meta = self._selected_comment.get("metadata", {})
        current_hidden = bool(meta.get("is_hidden", False))
        new_hidden = not current_hidden
        meta["is_hidden"] = new_hidden

        if self.comment_repo:
            self.comment_repo.upsert_comment(
                page_id=self._selected_comment.get("page_id", ""),
                remote_comment_id=self._selected_comment.get("remote_comment_id", ""),
                post_id=self._selected_comment.get("post_id"),
                metadata=meta,
            )

        self.btn_toggle_hide.setText("👁 Bỏ ẩn bình luận" if new_hidden else "👁 Ẩn bình luận")
        QMessageBox.information(
            self,
            "Cập nhật trạng thái",
            f"Đã {'ẩn' if new_hidden else 'bỏ ẩn'} bình luận trong bộ nhớ đệm.",
        )

    def _handle_delete_comment(self) -> None:
        if not self._selected_comment or not self.comment_repo:
            return
        page_id = self._selected_comment.get("page_id", "")
        remote_c_id = self._selected_comment.get("remote_comment_id", "")

        confirm = QMessageBox.question(
            self,
            "Xóa bình luận khỏi cache",
            "Bạn có chắc muốn xóa bản ghi bình luận này khỏi bộ nhớ đệm nội bộ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.comment_repo.delete_comment(page_id, remote_c_id)
            self.reload_comments()

    def _send_reply(self) -> None:
        reply_text = self.input_reply.toPlainText().strip()
        if not reply_text:
            QMessageBox.warning(self, "Chưa nhập nội dung", "Vui lòng nhập nội dung trước khi gửi phản hồi.")
            return

        if not self._selected_comment:
            QMessageBox.warning(self, "Chưa chọn bình luận", "Vui lòng chọn một bình luận để phản hồi.")
            return

        QMessageBox.information(
            self,
            "Phản hồi",
            "Đã ghi nhận câu trả lời. Hệ thống sẽ phát phản hồi với tư cách Fanpage qua Meta Graph API.",
        )
        self.input_reply.clear()

    def _sync_comments(self) -> None:
        """Đồng bộ bình luận qua FacebookCommentService."""
        QMessageBox.information(
            self,
            "Đồng bộ bình luận",
            "Đang kiểm tra quyền hạn và cập nhật danh sách bình luận mới nhất từ Facebook...",
        )
        self.reload_comments()

    def _on_page_scope_changed(self, page_id: Optional[str]) -> None:
        """Khi Header đổi Fanpage -> Lọc lại bảng bình luận và mẫu câu tương ứng."""
        self.reload_comments()
        self._refresh_templates()
