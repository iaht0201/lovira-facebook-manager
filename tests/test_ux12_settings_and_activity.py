"""
Tests for UX-12 — Settings 2.0 & Activity Log 2.0
Verifies:
- Settings sections (General, Posting, Media, Backup, License, Diagnostics)
- Theme switching and Device ID copy
- SQLite backup execution (AC-22)
- Activity log 5-column display, level badges, filtering, search, and export
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QMessageBox, QFileDialog, QApplication

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.licensing.client import LicenseClient, OfflineFallbackLicenseBackend
from src.lovira.ui.views.settings_workspace import SettingsWorkspaceView
from src.lovira.ui.views.activity_workspace import ActivityWorkspaceView


def test_settings_workspace_sections_and_features(qapp, tmp_path):
    """DoD UX-12: Kiểm tra các card section và thao tác cài đặt."""
    db_file = tmp_path / "test_settings.db"
    db = DatabaseManager(db_file)
    runner = MigrationRunner(db)
    runner.apply_all()

    backend = OfflineFallbackLicenseBackend()
    license_client = LicenseClient(backend, "DEV-DEVICE-99", "FP-99")

    view = SettingsWorkspaceView(db_manager=db, license_client=license_client)

    # 1. Các controls chính tồn tại
    assert view.combo_theme is not None
    assert view.chk_tray.isChecked()
    assert view.spin_interval.value() == 15
    assert view.btn_backup is not None
    assert view.btn_restore is not None
    assert view.lbl_device_id.text() == "DEV-DEVICE-99"

    # 2. Thao tác sao chép Device ID
    with patch.object(QMessageBox, "information") as mock_info:
        view._copy_device_id()
        mock_info.assert_called_once()
        assert QApplication.clipboard().text() == "DEV-DEVICE-99"

    # 3. Thao tác sao lưu SQLite (AC-22)
    backup_file = tmp_path / "backup_out.db"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(backup_file), "")):
        with patch.object(QMessageBox, "information") as mock_backup_info:
            view._handle_backup()
            mock_backup_info.assert_called_once()
            assert backup_file.exists()


def test_activity_workspace_table_and_filtering(qapp, tmp_path):
    """DoD UX-12: Kiểm tra bảng nhật ký 5 cột, lọc phân hệ, tìm kiếm và xuất file."""
    db_file = tmp_path / "test_activity.db"
    db = DatabaseManager(db_file)
    runner = MigrationRunner(db)
    runner.apply_all()

    view = ActivityWorkspaceView(db_manager=db)

    # Bảng 5 cột chuẩn
    assert view.table.columnCount() == 5
    assert view.table.rowCount() >= 3

    # Cột 1 có badge Thành công / Thông tin
    assert "THÀNH CÔNG" in view.table.item(0, 1).text()

    # Thử tìm kiếm không khớp -> EmptyState
    view.search_filter.setText("Khóa tìm kiếm không tồn tại 12345")
    assert view.table_stack_layout.currentWidget() == view.empty_state_search

    # Xóa tìm kiếm -> quay lại bảng
    view.search_filter.clear()
    assert view.table_stack_layout.currentWidget() == view.table

    # Lọc phân hệ
    view.combo_filter.setCurrentIndex(view.combo_filter.findData("system"))
    assert view.table.rowCount() >= 1

    # Xuất file nhật ký
    export_file = tmp_path / "exported_log.txt"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(export_file), "")):
        with patch.object(QMessageBox, "information") as mock_exp_info:
            view._export_logs()
            mock_exp_info.assert_called_once()
            assert export_file.exists()
            content = export_file.read_text(encoding="utf-8")
            assert "LOVIRA ACTIVITY AUDIT LOG" in content
