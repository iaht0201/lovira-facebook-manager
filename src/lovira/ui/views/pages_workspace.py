"""
Lovira Workspace 2.0 — Fanpage Workspace (pages_workspace.py)
Quản lý Fanpage, Nhóm & Kết nối Facebook Graph API (Mockup 02_fanpage.png):
- Kết nối Fanpage qua 2 luồng: Nhập trực tiếp Page ID + Page Token hoặc Quét từ User Token
- Kiểm toán quyền hạn bảo mật: Phân biệt ready, unverified, insufficient_permissions, token_expired (A-06)
- Bảng Fanpage nâng cao tích hợp StatusChip, sao chép ID nhanh và EmptyState onboarding
- Kiểm tra sức khỏe token trực tiếp (Verify Token Health)
- Cảnh báo an toàn tác động lịch đăng local & remote khi gỡ liên kết (AC-11)
"""

import logging
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QLineEdit,
    QDialog,
    QMessageBox,
    QFrame,
    QTabWidget,
    QStackedLayout,
)
from src.lovira.storage.page_repository import PageRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.feedback import FeedbackBanner
from src.lovira.domain.timezone import format_vn_display

logger = logging.getLogger(__name__)


class ConnectPageDialog(QDialog):
    """Hộp thoại kết nối Fanpage mới (Hỗ trợ 2 Tab: Page ID + Token hoặc Quét tự động)."""

    def __init__(self, fb_client: FacebookGraphClient, page_repo: PageRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.fb = fb_client
        self.repo = page_repo
        self.setWindowTitle("Kết nối Fanpage mới — Lovira Workspace 2.0")
        self.setFixedWidth(560)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # Header Dialog
        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("pages", "#6258E8", 22).pixmap(22, 22))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("KẾT NỐI FANPAGE FACEBOOK")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #F3F6FC; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        desc_lbl = QLabel("Liên kết Fanpage để thực hiện soạn bài, lập lịch đăng Reels và quản lý tương tác tự động.")
        desc_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Tab Widget cho 2 phương thức kết nối
        self.tab_widget = QTabWidget()

        # TAB 1: Nhập trực tiếp Page ID & Page Access Token
        tab_page_id = QWidget()
        page_id_layout = QVBoxLayout(tab_page_id)
        page_id_layout.setContentsMargins(14, 14, 14, 14)
        page_id_layout.setSpacing(10)

        desc1 = QLabel(
            "Phương thức khuyến nghị khi bạn đã có Page ID và Page Access Token vĩnh viễn (System User hoặc Page Token)."
        )
        desc1.setStyleSheet("color: #A9B8CF; font-size: 11px;")
        desc1.setWordWrap(True)
        page_id_layout.addWidget(desc1)

        page_id_layout.addWidget(QLabel("Facebook Page ID (Bắt buộc):"))
        self.input_page_id = QLineEdit()
        self.input_page_id.setPlaceholderText("Ví dụ: 100085942398412 hoặc ID số của Fanpage...")
        page_id_layout.addWidget(self.input_page_id)

        page_id_layout.addWidget(QLabel("Tên Fanpage (Gợi nhớ, tùy chọn):"))
        self.input_page_name = QLineEdit()
        self.input_page_name.setPlaceholderText("Ví dụ: Lovira Official, Shop Mỹ Phẩm...")
        page_id_layout.addWidget(self.input_page_name)

        page_id_layout.addWidget(QLabel("Page Access Token (Bắt đầu bằng EAA...):"))
        self.input_page_token = QLineEdit()
        self.input_page_token.setPlaceholderText("Dán mã Page Access Token vào đây...")
        page_id_layout.addWidget(self.input_page_token)

        self.tab_widget.addTab(tab_page_id, "📌 Nhập Page ID & Token")

        # TAB 2: Quét tự động từ User Access Token
        tab_user_token = QWidget()
        user_layout = QVBoxLayout(tab_user_token)
        user_layout.setContentsMargins(14, 14, 14, 14)
        user_layout.setSpacing(10)

        desc2 = QLabel(
            "Dán mã User Access Token (cấp quyền quản lý Fanpage).\n"
            "Hệ thống sẽ tự động quét toàn bộ danh sách các Fanpage thuộc quyền quản lý của bạn."
        )
        desc2.setStyleSheet("color: #A9B8CF; font-size: 11px;")
        desc2.setWordWrap(True)
        user_layout.addWidget(desc2)

        user_layout.addWidget(QLabel("User Access Token (Bắt đầu bằng EAA...):"))
        self.input_user_token = QLineEdit()
        self.input_user_token.setPlaceholderText("Dán mã User Access Token vào đây...")
        user_layout.addWidget(self.input_user_token)
        user_layout.addStretch()

        # Alias tương thích ngược
        self.token_input = self.input_user_token

        self.tab_widget.addTab(tab_user_token, "🔍 Quét tự động từ User Token")
        layout.addWidget(self.tab_widget)

        # Nút điều khiển
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_connect = QPushButton("Xác thực và Kết nối")
        self.btn_connect.setObjectName("primaryButton")
        self.btn_connect.clicked.connect(self._handle_connect)

        btn_row.addStretch()
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_connect)
        layout.addLayout(btn_row)

    def _handle_connect(self) -> None:
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 0 and not self.input_page_id.text().strip() and self.input_user_token.text().strip():
            current_tab = 1

        if current_tab == 0:
            # Tab 1: Kết nối bằng Page ID + Page Token
            page_id = self.input_page_id.text().strip()
            token = self.input_page_token.text().strip()
            custom_name = self.input_page_name.text().strip()

            if not page_id or not token:
                QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ Facebook Page ID và Page Access Token.")
                return

            self.btn_connect.setEnabled(False)
            self.btn_connect.setText("Đang kết nối...")

            # Thử inspect token qua Graph API (UX-01 P0 safety check)
            token_info = self.fb.inspect_token(token)
            resolved_name = custom_name or f"Fanpage {page_id}"

            if token_info and token_info.is_valid:
                if token_info.name:
                    resolved_name = custom_name or token_info.name
                tasks = token_info.tasks if token_info.tasks else ["MANAGE", "CREATE_CONTENT"]
                has_publish_perm = any(t in ["CREATE_CONTENT", "MANAGE", "PUBLISH_TO_PAGE"] for t in tasks)
                status = "ready" if has_publish_perm else "insufficient_permissions"

                pid = self.repo.upsert_page(
                    facebook_page_id=page_id,
                    name=resolved_name,
                    status=status,
                )
                self.repo.save_page_token(pid, token, tasks=tasks)

                if status == "ready":
                    QMessageBox.information(
                        self,
                        "Kết nối thành công",
                        f"Đã xác thực và liên kết Fanpage thành công!\n• Tên Page: {resolved_name}\n• Page ID: {page_id}\n• Trạng thái: Sẵn sàng",
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Thiếu quyền đăng bài",
                        f"Đã lưu Fanpage nhưng Access Token thiếu quyền tạo nội dung (CREATE_CONTENT).\n• Tên Page: {resolved_name}\n• Trạng thái: Thiếu quyền",
                    )
                self.accept()
            else:
                # Không xác thực được hoặc token không hợp lệ -> CẤM lưu status='ready' (A-06)
                pid = self.repo.upsert_page(
                    facebook_page_id=page_id,
                    name=resolved_name,
                    status="unverified",
                )
                self.repo.save_page_token(pid, token, tasks=[])
                QMessageBox.warning(
                    self,
                    "Chưa xác thực được Token",
                    f"Không thể xác thực Access Token với Facebook (lỗi mạng hoặc token không hợp lệ).\n"
                    f"Fanpage được lưu ở trạng thái 'Chưa xác minh' (unverified) và KHÔNG THỂ đăng bài cho đến khi kết nối lại thành công.",
                )
                self.accept()

        else:
            # Tab 2: Quét tự động từ User Token
            user_token = self.input_user_token.text().strip()
            if not user_token:
                QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập User Access Token.")
                return

            self.btn_connect.setEnabled(False)
            self.btn_connect.setText("Đang quét Fanpage...")

            token_info = self.fb.inspect_token(user_token)
            if token_info and token_info.is_valid:
                if token_info.token_type == "PAGE":
                    pid = self.repo.upsert_page(
                        facebook_page_id=token_info.id,
                        name=token_info.name,
                        status="ready",
                    )
                    self.repo.save_page_token(pid, user_token, tasks=token_info.tasks)
                    QMessageBox.information(
                        self,
                        "Kết nối thành công",
                        f"Đã kết nối trực tiếp Page Token thành công!\n• Tên Page: {token_info.name}\n• ID: {token_info.id}",
                    )
                    self.accept()
                    return

                elif token_info.token_type == "USER" and token_info.pages:
                    added_count = 0
                    for p in token_info.pages:
                        pid = self.repo.upsert_page(
                            facebook_page_id=p.page_id,
                            name=p.name,
                            status="ready",
                        )
                        if p.access_token:
                            self.repo.save_page_token(pid, p.access_token, tasks=p.tasks)
                        added_count += 1

                    QMessageBox.information(
                        self,
                        "Kết nối thành công",
                        f"Đã kết nối tài khoản Facebook {token_info.name} thành công!\n• Đã tìm thấy và liên kết {added_count} Fanpage.",
                    )
                    self.accept()
                    return

            self.btn_connect.setEnabled(True)
            self.btn_connect.setText("Xác thực và Kết nối")
            QMessageBox.critical(
                self,
                "Kết nối thất bại (AC-20)",
                "Mã Access Token không hợp lệ hoặc không có quyền quản lý Fanpage nào.\nVui lòng kiểm tra lại token hoặc chuyển sang Tab 'Nhập Page ID và Token'.",
            )


