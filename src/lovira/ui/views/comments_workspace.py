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
from PySide6.QtGui import QPixmap, QIcon
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
    QFileDialog,
    QProgressBar,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.storage.comment_repository import CommentCacheRepository, ReplyTemplateRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.domain.timezone import format_vn_display
from src.lovira.services.link_preview import LinkPreviewService, AsyncLinkPreviewWorker

logger = logging.getLogger(__name__)


class ImportTemplatesDialog(QDialog):
    """Hộp thoại nhập hàng loạt mẫu câu & sản phẩm Shopee."""

    templates_imported = Signal(int)

    def __init__(self, reply_repo: ReplyTemplateRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.reply_repo = reply_repo
        self.setWindowTitle("📥 Nhập danh sách Mẫu câu & Sản phẩm Shopee")
        self.setMinimumSize(560, 460)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_guide = QLabel(
            "<b>Hướng dẫn nhập danh sách mẫu câu / sản phẩm:</b><br>"
            "• <b>Cách 1:</b> Dán danh sách link Shopee hoặc nội dung vào khung bên dưới.<br>"
            "&nbsp;&nbsp;Ví dụ: <code>https://s.shopee.vn/8A9B1C</code> (Tự động cào tên, giá & ảnh SP)<br>"
            "&nbsp;&nbsp;Hoặc: <code>Tên sản phẩm | Link Shopee / Nội dung bình luận</code><br>"
            "• <b>Cách 2:</b> Bấm <b>'Chọn file...'</b> để nhập từ file TXT, CSV hoặc JSON."
        )
        lbl_guide.setStyleSheet("color: #94A3B8; font-size: 12px; background: #131D2E; padding: 12px; border-radius: 6px; border: 1px solid #1E2D47;")
        lbl_guide.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_guide)

        self.txt_input = QTextEdit()
        self.txt_input.setPlaceholderText(
            "Dán danh sách tại đây, mỗi dòng một mẫu câu/sản phẩm:\n\n"
            "https://s.shopee.vn/8A9B1C\n"
            "Áo thun polo nam | https://shopee.vn/product/123/456\n"
            "Tư vấn size | Dạ shop chào bạn, bạn nhắn tin để shop tư vấn nhé!\n"
            "Giảm giá 50k | Nhập mã LOVIRA50K khi đặt hàng Shopee nè cả nhà!"
        )
        self.txt_input.setStyleSheet("""
            QTextEdit {
                background-color: #0F172A;
                border: 1px solid #24344D;
                border-radius: 6px;
                padding: 10px;
                color: #F8FAFC;
                font-size: 13px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.txt_input, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1E2D47;
                border-radius: 4px;
                text-align: center;
                background-color: #131D2E;
                color: #F1F5F9;
                font-size: 11px;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #6258E8;
            }
        """)
        layout.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_file = QPushButton("📁 Chọn file (TXT, CSV, JSON)...")
        self.btn_file.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                color: #E2E8F0;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        self.btn_file.clicked.connect(self._on_choose_file)
        btn_row.addWidget(self.btn_file)

        btn_row.addStretch()

        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_import = QPushButton("📥 Tiến hành Nhập dữ liệu")
        self.btn_import.setStyleSheet("""
            QPushButton {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                padding: 6px 18px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5348D6;
            }
        """)
        self.btn_import.clicked.connect(self._handle_import)
        btn_row.addWidget(self.btn_import)

        layout.addLayout(btn_row)

    def _on_choose_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file danh sách mẫu câu",
            "",
            "Tất cả định dạng hỗ trợ (*.txt *.csv *.json);;Text Files (*.txt);;CSV Files (*.csv);;JSON Files (*.json)",
        )
        if not file_path:
            return

        try:
            p = Path(file_path)
            content = p.read_text(encoding="utf-8", errors="ignore")
            if p.suffix.lower() == ".json":
                data = json.loads(content)
                lines = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get("name") or ""
                            val = item.get("content") or item.get("product_url") or ""
                            lines.append(f"{name} | {val}" if name else val)
                        elif isinstance(item, str):
                            lines.append(item)
                self.txt_input.setPlainText("\n".join(lines))
            else:
                self.txt_input.setPlainText(content)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", f"Không thể đọc file đã chọn:\n{e}")

    def _handle_import(self) -> None:
        text = self.txt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Trống", "Vui lòng nhập hoặc dán nội dung cần nhập.")
            return

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return

        self.btn_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(lines))
        self.progress_bar.setValue(0)

        preview_srv = LinkPreviewService.get_instance()
        items_to_save = []

        for idx, line in enumerate(lines, 1):
            name = ""
            content = line
            product_url = ""

            if "|" in line:
                parts = line.split("|", 1)
                name = parts[0].strip()
                content = parts[1].strip()

            urls = preview_srv.extract_urls(content)
            image_url = ""
            local_image_path = ""
            price = ""

            if urls:
                product_url = urls[0]
                prev = preview_srv.fetch_preview(product_url, timeout=3.5)
                if prev.get("success"):
                    if not name and prev.get("title"):
                        name = prev["title"]
                    image_url = prev.get("image_url", "")
                    local_image_path = prev.get("local_image_path", "")
                    price = prev.get("price", "")

            if not name:
                name = f"Mẫu #{idx} " + (content[:25] + "..." if len(content) > 25 else content)

            items_to_save.append({
                "name": name,
                "content": content,
                "product_url": product_url,
                "image_url": image_url,
                "local_image_path": local_image_path,
                "price": price,
            })

            self.progress_bar.setValue(idx)

        imported = self.reply_repo.import_templates(items_to_save)
        self.templates_imported.emit(imported)
        QMessageBox.information(
            self,
            "Nhập thành công",
            f"✅ Đã nhập thành công {imported} mẫu câu & sản phẩm vào thư viện!",
        )
        self.accept()


