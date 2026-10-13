"""
Lovira Workspace 2.0 — Global Page Context & Search Observable
Quản lý phạm vi Fanpage được chọn toàn cầu và tìm kiếm nhanh (Khắc phục A-03, A-04):
- Observable signal phát thông báo khi người dùng đổi Fanpage trên Header
- Không âm thầm sửa đổi bản nháp đang soạn bài (bảo toàn invariant BR)
"""

from typing import Optional, Dict, Any, List
from PySide6.QtCore import QObject, Signal, QTimer


class GlobalPageContext(QObject):
    """
    Context toàn cục quản lý phạm vi Page và Search trên Header.
    """

    page_scope_changed = Signal(object)      # Phát ra Optional[str]: None hoặc page_id
    page_changed = page_scope_changed        # Thuận tiện gọi
    search_submitted = Signal(str)            # Phát ra khi bấm Enter
    search_query_changed = Signal(str)        # Phát ra sau khi debounce 250ms

    _instance: Optional["GlobalPageContext"] = None

    def __init__(self):
        super().__init__()
        self._selected_page_id: Optional[str] = None
        self._search_query: str = ""

        # Timer debounce cho tìm kiếm
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(250)
        self._search_debounce_timer.timeout.connect(self._emit_debounced_search)

    @classmethod
    def get_instance(cls) -> "GlobalPageContext":
        if cls._instance is None:
            cls._instance = GlobalPageContext()
        return cls._instance

    @property
    def selected_page_id(self) -> Optional[str]:
        return self._selected_page_id

    def get_selected_page_id(self) -> Optional[str]:
        return self._selected_page_id

    @property
    def is_all_pages(self) -> bool:
        return self._selected_page_id is None

    def set_selected_page(self, page_id: Optional[str]) -> None:
        """Thay đổi phạm vi Page được chọn."""
        if self._selected_page_id != page_id:
            self._selected_page_id = page_id
            self.page_scope_changed.emit(self._selected_page_id)

    def set_search_query(self, query: str) -> None:
        """Cập nhật từ khóa tìm kiếm kèm debounce 250ms."""
        self._search_query = query.strip()
        self._search_debounce_timer.start()

    def submit_search(self, query: str) -> None:
        """Người dùng nhấn Enter tìm kiếm trực tiếp."""
        self._search_query = query.strip()
        self._search_debounce_timer.stop()
        self.search_submitted.emit(self._search_query)

    def _emit_debounced_search(self) -> None:
        self.search_query_changed.emit(self._search_query)
