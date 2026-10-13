"""
Lovira-Facebook Manager
Màn hình Quản lý Fanpage & Nội dung (PagesWorkspaceView)
- Quản lý danh sách Fanpage và phân nhóm (BR-03, Section 5.2)
- Kết nối Fanpage qua Access Token (User Token / Page Token) (AC-02, AC-03)
- Gỡ liên kết Fanpage kèm kiểm tra cảnh báo lịch local & remote (AC-11)
- Hiển thị trạng thái kết nối rõ ràng (Sẵn sàng, Hết hạn token, Thiếu quyền) (AC-20)
"""

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
    QComboBox,
)
from src.lovira.storage.page_repository import PageRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient

logger = logging.getLogger(__name__) if "logging" in globals() else None


class ConnectPageDialog(QDialog):
    """Hộp thoại thêm và kết nối Fanpage mới (Hỗ trợ cả Page ID + Token hoặc Quét tự động)."""

    def __init__(self, fb_client: FacebookGraphClient, page_repo: PageRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.fb = fb_client
        self.repo = page_repo
        self.setWindowTitle("Kết nối Fanpage mới — Facebook Graph API")
        self.setFixedWidth(520)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_lbl = QLabel("KẾT NỐI FANPAGE FACEBOOK")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #818CF8;")
        layout.addWidget(title_lbl)

        # Tab Widget cho 2 phương thức kết nối
        from PySide6.QtWidgets import QTabWidget
        self.tab_widget = QTabWidget()

        # TAB 1: Nhập trực tiếp Page ID & Token (Phổ biến nhất)
        tab_page_id = QWidget()
        page_id_layout = QVBoxLayout(tab_page_id)
        page_id_layout.setSpacing(10)

        desc1 = QLabel(
            "Nhập mã Facebook Page ID và Page Access Token tương ứng.\n"
            "Hệ thống sẽ lưu trữ Fanpage để sẵn sàng soạn bài và đặt lịch."
        )
        desc1.setStyleSheet("color: #94A3B8; font-size: 12px;")
        desc1.setWordWrap(True)
        page_id_layout.addWidget(desc1)

        page_id_layout.addWidget(QLabel("Facebook Page ID (Bắt buộc):"))
        self.input_page_id = QLineEdit()
        self.input_page_id.setPlaceholderText("Ví dụ: 100085942398412 hoặc ID Fanpage của bạn...")
        page_id_layout.addWidget(self.input_page_id)

        page_id_layout.addWidget(QLabel("Tên Fanpage (Tùy chọn gợi nhớ):"))
        self.input_page_name = QLineEdit()
        self.input_page_name.setPlaceholderText("Ví dụ: Lovira Official, Page Bán Hàng...")
        page_id_layout.addWidget(self.input_page_name)

        page_id_layout.addWidget(QLabel("Page Access Token (EAA...):"))
        self.input_page_token = QLineEdit()
        self.input_page_token.setPlaceholderText("Dán mã Page Access Token vào đây...")
        page_id_layout.addWidget(self.input_page_token)

        self.tab_widget.addTab(tab_page_id, "📌 Nhập Page ID và Token")

        # TAB 2: Quét tự động bằng User Access Token
        tab_user_token = QWidget()
        user_layout = QVBoxLayout(tab_user_token)
        user_layout.setSpacing(10)

        desc2 = QLabel(
            "Dán mã User Access Token (cấp quyền quản lý Fanpage).\n"
            "Hệ thống sẽ tự động quét danh sách các Fanpage thuộc quyền quản lý của bạn."
        )
        desc2.setStyleSheet("color: #94A3B8; font-size: 12px;")
        desc2.setWordWrap(True)
        user_layout.addWidget(desc2)

        user_layout.addWidget(QLabel("User Access Token (EAA...):"))
        self.input_user_token = QLineEdit()
        self.input_user_token.setPlaceholderText("Dán mã User Access Token vào đây...")
        user_layout.addWidget(self.input_user_token)
        user_layout.addStretch()

        # Alias tương thích ngược
        self.token_input = self.input_user_token

        self.tab_widget.addTab(tab_user_token, "🔍 Quét tự động từ User Token")

        layout.addWidget(self.tab_widget)

        # Nút điều khiển dưới cùng
        btn_row = QHBoxLayout()
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
                # Không xác thực được hoặc token không hợp lệ -> CẤM lưu status='ready'
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
    """Màn hình Quản lý Fanpage."""

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
        self._init_ui()
        self.reload_pages()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header toolbar
        toolbar = QHBoxLayout()
        title_lbl = QLabel("DANH SÁCH FANPAGE ĐANG QUẢN LÝ")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #818CF8;")
        toolbar.addWidget(title_lbl)

        toolbar.addStretch()

        self.btn_bulk_import = QPushButton("📊 Nhập Excel / CSV")
        self.btn_bulk_import.setObjectName("successButton")
        self.btn_bulk_import.clicked.connect(self.bulk_import_requested.emit)
        toolbar.addWidget(self.btn_bulk_import)

        self.btn_add_page = QPushButton("➕ Kết nối Fanpage mới")
        self.btn_add_page.setObjectName("primaryButton")
        self.btn_add_page.clicked.connect(self._open_connect_dialog)
        toolbar.addWidget(self.btn_add_page)

        self.btn_refresh = QPushButton("🔄 Tải lại")
        self.btn_refresh.clicked.connect(self.reload_pages)
        toolbar.addWidget(self.btn_refresh)

        layout.addLayout(toolbar)

        # Bảng danh sách Fanpage
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID Nội bộ", "Facebook Page ID", "Tên Fanpage", "Trạng thái", "Ngày cập nhật"
        ])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Thao tác gỡ Page
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_unlink_page = QPushButton("🗑 Gỡ liên kết Fanpage")
        self.btn_unlink_page.setObjectName("dangerButton")
        self.btn_unlink_page.clicked.connect(self._handle_unlink_page)
        btn_row.addWidget(self.btn_unlink_page)

        layout.addLayout(btn_row)

    def reload_pages(self) -> None:
        pages = self.repo.list_pages()
        self.table.setRowCount(len(pages))
        for row, p in enumerate(pages):
            self.table.setItem(row, 0, QTableWidgetItem(p["id"]))
            self.table.setItem(row, 1, QTableWidgetItem(p["facebook_page_id"]))
            self.table.setItem(row, 2, QTableWidgetItem(p["name"]))

            status_str = "🟢 Sẵn sàng" if p.get("status") == "ready" else "⚠️ Cần kiểm tra"
            self.table.setItem(row, 3, QTableWidgetItem(status_str))
            self.table.setItem(row, 4, QTableWidgetItem(p.get("updated_at", "")))

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
        return self.table.item(row, 0).text()

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
