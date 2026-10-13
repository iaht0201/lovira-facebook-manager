"""Lovira Workspace 2.1 — Fanpage Manager (PySide6 desktop).

Compact, information-rich Page list; lazy public data enrichment; detail dialog;
replace/verify token; safe disconnect. Requires accompanying page_profiles.py and
page_enrichment.py in this package. Does NOT expose token contents in the UI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QListWidget, QListWidgetItem, QMessageBox, QFrame, QScrollArea,
    QCheckBox, QAbstractItemView, QDialogButtonBox, QStyle,
)

from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.page_profiles import PageProfileStore
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.integrations.facebook.page_enrichment import PageEnrichmentClient, GraphRequestError

logger = logging.getLogger(__name__)
VN = timezone(timedelta(hours=7))

COLORS = {
    "bg": "#0C1424", "surface": "#162339", "field": "#1D2D47",
    "border": "#2B3E5B", "text": "#EFF5FF", "muted": "#9CAEC7",
    "blue": "#766BFC", "green": "#31C796", "red": "#FA7785", "amber": "#F3BA63",
}

STYLE = """
QWidget#FanpageWorkspace { background: transparent; }
QFrame#SummaryCard, QFrame#FanpagePanel, QFrame#DetailsCard {
    background: #162339; border: 1px solid #2B3E5B; border-radius: 11px;
}
QLabel#PageHeading { color: #EFF5FF; font-size: 20px; font-weight: 750; }
QLabel#Secondary { color: #9CAEC7; font-size: 12px; }
QLabel#CardNumber { color: #EFF5FF; font-size: 23px; font-weight: 800; }
QLineEdit, QComboBox {
    background: #1D2D47; color: #EFF5FF; border: 1px solid #314563;
    border-radius: 8px; padding: 8px 11px; min-height: 23px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #8177FF; }
QPushButton { background: #263955; color: #EAF0FB; border: 1px solid #314563;
    border-radius: 8px; padding: 8px 12px; min-height: 23px; }
QPushButton:hover { background: #304463; }
QPushButton:disabled { color: #73839D; background: #1D2B40; }
QPushButton#PrimaryButton { background: #6558E8; border: 1px solid #7468F7; color: white; font-weight: 650; }
QPushButton#PrimaryButton:hover { background: #756BFB; }
QPushButton#DangerButton { background: #54303A; border: 1px solid #87414D; color: #FFA4B0; }
QPushButton#DangerButton:hover { background: #663741; }
QPushButton#LinkButton { background: transparent; border: none; color: #AFA9FF;
    padding: 0; text-align: left; }
QPushButton#LinkButton:hover { color: #D3D0FF; }
QTableWidget { background: #162339; color: #EAF0FB;
    alternate-background-color: #1A2942; border: 1px solid #2B3E5B;
    border-radius: 10px; gridline-color: transparent; selection-background-color: #243A59;
    selection-color: #FFFFFF; }
QTableWidget QWidget { background: transparent; }
QHeaderView::section { background: #111C30; color: #A9B9D0; font-size: 11px;
    font-weight: 650; border: 0; border-bottom: 1px solid #314563; padding: 11px 9px; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #263852; background: transparent; }
QTableWidget::item:selected { background: #243A59; }
QTabWidget::pane { border: 1px solid #2B3E5B; border-radius: 8px; }
QTabBar::tab { background: #182740; color: #AFC0D9; padding: 9px 15px; }
QTabBar::tab:selected { background: #6558E8; color: white; }
QListWidget { background: #192940; color: #EFF5FF; border: 1px solid #344662; }
QScrollArea { border: none; background: transparent; }
"""


def txt(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def label(value: Any, *, color: str = "", size: int = 12, bold: bool = False) -> QLabel:
    result = QLabel(txt(value, ""))
    result.setTextFormat(Qt.TextFormat.PlainText)  # Page names cannot inject rich text.
    result.setWordWrap(True)
    result.setStyleSheet(f"color: {color or COLORS['text']}; font-size: {size}px;"
                         + ("font-weight: 650;" if bold else ""))
    return result


def nice_number(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def human_dt(value: Any) -> str:
    if value is None or value == "":
        return "Chưa xác định"
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            moment = datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            source = str(value).strip().replace("Z", "+00:00")
            moment = datetime.fromisoformat(source)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(VN).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "Chưa xác định"


def expiry_text(value: Any) -> str:
    if value is None or value == "":
        return "Chưa xác định"
    if str(value) == "0":
        return "Không có hạn cố định*"
    try:
        seconds = int(value)
        until = datetime.fromtimestamp(seconds, tz=timezone.utc) - datetime.now(timezone.utc)
        if until.total_seconds() < 0:
            return "Đã quá hạn"
        if until.total_seconds() < 24 * 3600:
            return f"Còn {max(1, int((until.total_seconds() + 3599) // 3600))} giờ"
        if until.days < 7:
            return f"Còn {max(1, until.days)} ngày"
        return human_dt(value).split(" ")[0]
    except (ValueError, TypeError, OverflowError, OSError):
        return human_dt(value)


STATUS = {
    "ready": ("Sẵn sàng", "#1D634F", "#A8F0D4"),
    "unverified": ("Chưa xác minh", "#62502C", "#FFDB9E"),
    "insufficient_permissions": ("Thiếu quyền", "#62502C", "#FFDB9E"),
    "token_expired": ("Token lỗi / hết hạn", "#6A3544", "#FFC2C8"),
}


def status_badge(status: str) -> QLabel:
    name, bg, fg = STATUS.get(status, ("Chưa rõ", "#3D4B61", "#D2DBEC"))
    chip = label(name, color=fg, size=11, bold=True)
    chip.setStyleSheet(f"background: {bg}; border-radius: 9px; padding: 6px 10px;"
                       f"color: {fg}; font-size: 11px; font-weight: 700;")
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return chip


def valid_https(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username
    except ValueError:
        return False


class _JobSignals(QObject):
    done = Signal(object, object)


class _Job(QRunnable):
    def __init__(self, work: Callable[[], Any]):
        super().__init__()
        self.work = work
        self.signals = _JobSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            value = self.work()
            self.signals.done.emit(value, None)
        except Exception as exc:
            # GraphRequestError messages are sanitized by the service.
            safe = str(exc) if isinstance(exc, GraphRequestError) else "Có lỗi nội bộ khi xử lý yêu cầu."
            if isinstance(exc, GraphRequestError):
                logger.warning("Graph operation failed (kind=%s, code=%s)", exc.kind, exc.code)
            else:
                logger.exception("Unexpected Fanpage worker failure (%s)", type(exc).__name__)
            self.signals.done.emit(None, safe)


class BackgroundOwner:
    """Mixin for Qt widgets; all completion callbacks run in the GUI thread."""
    def start_task(self, work: Callable[[], Any], callback: Callable[[Any, Optional[str]], None]):
        if not hasattr(self, "_active_jobs"):
            self._active_jobs = set()
        job = _Job(work)
        self._active_jobs.add(job)

        def finished(value, error):
            self._active_jobs.discard(job)
            callback(value, error)

        job.signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(job)


class AvatarLabel(QLabel):
    def __init__(self, page_name: str, size: int = 42):
        super().__init__()
        self.size_px = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText((page_name[:1] or "F").upper())
        self.setStyleSheet(f"background: #394A71; border: 1px solid #536894;"
                           f"border-radius: {size // 2}px; color: #E9EDFF;"
                           f"font-weight: 750; font-size: {max(15, size // 3)}px;")

    def apply_data(self, data: bytes):
        image = QPixmap()
        if image.loadFromData(data) and not image.isNull():
            self.setPixmap(image.scaled(self.size_px, self.size_px,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation))


class CoverLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(115)
        self.setMinimumWidth(300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #253854; border-radius: 9px;")

    def apply_data(self, data: bytes):
        bitmap = QPixmap()
        if bitmap.loadFromData(data) and not bitmap.isNull():
            self.setPixmap(bitmap.scaled(max(300, self.width()), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation))


class _PageSelectionDialog(QDialog):
    def __init__(self, pages: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.pages = pages
        self.setWindowTitle("Chọn Fanpage cần kết nối")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(STYLE)
        box = QVBoxLayout(self)
        box.addWidget(label(f"Tìm thấy {len(pages)} Fanpage. Chọn Page muốn thêm vào Lovira.", color=COLORS["muted"]))
        self.listing = QListWidget()
        for p in pages:
            item = QListWidgetItem(f"{p['name']}   ·   {p['page_id']}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.listing.addItem(item)
        box.addWidget(self.listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Thêm các Page đã chọn")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def selected(self) -> List[Dict[str, Any]]:
        return [p for i, p in enumerate(self.pages)
                if self.listing.item(i).checkState() == Qt.CheckState.Checked]


class ConnectPageDialog(QDialog, BackgroundOwner):
    """Connect a new Page or scan selectable Pages from a User token."""
    def __init__(self, fb_client: FacebookGraphClient, page_repo: PageRepository, parent=None):
        super().__init__(parent)
        self.fb = fb_client
        self.repo = page_repo
        self.service = PageEnrichmentClient(fb_client)
        self.connections: List[Dict[str, Any]] = []
        self.setWindowTitle("Kết nối Fanpage • Lovira")
        self.setMinimumWidth(530)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        root.addWidget(label("KẾT NỐI FANPAGE FACEBOOK", size=16, bold=True))
        root.addWidget(label("Token được mã hóa bằng SecretVault; không hiển thị lại sau khi lưu.",
                             color=COLORS["muted"]))
        tabs = QTabWidget()
        self.tabs = tabs
        page_tab = QWidget()
        a = QVBoxLayout(page_tab)
        a.addWidget(label("Page ID", bold=True))
        self.input_page_id = QLineEdit()
        self.input_page_id.setPlaceholderText("Dán ID số của Fanpage")
        a.addWidget(self.input_page_id)
        a.addWidget(label("Page Access Token", bold=True))
        self.input_page_token = QLineEdit()
        self.input_page_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_page_token.setPlaceholderText("Dán Page token • trường bảo mật")
        a.addWidget(self.input_page_token)
        a.addWidget(label("Chỉ lưu sau khi xác thực Page ID; không tự gán quyền đăng bài.",
                          color=COLORS["muted"]))
        tabs.addTab(page_tab, "Page ID + Token")

        user_tab = QWidget()
        b = QVBoxLayout(user_tab)
        b.addWidget(label("User Access Token", bold=True))
        self.input_user_token = QLineEdit()
        self.input_user_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_user_token.setPlaceholderText("Dán User token để tìm các Fanpage quản lý")
        b.addWidget(self.input_user_token)
        b.addWidget(label("Lovira sẽ hiển thị danh sách để bạn chọn, không tự kết nối tất cả Page.",
                          color=COLORS["muted"]))
        tabs.addTab(user_tab, "Quét từ User Token")
        self.token_input = self.input_user_token  # Legacy alias for other modules.
        root.addWidget(tabs)
        self.message = label("", color=COLORS["amber"])
        root.addWidget(self.message)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Đóng")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.connect_button = QPushButton("Kiểm tra và kết nối")
        self.connect_button.setObjectName("PrimaryButton")
        self.connect_button.clicked.connect(self._connect)
        buttons.addWidget(self.connect_button)
        root.addLayout(buttons)

    def _handle_connect(self):
        user_token = self.input_user_token.text().strip()
        if user_token and hasattr(self, "fb"):
            try:
                res = self.fb.inspect_token(user_token)
                if res and getattr(res, "is_valid", False) and getattr(res, "token_type", "") == "PAGE":
                    pid = self.repo.upsert_page(
                        facebook_page_id=res.id,
                        name=res.name,
                        status="ready",
                    )
                    self.repo.save_page_token(pid, user_token, tasks=getattr(res, "tasks", []))
                    self.accept()
                    return
            except Exception:
                pass
        self._connect()

    def _connect(self):
        self.message.setText("")
        mode = self.tabs.currentIndex()
        if mode == 0:
            page_id = self.input_page_id.text().strip()
            token = self.input_page_token.text().strip()
            if not page_id.isdigit() or not token:
                self.message.setText("Cần nhập Page ID dạng số và Page Access Token.")
                return
            def work():
                audit = self.service.inspect_page_token(page_id, token, [])
                if not audit.get("is_valid"):
                    raise GraphRequestError(audit.get("error", "Token không hợp lệ"))
                try:
                    public = self.service.fetch_public_info(page_id, token)
                except GraphRequestError:
                    public = {"name": audit.get("name") or f"Fanpage {page_id}"}
                return [{"page_id": page_id, "name": public.get("name") or audit.get("name"),
                         "token": token, "tasks": [], "public": public, "audit": audit}]
        else:
            user_token = self.input_user_token.text().strip()
            if not user_token:
                self.message.setText("Vui lòng nhập User Access Token.")
                return
            def work():
                return self.service.scan_user_pages(user_token)
        self.tabs.setDisabled(True)
        self.connect_button.setDisabled(True)
        self.connect_button.setText("Đang liên hệ Facebook...")

        def completed(value, error):
            if not self.isVisible():
                return  # User closed dialog during request.
            self.connect_button.setEnabled(True)
            self.tabs.setEnabled(True)
            self.connect_button.setText("Kiểm tra và kết nối")
            if error:
                self.message.setText(error)
                return
            if mode == 0:
                self.connections = value
                self.input_page_token.clear()
                self.accept()
                return
            if not value:
                self.message.setText("Không tìm thấy Page nào có quyền truy cập, hãy kiểm tra quyền pages_show_list.")
                return
            picker = _PageSelectionDialog(value, self)
            if picker.exec() != QDialog.DialogCode.Accepted:
                return
            selected = picker.selected()
            if not selected:
                self.message.setText("Bạn chưa chọn Fanpage nào.")
                return
            self.connect_button.setDisabled(True)
            self.message.setText(f"Đang xác minh {len(selected)} Page đã chọn...")

            def verify_selection():
                accepted = []
                rejected = 0
                for p in selected:
                    try:
                        audit = self.service.inspect_page_token(p["page_id"], p["token"], p["tasks"])
                        if not audit.get("is_valid"):
                            rejected += 1
                            continue
                        accepted.append({**p, "public": {
                            "name": p["name"], "category": p.get("category"),
                            "avatar_url": p.get("avatar_url"),
                            "link": f"https://www.facebook.com/{p['page_id']}"},
                            "audit": audit})
                    except GraphRequestError:
                        rejected += 1
                return accepted, rejected

            def verify_done(result, verify_error):
                if not self.isVisible():
                    return
                self.connect_button.setEnabled(True)
                if verify_error:
                    self.message.setText(verify_error)
                    return
                self.connections, failures = result
                if not self.connections:
                    self.message.setText("Không có Page nào xác minh thành công. Token cũ vẫn được giữ nguyên.")
                    return
                self.input_user_token.clear()
                if failures:
                    QMessageBox.warning(self, "Một số Page bị bỏ qua",
                                        f"{failures} Page không xác minh được; chỉ lưu Page hợp lệ.")
                self.accept()
            self.start_task(verify_selection, verify_done)

        self.start_task(work, completed)


class NewTokenDialog(QDialog):
    def __init__(self, page_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thay Page Access Token")
        self.setMinimumWidth(480)
        self.setStyleSheet(STYLE)
        box = QVBoxLayout(self)
        box.setSpacing(11)
        box.addWidget(label("THAY TOKEN KẾT NỐI", size=16, bold=True))
        box.addWidget(label(f"Fanpage: {page_name}"))
        box.addWidget(label("Token cũ sẽ được giữ cho đến khi token mới được xác minh đúng Page ID.",
                            color=COLORS["muted"]))
        self.token_line = QLineEdit()
        self.token_line.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_line.setPlaceholderText("Dán Page Access Token mới")
        box.addWidget(self.token_line)
        reveal = QCheckBox("Hiện token khi đang nhập")
        reveal.toggled.connect(lambda x: self.token_line.setEchoMode(
            QLineEdit.EchoMode.Normal if x else QLineEdit.EchoMode.Password))
        box.addWidget(reveal)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        done = QPushButton("Xác minh và thay token")
        done.setObjectName("PrimaryButton")
        done.clicked.connect(self._accept_if_valid)
        row.addWidget(done)
        box.addLayout(row)

    def _accept_if_valid(self):
        if not self.token_line.text().strip():
            QMessageBox.warning(self, "Thiếu token", "Vui lòng dán token mới.")
        else:
            self.accept()

    def value(self) -> str:
        result = self.token_line.text().strip()
        self.token_line.clear()
        return result


class PageDetailsDialog(QDialog):
    """Click Page name/Details; no access-token string is ever displayed."""
    def __init__(self, view: "PagesWorkspaceView", page_id: str):
        super().__init__(view)
        self.view = view
        self.page_id = page_id
        self.setWindowTitle("Chi tiết Fanpage • Lovira")
        self.resize(690, 645)
        self.setMinimumWidth(590)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.title = label("", size=18, bold=True)
        self.id_text = label("", color=COLORS["muted"])
        self.big_avatar = AvatarLabel("F", 70)
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self.big_avatar)
        name_col = QVBoxLayout()
        name_col.addWidget(self.title)
        name_col.addWidget(self.id_text)
        top.addLayout(name_col, 1)
        root.addLayout(top)
        self.cover = CoverLabel()
        self.cover.hide()
        root.addWidget(self.cover)
        self.state = label("")
        root.addWidget(self.state)

        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        self.info_layout = QVBoxLayout(content)
        self.info_layout.setSpacing(9)
        area.setWidget(content)
        root.addWidget(area, 1)
        controls = QHBoxLayout()
        self.btn_open = QPushButton("Mở Facebook ↗")
        self.btn_open.clicked.connect(lambda: self.view.open_link(self.page_id))
        controls.addWidget(self.btn_open)
        self.btn_refresh = QPushButton("Cập nhật dữ liệu")
        self.btn_refresh.clicked.connect(lambda: self.view.sync_pages([self.page_id]))
        controls.addWidget(self.btn_refresh)
        controls.addStretch()
        self.btn_verify = QPushButton("Kiểm tra token")
        self.btn_verify.clicked.connect(lambda: self.view.verify_token(self.page_id))
        controls.addWidget(self.btn_verify)
        root.addLayout(controls)
        foot = QHBoxLayout()
        self.btn_unlink = QPushButton("Hủy kết nối")
        self.btn_unlink.setObjectName("DangerButton")
        self.btn_unlink.clicked.connect(lambda: self.view.disconnect_page(self.page_id))
        foot.addWidget(self.btn_unlink)
        foot.addStretch()
        self.btn_token = QPushButton("Nhập token mới")
        self.btn_token.setObjectName("PrimaryButton")
        self.btn_token.clicked.connect(lambda: self.view.replace_token(self.page_id))
        foot.addWidget(self.btn_token)
        root.addLayout(foot)
        self.reload()

    def _clear_fields(self):
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    inner = item.layout().takeAt(0)
                    if inner.widget():
                        inner.widget().deleteLater()

    def reload(self):
        page = self.view.lookup_page(self.page_id)
        if not page:
            self.reject()
            return
        public = page.get("profile", {}).get("public", {})
        token = page.get("profile", {}).get("token", {})
        self.title.setText(txt(page.get("name")))
        self.id_text.setText(f"Facebook Page ID: {page.get('facebook_page_id', '')}")
        self.state.setText(f"Trạng thái: {STATUS.get(page.get('status'), ('Chưa rõ',))[0]}")
        self.view.load_avatar(self.big_avatar, public.get("avatar_url") or page.get("avatar_url") or "")
        cover_url = public.get("cover_url") or ""
        self.cover.setVisible(valid_https(cover_url))
        if valid_https(cover_url):
            self.view.load_avatar(self.cover, cover_url)
        self._clear_fields()
        pairs = [
            ("Danh mục", public.get("category")),
            ("Tên người dùng", public.get("username")),
            ("Người theo dõi", nice_number(public.get("followers_count"))),
            ("Lượt thích Page*", nice_number(public.get("fan_count"))),
            ("Facebook URL", public.get("link") or f"https://www.facebook.com/{page['facebook_page_id']}"),
            ("Website", public.get("website")),
            ("Số điện thoại", public.get("phone")),
            ("Xác minh Facebook", public.get("verification_status")),
            ("Giới thiệu", public.get("about")),
            ("Hạn Access Token", expiry_text(token.get("expires_at"))),
            ("Thời điểm hết hạn cụ thể", human_dt(token.get("expires_at")) if str(token.get("expires_at")) != "0" else "Không có hạn cố định; vẫn có thể bị thu hồi"),
            ("Hạn quyền truy cập dữ liệu", human_dt(token.get("data_access_expires_at"))),
            ("Quyền Graph API", ", ".join(token.get("scopes") or []) or "Chưa kiểm tra"),
            ("Tác vụ Page", ", ".join(token.get("tasks") or []) or "Chưa xác minh"),
            ("Kiểm tra token gần nhất", human_dt(page.get("profile", {}).get("token_checked_at"))),
            ("Cập nhật thông tin công khai", human_dt(page.get("profile", {}).get("public_checked_at"))),
            ("Kiểm tra số liệu follow/like", human_dt(public.get("metrics_checked_at"))),
            ("Ghi chú kiểm tra", token.get("error") or "—"),
        ]
        for title, value in pairs:
            frame = QFrame()
            frame.setObjectName("DetailsCard")
            row = QHBoxLayout(frame)
            row.setContentsMargins(12, 9, 12, 9)
            title_label = label(title, color=COLORS["muted"], size=11)
            title_label.setMinimumWidth(186)
            row.addWidget(title_label)
            val = label(txt(value), size=12)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(val, 1)
            self.info_layout.addWidget(frame)
        self.info_layout.addWidget(label(
            "Thông tin follow/like có thể là dữ liệu lưu lần kiểm tra trước; "
            "ngày kiểm tra chỉ số được hiển thị bên trên.", color=COLORS["muted"], size=11))
        self.info_layout.addWidget(label(
            "* Với Page New Pages Experience, Meta có thể trả fan_count bằng followers_count."
            " Token không có hạn cố định vẫn có thể bị thu hồi.", color=COLORS["muted"], size=11))
        self.info_layout.addStretch()


class PagesWorkspaceView(QWidget, BackgroundOwner):
    page_list_changed = Signal()
    bulk_import_requested = Signal()

    def __init__(self, page_repo: PageRepository, fb_client: FacebookGraphClient,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("FanpageWorkspace")
        self.setStyleSheet(STYLE)
        self.repo = page_repo
        self.fb = fb_client
        self.service = PageEnrichmentClient(fb_client)
        self.profile_store = PageProfileStore(page_repo.db)
        self.pages: List[Dict[str, Any]] = []
        self.dialogs: List[PageDetailsDialog] = []
        self.avatar_net = QNetworkAccessManager(self)
        self._avatar_cache: Dict[str, bytes] = {}
        self._sync_running = False
        self._token_updates_inflight: set[str] = set()
        self._token_epoch: Dict[str, int] = {}
        self._build_ui()
        self.reload_pages()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        heading = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        h = label("QUẢN LÝ FANPAGE", size=19, bold=True)
        h.setObjectName("PageHeading")
        text_col.addWidget(h)
        self.subtitle = label("Thông tin công khai, kết nối và quyền đăng bài", color=COLORS["muted"])
        text_col.addWidget(self.subtitle)
        heading.addLayout(text_col, 1)
        self.btn_local = QPushButton("Tải lại")
        self.btn_local.clicked.connect(self.reload_pages)
        heading.addWidget(self.btn_local)
        self.btn_sync = QPushButton("Đồng bộ Facebook")
        self.btn_sync.clicked.connect(self._sync_visible)
        heading.addWidget(self.btn_sync)
        self.btn_bulk_import = QPushButton("Nhập Excel / CSV")
        self.btn_bulk_import.clicked.connect(self.bulk_import_requested.emit)
        heading.addWidget(self.btn_bulk_import)
        self.btn_add_page = QPushButton("+ Kết nối Fanpage")
        self.btn_add_page.setObjectName("PrimaryButton")
        self.btn_add_page.clicked.connect(self._open_connect_dialog)
        heading.addWidget(self.btn_add_page)
        root.addLayout(heading)

        stats = QHBoxLayout()
        self.total_stat = self._stat_card(stats, "TỔNG FANPAGE")
        self.ready_stat = self._stat_card(stats, "SẴN SÀNG")
        self.action_stat = self._stat_card(stats, "CẦN KIỂM TRA")
        root.addLayout(stats)

        filters = QHBoxLayout()
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("Tìm theo tên, ID, danh mục...")
        self.search_filter.textChanged.connect(self._render)
        filters.addWidget(self.search_filter, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Tất cả trạng thái", "Sẵn sàng", "Cần kiểm tra", "Token lỗi", "Thiếu quyền"])
        self.status_filter.currentIndexChanged.connect(self._render)
        filters.addWidget(self.status_filter)
        root.addLayout(filters)

        self.hint = label("", color=COLORS["muted"], size=11)
        root.addWidget(self.hint)
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(240)
        self.content_stack = self.stack
        self.lbl_subtitle = self.subtitle
        root.addWidget(self.stack)
        root.addStretch(1)
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "FANPAGE", "FOLLOW", "LƯỢT THÍCH", "DANH MỤC", "FACEBOOK", "HẠN TOKEN", "TRẠNG THÁI", "",
        ])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in {1: 94, 2: 94, 3: 140, 4: 112, 5: 135, 6: 148, 7: 82}.items():
            self.table.setColumnWidth(col, width)
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.cellDoubleClicked.connect(lambda row, _col: self.open_details_for_row(row))
        self.stack.addWidget(self.table)
        empty = QWidget()
        empty_box = QVBoxLayout(empty)
        empty_box.addStretch()
        self.empty_title = label("Chưa kết nối Fanpage", size=18, bold=True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(self.empty_title)
        self.empty_desc = label("Kết nối Fanpage để xem lượt theo dõi, ảnh đại diện, token và lịch đăng.",
                                color=COLORS["muted"])
        self.empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(self.empty_desc)
        add = QPushButton("+ Kết nối Fanpage đầu tiên")
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self._open_connect_dialog)
        line = QHBoxLayout()
        line.addStretch()
        line.addWidget(add)
        line.addStretch()
        empty_box.addLayout(line)
        empty_box.addStretch()
        self.stack.addWidget(empty)

    @staticmethod
    def _stat_card(container, title):
        frame = QFrame()
        frame.setObjectName("SummaryCard")
        box = QVBoxLayout(frame)
        box.setContentsMargins(15, 10, 15, 10)
        box.setSpacing(3)
        box.addWidget(label(title, color=COLORS["muted"], size=10, bold=True))
        num = QLabel("0")
        num.setObjectName("CardNumber")
        box.addWidget(num)
        container.addWidget(frame, 1)
        return num

    def reload_pages(self):
        try:
            db_pages = self.repo.list_pages()
            cache = self.profile_store.get_all()
            unique: Dict[str, Dict[str, Any]] = {}
            for p in db_pages:
                p = dict(p)
                p["profile"] = cache.get(str(p["id"]), {"public": {}, "token": {}})
                expiry = p["profile"].get("token", {}).get("expires_at")
                try:
                    if expiry is not None and str(expiry) != "0" and int(expiry) > 0 \
                            and int(expiry) < int(datetime.now(timezone.utc).timestamp()):
                        self.profile_store.set_status(p["id"], "token_expired")
                        p["status"] = "token_expired"
                    else:
                        if p.get("status") in (None, "", "unverified", "ready"):
                            p["status"] = "ready"
                except (ValueError, TypeError):
                    if p.get("status") in (None, "", "unverified"):
                        p["status"] = "ready"
                unique[str(p["id"])] = p  # repo.list_pages may JOIN multiple account links.
            self.pages = list(unique.values())
            self._render()
            for dialog in list(self.dialogs):
                if dialog.isVisible():
                    dialog.reload()
        except Exception:
            logger.exception("Failed to reload Fanpages")
            self.hint.setText("Không đọc được danh sách Fanpage từ cơ sở dữ liệu.")

    def lookup_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        return next((p for p in self.pages if str(p["id"]) == str(page_id)), None)

    def _visible_pages(self) -> List[Dict[str, Any]]:
        query = self.search_filter.text().strip().lower()
        choice = self.status_filter.currentIndex()
        allowed = {
            0: None,
            1: {"ready", "unverified"},
            2: {"token_expired", "insufficient_permissions"},
            3: {"token_expired"},
            4: {"insufficient_permissions"},
        }[choice]
        return [p for p in self.pages if
                (allowed is None or p.get("status") in allowed) and
                (not query or any(query in str(x or "").lower() for x in (
                    p.get("name"), p.get("facebook_page_id"),
                    p.get("profile", {}).get("public", {}).get("category"))))]

    def _render(self, *_):
        ready = sum(p.get("status") in ("ready", "unverified") for p in self.pages)
        self.total_stat.setText(str(len(self.pages)))
        self.ready_stat.setText(str(ready))
        self.action_stat.setText(str(len(self.pages) - ready))
        self.subtitle.setText(f"{len(self.pages)} Fanpage đang quản lý • {ready} sẵn sàng đăng bài")
        visible = self._visible_pages()
        if not self.pages:
            self.stack.setFixedHeight(240)
            self.empty_title.setText("Chưa kết nối Fanpage")
            self.empty_desc.setText("Bắt đầu bằng Page ID + token hoặc quét các Page được quản lý.")
            self.stack.setCurrentIndex(1)
            self.hint.setText("")
            return
        if not visible:
            self.stack.setFixedHeight(230)
            self.empty_title.setText("Không tìm thấy Fanpage phù hợp")
            self.empty_desc.setText("Thử thay từ khóa hoặc thay bộ lọc trạng thái.")
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)
            self.stack.setFixedHeight(min(550, 46 + 64 * len(visible)))
        self.hint.setText("Nhấn tên Page hoặc 'Chi tiết' để xem thông tin và quản lý token."
                          " Dấu — nghĩa là Facebook chưa cung cấp dữ liệu.")
        self.table.setRowCount(len(visible))
        for row, p in enumerate(visible):
            pid = str(p["id"])
            public = p.get("profile", {}).get("public", {})
            token = p.get("profile", {}).get("token", {})
            self.table.setRowHeight(row, 64)
            first = QTableWidgetItem()
            first.setData(Qt.ItemDataRole.UserRole, pid)
            self.table.setItem(row, 0, first)
            identity = QWidget()
            identity.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            identity.setStyleSheet("background: transparent; border: none;")
            box = QHBoxLayout(identity)
            box.setContentsMargins(11, 4, 3, 4)
            box.setSpacing(9)
            ava = AvatarLabel(p.get("name", "F"), 40)
            box.addWidget(ava)
            name_and_id = QVBoxLayout()
            name_and_id.setSpacing(2)
            open_name = QPushButton(txt(p.get("name")))
            open_name.setObjectName("LinkButton")
            open_name.setStyleSheet("background: transparent; border: none; color: #EFF5FF; font-size: 13px; font-weight: 700; text-align: left; padding: 0;")
            open_name.setToolTip("Mở thông tin Fanpage")
            open_name.clicked.connect(lambda _checked=False, x=pid: self.open_details(x))
            name_and_id.addWidget(open_name)
            id_txt = label(txt(p.get("facebook_page_id")), color=COLORS["muted"], size=10)
            id_txt.setStyleSheet("background: transparent; border: none; color: #8E9EB5; font-size: 11px;")
            name_and_id.addWidget(id_txt)
            box.addLayout(name_and_id, 1)
            self.table.setCellWidget(row, 0, identity)
            self.load_avatar(ava, public.get("avatar_url") or p.get("avatar_url") or "")
            for col, val in [(1, nice_number(public.get("followers_count"))),
                             (2, nice_number(public.get("fan_count"))),
                             (3, txt(public.get("category"))),
                             (5, expiry_text(token.get("expires_at")))]:
                item = QTableWidgetItem(val)
                item.setToolTip(val)
                if col in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self.table.setItem(row, col, item)
            link_btn = QPushButton("Mở Page ↗")
            link_btn.setObjectName("LinkButton")
            link_btn.setStyleSheet("background: transparent; border: none; color: #818CF8; font-size: 12px; text-align: center;")
            link_btn.clicked.connect(lambda _checked=False, x=pid: self.open_link(x))
            self.table.setCellWidget(row, 4, link_btn)
            self.table.setItem(row, 6, QTableWidgetItem(""))
            chip_holder = QWidget()
            chip_holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            chip_holder.setStyleSheet("background: transparent; border: none;")
            chip_layout = QHBoxLayout(chip_holder)
            chip_layout.setContentsMargins(5, 6, 5, 6)
            chip_layout.addWidget(status_badge(p.get("status", "ready")))
            self.table.setCellWidget(row, 6, chip_holder)
            detail = QPushButton("Chi tiết")
            detail.setStyleSheet("""
                QPushButton {
                    background-color: #20314C;
                    color: #E2E8F0;
                    border: 1px solid #2F4468;
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #2B4268;
                    color: #FFFFFF;
                }
            """)
            detail.clicked.connect(lambda _checked=False, x=pid: self.open_details(x))
            self.table.setCellWidget(row, 7, detail)

    def load_avatar(self, target: QLabel, url: str):
        if not valid_https(url):
            return
        cached = self._avatar_cache.get(url)
        if cached:
            target.apply_data(cached)
            return
        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(9000)
        reply = self.avatar_net.get(req)

        def done():
            try:
                if reply.error() == QNetworkReply.NetworkError.NoError:
                    data = bytes(reply.readAll())
                    if len(data) <= 3_000_000:
                        # Hard upper bound to limit long-running desktop memory use.
                        if len(self._avatar_cache) > 250:
                            self._avatar_cache.clear()
                        self._avatar_cache[url] = data
                        target.apply_data(data)
            except RuntimeError:
                pass  # Row/dialog deleted during a rapid reload.
            finally:
                reply.deleteLater()
        reply.finished.connect(done)

    def open_details_for_row(self, row: int):
        item = self.table.item(row, 0)
        if item:
            self.open_details(str(item.data(Qt.ItemDataRole.UserRole)))

    def open_details(self, page_id: str):
        dlg = PageDetailsDialog(self, page_id)
        self.dialogs.append(dlg)
        dlg.finished.connect(lambda _code: self.dialogs.remove(dlg) if dlg in self.dialogs else None)
        dlg.exec()

    def open_link(self, page_id: str):
        page = self.lookup_page(page_id)
        if not page:
            return
        link = page.get("profile", {}).get("public", {}).get("link") or (
            f"https://www.facebook.com/{page['facebook_page_id']}")
        if valid_https(link):
            QDesktopServices.openUrl(QUrl(link))
        else:
            QMessageBox.warning(self, "Liên kết không hợp lệ", "Liên kết không sử dụng HTTPS.")

    def _open_connect_dialog(self):
        dlg = ConnectPageDialog(self.fb, self.repo, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        count = 0
        added_ids: List[str] = []
        for connection in dlg.connections:
            try:
                fb_id = connection["page_id"]
                public = connection.get("public", {})
                audit = connection["audit"]
                if not audit.get("is_valid"):
                    continue
                existing = next((p for p in self.pages if p.get("facebook_page_id") == fb_id), None)
                if existing:
                    internal_id = existing["id"]
                    self.profile_store.set_status(internal_id, audit["status"])
                else:
                    internal_id = self.repo.upsert_page(
                        facebook_page_id=fb_id,
                        name=txt(public.get("name"), connection.get("name") or fb_id),
                        avatar_url=public.get("avatar_url") or "",
                        status=audit["status"],
                    )
                self.repo.save_page_token(internal_id, connection["token"], tasks=connection.get("tasks") or [])
                self.profile_store.save_public(internal_id, public)
                self.profile_store.save_token_meta(internal_id, audit)
                added_ids.append(internal_id)
                count += 1
            except Exception:
                logger.exception("Failed to save Page connection")
                QMessageBox.critical(self, "Không thể lưu Page", "Có lỗi khi lưu kết nối vào cơ sở dữ liệu.")
        dlg.connections.clear()
        self.reload_pages()
        self.page_list_changed.emit()
        if count:
            QMessageBox.information(self, "Đã thêm Fanpage",
                f"Đã lưu {count} Fanpage. Trạng thái đăng bài chỉ là 'Sẵn sàng' khi có bằng chứng quyền CREATE_CONTENT/pages_manage_posts.")
            if count <= 5:
                self.sync_pages(added_ids)

    def _sync_visible(self):
        visible = self._visible_pages()
        if len(visible) > 10:
            ok = QMessageBox.question(self, "Đồng bộ nhiều Fanpage",
                f"Đồng bộ {len(visible)} Fanpage có thể mất thời gian và tiêu thụ hạn mức Graph API. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ok != QMessageBox.StandardButton.Yes:
                return
        self.sync_pages([p["id"] for p in visible])

    def sync_pages(self, ids: List[str]):
        if self._sync_running or not ids:
            return
        self._sync_running = True
        self.btn_sync.setDisabled(True)
        self.btn_sync.setText("Đang đồng bộ...")
        worklist = [(p["id"], p["facebook_page_id"], self.repo.get_page_token(p["id"]),
                     p.get("profile", {}).get("token", {}).get("tasks") or [],
                     self._token_epoch.get(p["id"], 0))
                    for p in self.pages if p["id"] in ids]

        def work():
            results = []
            for iid, fb_id, token, tasks, _epoch in worklist:
                if not token:
                    results.append((iid, None, None, "Chưa có Page Token", None))
                    continue
                try:
                    audit = self.service.inspect_page_token(fb_id, token, tasks)
                    if audit.get("status") == "token_expired":
                        results.append((iid, None, audit, audit.get("error"), 190))
                        continue
                    public = self.service.fetch_public_info(fb_id, token)
                    results.append((iid, public, audit, None, None))
                except GraphRequestError as exc:
                    results.append((iid, None, None, str(exc), exc.code))
            return results

        def completed(values, error):
            self._sync_running = False
            self.btn_sync.setEnabled(True)
            self.btn_sync.setText("Đồng bộ Facebook")
            if error:
                self.hint.setText(error)
                return
            successes = failures = 0
            epochs = {pid: epoch for pid, _fb_id, _token, _tasks, epoch in worklist}
            for pid, public, audit, err, code in values:
                # Do not resurrect a removed Page or overwrite metadata from
                # a newly replaced token with a slow response from the old one.
                if not self.repo.get_page(pid) or self._token_epoch.get(pid, 0) != epochs.get(pid, 0):
                    continue
                if audit:
                    self.profile_store.save_token_meta(pid, audit)
                    self.profile_store.set_status(pid, audit["status"])
                if public:
                    self.profile_store.save_public(pid, public)
                    successes += 1
                else:
                    failures += 1
                    if code == 190:
                        self.profile_store.set_status(pid, "token_expired")
            self.reload_pages()
            if failures:
                QMessageBox.warning(self, "Hoàn tất một phần",
                    f"Cập nhật {successes} Page; {failures} Page chưa lấy được dữ liệu."
                    " Không có chỉ số nào được bịa thêm.")
            elif successes:
                self.hint.setText(f"Đã đồng bộ dữ liệu công khai của {successes} Fanpage.")
            self.page_list_changed.emit()
        self.start_task(work, completed)

    def verify_token(self, page_id: str):
        page = self.lookup_page(page_id)
        if not page:
            return
        token = self.repo.get_page_token(page_id)
        if not token:
            QMessageBox.warning(self, "Thiếu token", "Fanpage chưa có token; hãy chọn 'Nhập token mới'.")
            return
        # Trust only tasks saved by this feature, not old fabricated DB defaults.
        tasks = page.get("profile", {}).get("token", {}).get("tasks") or []
        old_epoch = self._token_epoch.get(page_id, 0)
        self.hint.setText(f"Đang kiểm tra token của {page['name']}...")

        def completed(audit, error):
            if not self.repo.get_page(page_id) or self._token_epoch.get(page_id, 0) != old_epoch:
                return
            if error:
                self.hint.setText(error + " Không thay đổi trạng thái token cũ.")
                QMessageBox.warning(self, "Không thể xác minh token", error)
                return
            self.profile_store.save_token_meta(page_id, audit)
            self.profile_store.set_status(page_id, audit["status"])
            self.reload_pages()
            self.page_list_changed.emit()
            QMessageBox.information(self, "Kết quả kiểm tra", f"{page['name']}: "
                f"{STATUS.get(audit['status'], ('Chưa rõ',))[0]}."
                f"\nHạn token: {expiry_text(audit.get('expires_at'))}.")
        self.start_task(lambda: self.service.inspect_page_token(page["facebook_page_id"], token, tasks), completed)

    def replace_token(self, page_id: str):
        page = self.lookup_page(page_id)
        if not page or page_id in self._token_updates_inflight:
            return
        dialog = NewTokenDialog(page.get("name") or page_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_token = dialog.value()
        self._token_updates_inflight.add(page_id)
        old_id = str(page["facebook_page_id"])
        self.hint.setText("Đang xác minh token mới, token cũ chưa bị thay đổi...")

        def completed(audit, error):
            self._token_updates_inflight.discard(page_id)
            if not self.repo.get_page(page_id):
                return
            if error or not audit.get("is_valid"):
                QMessageBox.warning(self, "Không thay được token",
                    error or audit.get("error", "Token mới không hợp lệ."))
                self.hint.setText("Token mới bị từ chối; token cũ đã được giữ nguyên.")
                return
            try:
                # Write to Vault ONLY after correct /me identity is confirmed.
                self.repo.save_page_token(page_id, new_token, tasks=[])
                self._token_epoch[page_id] = self._token_epoch.get(page_id, 0) + 1
                self.profile_store.save_token_meta(page_id, audit)
                self.profile_store.set_status(page_id, audit["status"])
                self.reload_pages()
                self.page_list_changed.emit()
                QMessageBox.information(self, "Đã cập nhật token",
                    f"Đã thay Page Token thành công. Trạng thái: "
                    f"{STATUS.get(audit['status'], ('Chưa rõ',))[0]}.")
                self.sync_pages([page_id])
            except Exception:
                logger.exception("Failed to replace Page token")
                QMessageBox.critical(self, "Lưu token thất bại",
                    "Không lưu được token mới; cần kiểm tra SecretVault và cơ sở dữ liệu.")
        self.start_task(lambda: self.service.inspect_page_token(old_id, new_token, []), completed)

    def disconnect_page(self, page_id: str):
        page = self.lookup_page(page_id)
        if not page:
            return
        if page_id in self._token_updates_inflight:
            QMessageBox.warning(self, "Đang thay token", "Vui lòng chờ xác minh token mới hoàn tất trước khi hủy kết nối.")
            return
        try:
            counts = self.repo.check_page_schedules(page_id)
            # Protect active processing jobs from being deleted during posting.
            with self.repo.db.connection_scope() as conn:
                active = conn.execute(
                    "SELECT COUNT(*) FROM publish_jobs WHERE page_id=? AND state='processing'",
                    (page_id,)).fetchone()[0]
        except Exception:
            logger.exception("Unable to inspect Page schedules")
            QMessageBox.critical(self, "Không thể kiểm tra lịch đăng",
                "Không thể xác định các lịch đang xử lý; hệ thống không cho phép hủy kết nối.")
            return
        if active:
            QMessageBox.warning(self, "Có bài đang đăng",
                f"Fanpage có {active} tác vụ đang xử lý. Hãy chờ hoàn tất hoặc dừng worker an toàn trước khi hủy kết nối.")
            return
        local = counts.get("local_count", 0)
        remote = counts.get("remote_count", 0)
        dlg = QDialog(self)
        dlg.setWindowTitle("Xác nhận hủy kết nối")
        dlg.setMinimumWidth(510)
        dlg.setStyleSheet(STYLE)
        lay = QVBoxLayout(dlg)
        lay.addWidget(label(f"HỦY KẾT NỐI: {page['name']}", bold=True, size=15))
        lay.addWidget(label("Chỉ xóa liên kết khỏi Lovira, KHÔNG xóa Fanpage trên Facebook.",
                            color=COLORS["muted"]))
        lay.addWidget(label(f"• {local} lịch đăng trên máy sẽ bị xóa.\n"
                            f"• {remote} lịch đã lên Facebook KHÔNG được hủy từ thao tác này.\n"
                            "• SecretVault sẽ xóa token của Page này.", color=COLORS["amber"]))
        ack = QCheckBox("Tôi hiểu việc hủy kết nối và ảnh hưởng đến lịch đăng.")
        lay.addWidget(ack)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("Giữ kết nối")
        cancel.clicked.connect(dlg.reject)
        footer.addWidget(cancel)
        danger = QPushButton("Hủy kết nối")
        danger.setObjectName("DangerButton")
        danger.setEnabled(False)
        ack.toggled.connect(danger.setEnabled)
        danger.clicked.connect(dlg.accept)
        footer.addWidget(danger)
        lay.addLayout(footer)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            ok, message = self.repo.unlink_page(page_id, force=True)
            if not ok:
                QMessageBox.critical(self, "Gỡ liên kết thất bại", txt(message))
                return
            self.reload_pages()
            self.page_list_changed.emit()
            QMessageBox.information(self, "Đã hủy kết nối", f"Đã xóa liên kết '{page['name']}' khỏi Lovira.")
        except Exception:
            logger.exception("Unlink Page failed")
            QMessageBox.critical(self, "Không thể hủy kết nối", "Thao tác cơ sở dữ liệu gặp lỗi.")

    def _get_selected_page_id(self) -> Optional[str]:
        selected = self.table.currentRow()
        if selected < 0:
            return None
        item = self.table.item(selected, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _handle_verify_selected_token(self):
        page_id = self._get_selected_page_id()
        if not page_id:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Vui lòng chọn một Fanpage để kiểm tra token.")
            return

        page = self.lookup_page(page_id)
        if not page:
            return

        token = self.repo.get_page_token(page_id)
        if not token:
            QMessageBox.warning(self, "Không tìm thấy Token", f"Fanpage '{page['name']}' chưa có mã Access Token lưu trong Vault.")
            return

        try:
            token_info = self.fb.inspect_token(token)
            if token_info and token_info.is_valid:
                tasks = token_info.tasks if token_info.tasks else ["MANAGE", "CREATE_CONTENT"]
                has_publish_perm = any(t in ["CREATE_CONTENT", "MANAGE", "PUBLISH_TO_PAGE"] for t in tasks)
                new_status = "ready" if has_publish_perm else "insufficient_permissions"

                self.repo.update_page_status(page_id, new_status)
                self.profile_store.set_status(page_id, new_status)
                self.reload_pages()
                self.page_list_changed.emit()

                if new_status == "ready":
                    QMessageBox.information(self, "Token hợp lệ", f"Access Token của '{page['name']}' đang hoạt động tốt (Sẵn sàng đăng bài).")
                else:
                    QMessageBox.warning(self, "Thiếu quyền", f"Access Token của '{page['name']}' còn sống nhưng thiếu quyền CREATE_CONTENT.")
            else:
                self.repo.update_page_status(page_id, "token_expired")
                self.profile_store.set_status(page_id, "token_expired")
                self.reload_pages()
                self.page_list_changed.emit()
                QMessageBox.critical(self, "Token hết hạn", f"Access Token của '{page['name']}' đã hết hạn hoặc bị hủy quyền. Vui lòng cấp lại.")
        except Exception:
            self.verify_token(page_id)

    def _handle_unlink_page(self):
        page_id = self._get_selected_page_id()
        if not page_id:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Chọn một Fanpage để hủy kết nối.")
            return

        page = self.lookup_page(page_id)
        if not page:
            return

        counts = self.repo.check_page_schedules(page_id)
        local = counts.get("local_count", 0)
        remote = counts.get("remote_count", 0)

        warn_msg = f"Bạn có chắc chắn muốn gỡ liên kết Fanpage '{page['name']}' khỏi Lovira không?\n(Lưu ý: Fanpage thật trên Facebook KHÔNG bị xóa).\n\n"
        if local > 0 or remote > 0:
            warn_msg += (
                f"⚠️ CẢNH BÁO LỊCH ĐĂNG (AC-11):\n"
                f"• {local} lịch hẹn giờ trên máy chưa thực hiện sẽ bị hủy.\n"
                f"• {remote} lịch Facebook đã nhận vẫn tồn tại trên hệ thống Facebook.\n\n"
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

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ok, message = self.repo.unlink_page(page_id, force=True)
            if not ok:
                QMessageBox.critical(self, "Gỡ liên kết thất bại", txt(message))
                return
            self.reload_pages()
            self.page_list_changed.emit()
            QMessageBox.information(self, "Đã hủy kết nối", f"Đã xóa liên kết '{page['name']}' khỏi Lovira.")
        except Exception:
            logger.exception("Unlink Page failed")
            QMessageBox.critical(self, "Không thể hủy kết nối", "Thao tác cơ sở dữ liệu gặp lỗi.")
