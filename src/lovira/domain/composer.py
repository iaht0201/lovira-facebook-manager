"""
Lovira-Facebook Manager
Domain Model Soạn bài, Quản lý Nháp & Content Snapshot (Composer Domain)
- Hỗ trợ loại nội dung: Text, Video, Reels
- Soạn chung và ghi đè caption riêng từng Page (Section 7.1)
- Tạo bản chụp nội dung (Content Snapshot) bất biến độc lập với nháp gốc (Section 7.2, AC-19)
- Tắt công tắc hẹn giờ KHÔNG tự động đăng bài, giữ nguyên dữ liệu giờ đã nhập (AC-06, AC-41)
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from .timezone import vn_now, vn_datetime_to_utc_iso, validate_schedule_time


class ContentType(str, Enum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    REELS = "reels"


class ScheduleMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass
class TargetPageConfig:
    page_id: str
    caption_override: Optional[str] = None
    extra_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentSnapshot:
    """Bản chụp nội dung đóng băng bất biến cho tác vụ đăng (Section 7.2)."""
    batch_id: str
    page_id: str
    content_type: ContentType
    final_caption: str
    primary_media_id: Optional[str] = None
    media_checksum: Optional[str] = None
    media_path: Optional[str] = None
    scheduled_at_utc: str = ""
    schedule_mode: ScheduleMode = ScheduleMode.LOCAL
    timezone: str = "Asia/Ho_Chi_Minh"
    revision: int = 1
    created_at_utc: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ContentSnapshot":
        data = json.loads(json_str)
        data["content_type"] = ContentType(data["content_type"])
        data["schedule_mode"] = ScheduleMode(data["schedule_mode"])
        return cls(**data)


@dataclass
class PostComposerState:
    """Trạng thái form soạn bài trên giao diện desktop."""
    content_type: ContentType = ContentType.VIDEO
    general_caption: str = ""
    media_ids: List[str] = field(default_factory=list)
    media_path: Optional[str] = None
    media_checksum: Optional[str] = None
    selected_page_ids: List[str] = field(default_factory=list)
    page_overrides: Dict[str, TargetPageConfig] = field(default_factory=dict)
    is_scheduled: bool = False
    scheduled_year: int = 0
    scheduled_month: int = 0
    scheduled_day: int = 0
    scheduled_hour: int = 0
    scheduled_minute: int = 0
    schedule_mode: ScheduleMode = ScheduleMode.LOCAL
    draft_id: Optional[str] = None
    revision: int = 1

    def toggle_schedule(self, enable: bool) -> None:
        """
        Bật/tắt công tắc hẹn giờ:
        - Tắt công tắc KHÔNG làm mất ngày giờ đã nhập trước đó (AC-06).
        - Tắt công tắc KHÔNG tự động đăng bài ngay (AC-41).
        """
        self.is_scheduled = enable

    def set_override_caption(self, page_id: str, caption: Optional[str]) -> None:
        """Thiết lập caption riêng cho 1 Page mà không ảnh hưởng các Page khác."""
        if page_id not in self.page_overrides:
            self.page_overrides[page_id] = TargetPageConfig(page_id=page_id, caption_override=caption)
        else:
            self.page_overrides[page_id].caption_override = caption

    def get_effective_caption(self, page_id: str) -> str:
        """Lấy caption thực tế cho Page (nếu có override thì dùng override, ngược lại dùng caption chung)."""
        override = self.page_overrides.get(page_id)
        if override and override.caption_override is not None and override.caption_override.strip() != "":
            return override.caption_override
        return self.general_caption

    def validate(self) -> Tuple[bool, str]:
        """Kiểm tra tính hợp lệ trước khi đăng hoặc đặt lịch."""
        if not self.selected_page_ids:
            return False, "Vui lòng chọn ít nhất một Fanpage đích."

        if self.content_type in (ContentType.VIDEO, ContentType.REELS):
            if not self.media_path and not self.media_ids:
                return False, f"Loại bài {self.content_type.value} yêu cầu phải có file video đính kèm."

        if self.content_type == ContentType.TEXT and not self.general_caption.strip():
            return False, "Vui lòng nhập nội dung văn bản bài viết."

        return True, "Hợp lệ"

    def create_snapshots(self, scheduled_at_utc: str = "") -> List[ContentSnapshot]:
        """Đóng băng dữ liệu thành danh sách ContentSnapshot độc lập cho từng Page đích (Section 7.2)."""
        valid, msg = self.validate()
        if not valid:
            raise ValueError(msg)

        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        now_utc = vn_datetime_to_utc_iso(vn_now())
        target_schedule_utc = scheduled_at_utc if (scheduled_at_utc or self.is_scheduled) else now_utc

        snapshots: List[ContentSnapshot] = []
        for page_id in self.selected_page_ids:
            caption = self.get_effective_caption(page_id)
            primary_media = self.media_ids[0] if self.media_ids else None

            snap = ContentSnapshot(
                batch_id=batch_id,
                page_id=page_id,
                content_type=self.content_type,
                final_caption=caption,
                primary_media_id=primary_media,
                media_checksum=self.media_checksum,
                media_path=self.media_path,
                scheduled_at_utc=target_schedule_utc,
                schedule_mode=self.schedule_mode,
                revision=self.revision,
                created_at_utc=now_utc,
            )
            snapshots.append(snap)
        return snapshots