class PagesWorkspaceView(QWidget):
    """Màn hình Quản lý Fanpage 2.0 (Workspace)."""

    page_list_changed = Signal()
    bulk_import_requested = Signal()

    def __init__(
        self,
        page_repo: PageRepository,
        fb_client: FacebookGraphClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.repo = page_repo
        self.fb = fb_client
        self._all_pages: List[Dict[str, Any]] = []

        self._init_ui()
        self.reload_pages()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # 1. Header Toolbar
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title_lbl = QLabel("QUẢN LÝ FANPAGE FACEBOOK")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #F3F6FC;")

        self.lbl_subtitle = QLabel("Quản lý danh sách kết nối, trạng thái token và quyền đăng bài")
        self.lbl_subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        header_box.addWidget(title_lbl)
        header_box.addWidget(self.lbl_subtitle)
        header_row.addLayout(header_box)

        header_row.addStretch()

        self.btn_refresh = QPushButton(" Làm mới")
        self.btn_refresh.setIcon(get_icon("refresh_cw", "#A9B8CF", 14))
        self.btn_refresh.clicked.connect(self.reload_pages)
        header_row.addWidget(self.btn_refresh)

        self.btn_bulk_import = QPushButton(" Nhập Excel / CSV")
        self.btn_bulk_import.setObjectName("successButton")
        self.btn_bulk_import.setIcon(get_icon("bulk_import", "#FFFFFF", 15))
        self.btn_bulk_import.clicked.connect(self.bulk_import_requested.emit)
        header_row.addWidget(self.btn_bulk_import)

        self.btn_add_page = QPushButton(" Kết nối Fanpage mới")
        self.btn_add_page.setObjectName("primaryButton")
        self.btn_add_page.setIcon(get_icon("plus", "#FFFFFF", 16))
        self.btn_add_page.clicked.connect(self._open_connect_dialog)
        header_row.addWidget(self.btn_add_page)

        layout.addLayout(header_row)

        # 2. Bộ lọc & Tìm kiếm nhanh
        filter_frame = QFrame()
        filter_frame.setObjectName("cardFrame")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)

        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("🔍 Tìm theo tên Fanpage hoặc Facebook Page ID...")
        self.search_filter.textChanged.connect(self._apply_table_filter)
        filter_layout.addWidget(self.search_filter, stretch=1)

        layout.addWidget(filter_frame)

        # 3. Vùng danh sách: QStackedLayout giữa Bảng và EmptyState
        self.content_stack = QStackedLayout()

        # View 1: Bảng danh sách Fanpage
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(10)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Facebook Page ID", "Tên Fanpage", "Trạng thái", "Xác thực Token", "Ngày cập nhật"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(42)
        table_layout.addWidget(self.table)

        # Thanh nút hành động cho hàng được chọn
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        self.btn_verify_token = QPushButton("🔍 Kiểm tra lại Token")
        self.btn_verify_token.clicked.connect(self._handle_verify_selected_token)
        action_bar.addWidget(self.btn_verify_token)

        action_bar.addStretch()

        self.btn_unlink_page = QPushButton("🗑 Gỡ liên kết Fanpage")
        self.btn_unlink_page.setObjectName("dangerButton")
        self.btn_unlink_page.clicked.connect(self._handle_unlink_page)
        action_bar.addWidget(self.btn_unlink_page)

        table_layout.addLayout(action_bar)
        self.content_stack.addWidget(table_container)

        # View 2: EmptyState Container
        self.empty_container = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_container)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_state = EmptyState.no_pages(on_add=self._open_connect_dialog)
        self.empty_layout.addWidget(self.empty_state)
        self.content_stack.addWidget(self.empty_container)

        layout.addLayout(self.content_stack, stretch=1)

    def reload_pages(self) -> None:
        """Tải lại danh sách Fanpage từ database."""
        self._all_pages = self.repo.list_pages()
        self._apply_table_filter()

    def _apply_table_filter(self) -> None:
        """Lọc và cập nhật dữ liệu bảng."""
        query = self.search_filter.text().strip().lower()

        filtered_pages = []
        for p in self._all_pages:
            name = (p.get("name") or "").lower()
            fbid = (p.get("facebook_page_id") or "").lower()
            if not query or query in name or query in fbid:
                filtered_pages.append(p)

        # Cập nhật số lượng trên subtitle
        ready_count = sum(1 for p in self._all_pages if p.get("status") == "ready")
        self.lbl_subtitle.setText(
            f"Tổng cộng {len(self._all_pages)} Fanpage | {ready_count} sẵn sàng đăng bài"
        )

        if not self._all_pages:
            self.content_stack.setCurrentIndex(1)
            return

        self.content_stack.setCurrentIndex(0)
        self.table.setRowCount(len(filtered_pages))

        for row, p in enumerate(filtered_pages):
            # Cột 0: Facebook Page ID — lưu internal_id vào UserRole để lookup
            fb_pid = p["facebook_page_id"]
            item_fb = QTableWidgetItem(fb_pid)
            item_fb.setData(Qt.ItemDataRole.UserRole, p["id"])  # ID nội bộ ẩn
            self.table.setItem(row, 0, item_fb)

            # Cột 1: Tên Fanpage
            self.table.setItem(row, 1, QTableWidgetItem(p["name"]))

            # Cột 2: Trạng thái (Chip hiện đại)
            status_key = p.get("status", "unknown")
            self.table.setItem(row, 2, QTableWidgetItem(status_key))
            chip = StatusChip(status_key)
            self.table.setCellWidget(row, 2, chip)

            # Cột 3: Xác thực token — có thể đăng bài?
            PUBLISH_READY = {"ready"}
            NEEDS_RECONNECT = {"token_expired", "insufficient_permissions"}
            if status_key in PUBLISH_READY:
                auth_text = "✅ Sẵn sàng đăng bài"
            elif status_key in NEEDS_RECONNECT:
                auth_text = "⚠️ Cần kết nối lại"
            elif status_key == "unverified":
                auth_text = "❓ Chưa xác minh"
            else:
                auth_text = "❓ Chưa biết"
            self.table.setItem(row, 3, QTableWidgetItem(auth_text))

            # Cột 4: Ngày cập nhật
            raw_updated = p.get("updated_at", "")
            disp_updated = format_vn_display(raw_updated) if raw_updated else ""
            self.table.setItem(row, 4, QTableWidgetItem(disp_updated or raw_updated))

    def _open_connect_dialog(self) -> None:
        dlg = ConnectPageDialog(self.fb, self.repo, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload_pages()
            self.page_list_changed.emit()

    def _get_selected_page_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, 0)
        # Lấy internal ID từ UserRole (không hiển thị trên bảng)
        if item:
            internal_id = item.data(Qt.ItemDataRole.UserRole)
            return internal_id if internal_id else item.text()
        return None

    def _handle_verify_selected_token(self) -> None:
        """Kiểm tra sức khỏe Access Token của Fanpage được chọn."""
        page_id = self._get_selected_page_id()
        if not page_id:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Vui lòng chọn Fanpage trong bảng để kiểm tra lại token.")
            return

        page = self.repo.get_page(page_id)
        if not page:
            return

        token = self.repo.get_page_token(page_id)
        if not token:
            QMessageBox.warning(self, "Không tìm thấy Token", f"Fanpage '{page['name']}' chưa có mã Access Token lưu trong Vault.")
            return

        token_info = self.fb.inspect_token(token)
        if token_info and token_info.is_valid:
            tasks = token_info.tasks if token_info.tasks else ["MANAGE", "CREATE_CONTENT"]
            has_publish_perm = any(t in ["CREATE_CONTENT", "MANAGE", "PUBLISH_TO_PAGE"] for t in tasks)
            new_status = "ready" if has_publish_perm else "insufficient_permissions"

            self.repo.update_page_status(page_id, new_status)
            self.reload_pages()
            self.page_list_changed.emit()

            if new_status == "ready":
                QMessageBox.information(self, "Token hợp lệ", f"Access Token của '{page['name']}' đang hoạt động tốt (Sẵn sàng đăng bài).")
            else:
                QMessageBox.warning(self, "Thiếu quyền", f"Access Token của '{page['name']}' còn sống nhưng thiếu quyền CREATE_CONTENT.")
        else:
            self.repo.update_page_status(page_id, "token_expired")
            self.reload_pages()
            self.page_list_changed.emit()
            QMessageBox.critical(self, "Token hết hạn", f"Access Token của '{page['name']}' đã hết hạn hoặc bị hủy quyền. Vui lòng cấp lại.")

    def _handle_unlink_page(self) -> None:
        """AC-11: Cảnh báo số lượng lịch local và remote khi gỡ liên kết Page."""
        page_id = self._get_selected_page_id()
        if not page_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn Fanpage cần gỡ liên kết.")
            return

        page = self.repo.get_page(page_id)
        page_name = page["name"] if page else page_id

        # Kiểm tra lịch chờ
        sched = self.repo.check_page_schedules(page_id)
        local_count = sched["local_count"]
        remote_count = sched["remote_count"]

        warn_msg = f"Bạn có chắc chắn muốn gỡ liên kết Fanpage '{page_name}' khỏi Lovira không?\n(Lưu ý: Fanpage thật trên Facebook KHÔNG bị xóa).\n\n"
        if local_count > 0 or remote_count > 0:
            warn_msg += (
                f"⚠️ CẢNH BÁO LỊCH ĐĂNG (AC-11):\n"
                f"• {local_count} lịch hẹn giờ trên máy chưa thực hiện sẽ bị hủy.\n"
                f"• {remote_count} lịch Facebook đã nhận vẫn tồn tại trên hệ thống Facebook.\n\n"
                "Bạn có muốn tiếp tục gỡ Fanpage này không?"
            )
        else:
            warn_msg += "Fanpage này hiện không có lịch hẹn giờ nào đang chờ."

        reply = QMessageBox.question(
            self,
            "Xác nhận gỡ Fanpage (AC-11)",
            warn_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.repo.unlink_page(page_id, force=True)
            if success:
                QMessageBox.information(self, "Thành công", f"Đã gỡ liên kết Fanpage '{page_name}'.")
                self.reload_pages()
                self.page_list_changed.emit()
            else:
                QMessageBox.critical(self, "Lỗi gỡ Page", msg)
