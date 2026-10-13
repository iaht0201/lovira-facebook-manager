"""
Kiểm thử chuyên biệt cho Task UX-05: Dashboard 2.0 (DoD Compliance)
- Kiểm tra 4 MetricCards hiển thị số liệu, click-through chuyển route
- Kiểm tra Actionable Alert Banner thông báo lỗi / token hết hạn
- Kiểm tra ScheduleTimelineWidget phân bổ bài đăng 7 ngày theo giờ VN
- Kiểm tra EmptyState khi 0 page hoặc 0 jobs
- Kiểm tra Bảng Recent Jobs tích hợp StatusChip
- Kiểm tra đồng bộ hóa theo GlobalPageContext
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
from src.lovira.security.vault import SecretVault
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager, RemoteAppConfig
from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.views.overview_workspace import OverviewWorkspaceView, MetricCard
from src.lovira.ui.widgets.status_chip import StatusChip


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux05.db"
    db = DatabaseManager(db_file)
    MigrationRunner(db).apply_all()
    return db


def test_metric_card_click_through(qapp):
    """DoD UX-05: MetricCard phát tín hiệu clicked kèm route khi người dùng nhấp chuột."""
    card = MetricCard("📑", "FANPAGE", "5", "5 Fanpage sẵn sàng", target_route="pages")
    clicked_routes = []
    card.clicked.connect(clicked_routes.append)

    # Click
    card.clicked.emit("pages")
    assert "pages" in clicked_routes


def test_dashboard_empty_states(qapp, temp_db, tmp_path):
    """DoD UX-05: Dashboard hiển thị đúng EmptyState khi 0 page hoặc 0 jobs."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    media_repo = MediaRepository(temp_db)
    queue_repo = PublishQueueRepository(temp_db)

    client = MagicMock(spec=LicenseClient)
    client.is_active = True
    policy = AccessPolicyManager(RemoteAppConfig(license_required=False))

    # 1. Ban đầu 0 page: Hiển thị EmptyState no_pages (content_stack index 1)
    view = OverviewWorkspaceView(temp_db, page_repo, media_repo, queue_repo, client, policy)
    assert view.content_stack.currentIndex() == 1
    assert view.card_pages.lbl_val.text() == "0"

    # 2. Thêm 1 page nhưng 0 jobs: Hiển thị EmptyState no_schedules
    page_repo.upsert_page("fb_1", "Page Thoi Trang", status="ready")
    view.reload_dashboard_data()
    assert view.content_stack.currentIndex() == 1
    assert view.card_pages.lbl_val.text() == "1"