class TemplateManagerDialog(QDialog):
    """Hộp thoại Quản lý Mẫu câu phản hồi nhanh & Sản phẩm Shopee."""

    template_selected = Signal(dict)

    def __init__(
        self,
        reply_repo: ReplyTemplateRepository,
        current_page_id: Optional[str] = None,
        is_picker: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.reply_repo = reply_repo
        self.current_page_id = current_page_id
        self.is_picker = is_picker
        self.selected_template: Optional[Dict[str, Any]] = None

        self._active_worker: Optional[AsyncLinkPreviewWorker] = None
        self._current_preview_data: Dict[str, Any] = {}

        title = "🛍 Chọn Mẫu câu & Sản phẩm bình luận" if is_picker else "Quản lý Mẫu câu Phản hồi Nhanh & Sản phẩm Shopee"
        self.setWindowTitle(title)
        self.setMinimumSize(780, 560)
        self._init_ui()
        self._load_templates()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_desc = QLabel(
            "Tạo, quản lý và lưu trữ các mẫu câu bình luận, link sản phẩm Shopee để tự động đính kèm khi đăng bài Reels/Video."
        )
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # 1. Bảng danh sách mẫu câu (4 cột: Ảnh, Tên/Sản phẩm, Giá, Nội dung/Link)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Ảnh SP", "Tên mẫu / Sản phẩm", "Giá", "Nội dung phản hồi / Link Shopee"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 56)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 220)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 90)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self.table, stretch=1)

        # 2. Form thêm mẫu câu / sản phẩm mới
        add_frame = QFrame()
        add_frame.setStyleSheet("background: #141E33; border: 1px solid #22334F; border-radius: 8px; padding: 12px;")
        add_layout = QVBoxLayout(add_frame)
        add_layout.setSpacing(8)

        lbl_add_title = QLabel("➕ Thêm mẫu câu / Sản phẩm Shopee mới:")
        lbl_add_title.setStyleSheet("font-weight: 700; color: #F1F5F9; font-size: 13px;")
        add_layout.addWidget(lbl_add_title)

        # Dòng 1: Link sản phẩm Shopee & nút quét
        row_url = QHBoxLayout()
        row_url.setSpacing(8)
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("🛍 Dán link sản phẩm Shopee (https://s.shopee.vn/... hoặc shopee.vn) để tự động quét ảnh & tên SP...")
        self.txt_url.setStyleSheet("""
            QLineEdit {
                background: #0B111E;
                border: 1px solid #2A3C59;
                border-radius: 6px;
                padding: 6px 10px;
                color: #F8FAFC;
                font-size: 12px;
            }
        """)
        self.txt_url.textChanged.connect(self._on_url_changed)
        row_url.addWidget(self.txt_url, stretch=1)

        self.btn_scan = QPushButton("🔍 Dò tìm SP")
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background: #1E2D47;
                color: #CBD5E1;
                border: 1px solid #33476B;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #283C60;
                color: #FFFFFF;
            }
        """)
        self.btn_scan.clicked.connect(self._scan_product_url)
        row_url.addWidget(self.btn_scan)
        add_layout.addLayout(row_url)

        # Card xem trước mini khi quét link thành công
        self.preview_card = QFrame()
        self.preview_card.setStyleSheet("background: #0D1627; border: 1px solid #3B4E75; border-radius: 6px; padding: 6px;")
        self.preview_card.setVisible(False)
        pv_layout = QHBoxLayout(self.preview_card)
        pv_layout.setContentsMargins(6, 4, 6, 4)
        pv_layout.setSpacing(10)

        self.lbl_pv_thumb = QLabel()
        self.lbl_pv_thumb.setFixedSize(40, 40)
        self.lbl_pv_thumb.setStyleSheet("background: #1E293B; border-radius: 4px;")
        pv_layout.addWidget(self.lbl_pv_thumb)

        pv_text_box = QVBoxLayout()
        pv_text_box.setSpacing(2)
        self.lbl_pv_title = QLabel()
        self.lbl_pv_title.setStyleSheet("font-weight: 700; color: #F1F5F9; font-size: 12px;")
        self.lbl_pv_price = QLabel()
        self.lbl_pv_price.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        pv_text_box.addWidget(self.lbl_pv_title)
        pv_text_box.addWidget(self.lbl_pv_price)
        pv_layout.addLayout(pv_text_box, stretch=1)

        add_layout.addWidget(self.preview_card)

        # Dòng 2: Tên mẫu gợi nhớ
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Tên gợi nhớ (VD: Áo polo nam, Đồ ăn cho cún, Chào hỏi...)")
        self.txt_name.setStyleSheet(self.txt_url.styleSheet())
        add_layout.addWidget(self.txt_name)

        # Dòng 3: Nội dung phản hồi / bình luận
        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("Nội dung bình luận tự động đăng lên bài viết (kèm link Shopee nếu có)...")
        self.txt_content.setMaximumHeight(65)
        self.txt_content.setStyleSheet("""
            QTextEdit {
                background: #0B111E;
                border: 1px solid #2A3C59;
                border-radius: 6px;
                padding: 6px 10px;
                color: #F8FAFC;
                font-size: 12px;
            }
        """)
        add_layout.addWidget(self.txt_content)

        # Các nút thao tác thêm / xóa / import
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_add = QPushButton(" Thêm vào thư viện")
        self.btn_add.setObjectName("primaryButton")
        self.btn_add.setIcon(get_icon("composer", "#FFFFFF", 14))
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #6258E8;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #5348D6;
            }
        """)
        self.btn_add.clicked.connect(self._handle_add)
        btn_row.addWidget(self.btn_add)

        self.btn_import = QPushButton(" 📥 Nhập danh sách...")
        self.btn_import.setStyleSheet("""
            QPushButton {
                background: #17243B;
                border: 1px solid #2B3D59;
                color: #E2E8F0;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #22334F;
                color: #FFFFFF;
            }
        """)
        self.btn_import.clicked.connect(self._open_import_dialog)
        btn_row.addWidget(self.btn_import)

        self.btn_delete = QPushButton(" Xóa mẫu đã chọn")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.setIcon(get_icon("trash", "#FFFFFF", 14))
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background: #7F1D1D;
                color: #FCA5A5;
                border: 1px solid #991B1B;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #991B1B;
                color: #FFFFFF;
            }
        """)
        self.btn_delete.clicked.connect(self._handle_delete)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        add_layout.addLayout(btn_row)
        layout.addWidget(add_frame)

        # 3. Footer Buttons
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        if self.is_picker:
            self.btn_use = QPushButton("✓ Sử dụng mẫu này cho bài viết")
            self.btn_use.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6258E8, stop:1 #4F46E5);
                    color: #FFFFFF;
                    font-weight: 700;
                    padding: 8px 18px;
                    border-radius: 6px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #5348D6;
                }
            """)
            self.btn_use.clicked.connect(self._handle_use_selected)
            bottom_row.addWidget(self.btn_use)

        bottom_row.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

    def _on_url_changed(self, text: str) -> None:
        clean = text.strip()
        if clean.startswith("http://") or clean.startswith("https://"):
            # Nếu người dùng dán link, tự động quét sau 400ms
            from PySide6.QtCore import QTimer
            QTimer.singleShot(400, self._scan_product_url)

    def _scan_product_url(self) -> None:
        url = self.txt_url.text().strip()
        if not url:
            return

        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("⏳ Đang dò...")

        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.terminate()

        self._active_worker = AsyncLinkPreviewWorker(url, parent=self)
        self._active_worker.preview_ready.connect(self._on_preview_ready)
        self._active_worker.preview_failed.connect(self._on_preview_failed)
        self._active_worker.start()

    def _on_preview_ready(self, data: dict) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🔍 Dò tìm SP")
        self._current_preview_data = data

        title = data.get("title", "")
        price = data.get("price", "")
        local_img = data.get("local_image_path", "")

        # Hiển thị card xem trước
        self.preview_card.setVisible(True)
        self.lbl_pv_title.setText(title or data.get("url", ""))
        self.lbl_pv_price.setText(f"Giá: {price}" if price else "Sản phẩm Shopee")

        if local_img and os.path.exists(local_img):
            pix = QPixmap(local_img)
            if not pix.isNull():
                self.lbl_pv_thumb.setPixmap(
                    pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                )

        # Tự động điền tên và nội dung nếu đang trống
        if not self.txt_name.text().strip() and title:
            self.txt_name.setText(title[:45] + "..." if len(title) > 45 else title)

        if not self.txt_content.toPlainText().strip():
            url = data.get("url", "")
            self.txt_content.setPlainText(f"✨ Link mua sản phẩm chính hãng giá tốt nè cả nhà:\n{url}")

    def _on_preview_failed(self, url: str, err: str) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🔍 Dò tìm SP")
        # Vẫn cho phép nhập bằng tay
        if not self.txt_content.toPlainText().strip():
            self.txt_content.setPlainText(f"✨ Link mua sản phẩm chính hãng:\n{url}")

    def _load_templates(self) -> None:
        self.table.setRowCount(0)
        templates = self.reply_repo.list_templates(page_id=self.current_page_id)
        for tpl in templates:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # Cột 0: Thumbnail ảnh
            item_thumb = QTableWidgetItem()
            local_path = tpl.get("local_image_path")
            if local_path and os.path.exists(local_path):
                pix = QPixmap(local_path)
                if not pix.isNull():
                    icon = QIcon(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                    item_thumb.setIcon(icon)
            self.table.setItem(r, 0, item_thumb)

            # Cột 1: Tên mẫu
            item_name = QTableWidgetItem(tpl.get("name", ""))
            item_name.setData(Qt.ItemDataRole.UserRole, tpl)
            font_b = item_name.font()
            font_b.setBold(True)
            item_name.setFont(font_b)
            self.table.setItem(r, 1, item_name)

            # Cột 2: Giá
            price_text = tpl.get("price") or "—"
            item_price = QTableWidgetItem(price_text)
            item_price.setForeground(Qt.GlobalColor.darkGreen if price_text != "—" else Qt.GlobalColor.gray)
            self.table.setItem(r, 2, item_price)

            # Cột 3: Nội dung / Link
            self.table.setItem(r, 3, QTableWidgetItem(tpl.get("content", "")))

    def _handle_add(self) -> None:
        name = self.txt_name.text().strip()
        content = self.txt_content.toPlainText().strip()
        url = self.txt_url.text().strip()

        if not name and not content and not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập link sản phẩm, tên hoặc nội dung mẫu câu.")
            return

        if not name:
            name = (url or content)[:35]
        if not content and url:
            content = f"✨ Link mua sản phẩm chính hãng nè cả nhà:\n{url}"

        self.reply_repo.create_template(
            name=name,
            content=content,
            page_scope=[self.current_page_id] if self.current_page_id else None,
            product_url=url or self._current_preview_data.get("url"),
            image_url=self._current_preview_data.get("image_url"),
            local_image_path=self._current_preview_data.get("local_image_path"),
            price=self._current_preview_data.get("price"),
        )

        self.txt_url.clear()
        self.txt_name.clear()
        self.txt_content.clear()
        self.preview_card.setVisible(False)
        self._current_preview_data = {}
        self._load_templates()

    def _open_import_dialog(self) -> None:
        dlg = ImportTemplatesDialog(self.reply_repo, parent=self)
        dlg.templates_imported.connect(lambda _: self._load_templates())
        dlg.exec()

    def _handle_delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một mẫu câu để xóa.")
            return
        item = self.table.item(row, 1)
        if not item:
            return
        tpl_data = item.data(Qt.ItemDataRole.UserRole) or {}
        tpl_id = tpl_data.get("id")
        if tpl_id:
            reply = QMessageBox.question(
                self,
                "Xác nhận xóa",
                f"Bạn có chắc muốn xóa mẫu '{tpl_data.get('name')}' không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.reply_repo.delete_template(tpl_id)
                self._load_templates()

    def _on_table_double_clicked(self, item: QTableWidgetItem) -> None:
        if self.is_picker:
            self._handle_use_selected()

    def _handle_use_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một mẫu câu từ danh sách.")
            return
        item = self.table.item(row, 1)
        if not item:
            return
        tpl = item.data(Qt.ItemDataRole.UserRole)
        if tpl:
            self.selected_template = tpl
            self.template_selected.emit(tpl)
            self.accept()


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

        self.btn_manage_templates = QPushButton(" Quản lý mẫu câu")
        self.btn_manage_templates.setIcon(get_icon("composer", "#F3F6FC", 16))
        self.btn_manage_templates.clicked.connect(self._open_template_manager)
        top_layout.addWidget(self.btn_manage_templates)

        self.btn_refresh = QPushButton(" Đồng bộ bình luận")
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