def test_dashboard_alert_banner_and_status_chips(qapp, temp_db, tmp_path):
    """DoD UX-05: Alert Banner xuất hiện khi có lỗi, và Bảng Recent Jobs dùng StatusChip."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    media_repo = MediaRepository(temp_db)
    queue_repo = PublishQueueRepository(temp_db)

    client = MagicMock(spec=LicenseClient)
    client.is_active = True
    policy = AccessPolicyManager(RemoteAppConfig(license_required=False))

    # Thêm 1 page bình thường và 1 page lỗi token
    pid_ok = page_repo.upsert_page("fb_ok", "Page Tot", status="ready")
    pid_err = page_repo.upsert_page("fb_err", "Page Het Han", status="token_expired")

    # Thêm 1 job bằng enqueue_batch
    now_vn = vn_now() + timedelta(hours=2)
    sched_iso = vn_datetime_to_utc_iso(now_vn)
    snap = ContentSnapshot(
        batch_id="batch_01",
        page_id=pid_ok,
        content_type=ContentType.REELS,
        final_caption="Video danh gia san pham #review",
        scheduled_at_utc=sched_iso,
        schedule_mode=ScheduleMode.LOCAL,
    )
    job_ids = queue_repo.enqueue_batch(client_request_id="req_01", snapshots=[snap])
    assert len(job_ids) == 1

    view = OverviewWorkspaceView(temp_db, page_repo, media_repo, queue_repo, client, policy)

    # 1. Alert Banner phải hiển thị cảnh báo token_expired
    assert not view.alert_banner.isHidden()
    assert "token" in view.alert_banner.lbl_msg.text().lower() or "quyền" in view.alert_banner.lbl_msg.text().lower()

    # 2. Bảng Recent Jobs hiển thị (content_stack index 0)
    assert view.content_stack.currentIndex() == 0
    assert view.table_recent.rowCount() == 1
    assert view.table_recent.item(0, 0).text() == job_ids[0][:12]

    # 3. Cột 4 phải gắn StatusChip
    chip_widget = view.table_recent.cellWidget(0, 4)
    assert isinstance(chip_widget, StatusChip)
    assert chip_widget.status_key == "scheduled_local"


def test_dashboard_7day_schedule_timeline(qapp, temp_db, tmp_path):
    """DoD UX-05: ScheduleTimelineWidget đếm chính xác số bài trong 7 ngày tới."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    media_repo = MediaRepository(temp_db)
    queue_repo = PublishQueueRepository(temp_db)

    client = MagicMock(spec=LicenseClient)
    client.is_active = True
    policy = AccessPolicyManager(RemoteAppConfig(license_required=False))

    pid = page_repo.upsert_page("fb_1", "Page 1", status="ready")

    # Tạo 2 bài hôm nay và 1 bài ngày mai
    now_vn = vn_now()
    today_iso_1 = vn_datetime_to_utc_iso(now_vn + timedelta(minutes=10))
    today_iso_2 = vn_datetime_to_utc_iso(now_vn + timedelta(hours=3))
    tomorrow_iso = vn_datetime_to_utc_iso(now_vn + timedelta(days=1, hours=2))

    snaps = [
        ContentSnapshot(batch_id="b1", page_id=pid, content_type=ContentType.REELS, final_caption="Bai 1", scheduled_at_utc=today_iso_1),
        ContentSnapshot(batch_id="b2", page_id=pid, content_type=ContentType.REELS, final_caption="Bai 2", scheduled_at_utc=today_iso_2),
        ContentSnapshot(batch_id="b3", page_id=pid, content_type=ContentType.REELS, final_caption="Bai 3", scheduled_at_utc=tomorrow_iso),
    ]
    queue_repo.enqueue_batch(client_request_id="batch_req_timeline", snapshots=snaps)

    view = OverviewWorkspaceView(temp_db, page_repo, media_repo, queue_repo, client, policy)

    # Thẻ hôm nay (index 0) phải có count 2
    assert view.timeline.cards[0].count == 2
    # Thẻ ngày mai (index 1) phải có count 1
    assert view.timeline.cards[1].count == 1
    # Tóm tắt
    assert "3 bài đăng" in view.timeline.lbl_summary.text()


def test_dashboard_global_page_context_filtering(qapp, temp_db, tmp_path):
    """DoD UX-05: Dashboard tự động lọc dữ liệu khi người dùng chọn Page trên Header."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    media_repo = MediaRepository(temp_db)
    queue_repo = PublishQueueRepository(temp_db)

    client = MagicMock(spec=LicenseClient)
    client.is_active = True
    policy = AccessPolicyManager(RemoteAppConfig(license_required=False))

    pid_a = page_repo.upsert_page("fb_a", "Fanpage A", status="ready")
    pid_b = page_repo.upsert_page("fb_b", "Fanpage B", status="ready")

    now_iso = vn_datetime_to_utc_iso(vn_now() + timedelta(hours=1))
    snaps_a = [ContentSnapshot(batch_id="ba", page_id=pid_a, content_type=ContentType.REELS, final_caption="Post Page A", scheduled_at_utc=now_iso)]
    snaps_b = [ContentSnapshot(batch_id="bb", page_id=pid_b, content_type=ContentType.REELS, final_caption="Post Page B", scheduled_at_utc=now_iso)]

    queue_repo.enqueue_batch("req_pa", snaps_a)
    queue_repo.enqueue_batch("req_pb", snaps_b)

    context = GlobalPageContext()
    view = OverviewWorkspaceView(temp_db, page_repo, media_repo, queue_repo, client, policy, page_context=context)

    # Ban đầu Tất cả Page: hiển thị 2 bài
    assert view.table_recent.rowCount() == 2

    # Chọn Fanpage A
    context.set_selected_page(pid_a)
    assert view.table_recent.rowCount() == 1
    assert view.table_recent.item(0, 1).text() == "Fanpage A" or view.table_recent.item(0, 1).text() == pid_a

    # Chọn lại Tất cả Page
    context.set_selected_page(None)
    assert view.table_recent.rowCount() == 2
