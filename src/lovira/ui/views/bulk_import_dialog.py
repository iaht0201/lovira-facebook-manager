"""
Lovira-Facebook Manager
Hộp thoại Nhập Lịch đăng Hàng loạt từ File Sheet Mẫu Excel / CSV (BulkImportDialog)
- Xuất file sheet mẫu (.xlsx / .csv) chuẩn hóa (Tiêu đề, Caption, Link video/File, Page IDs, Giờ VN, Loại đăng)
- Nhập dữ liệu tự động: Hỗ trợ link video TikTok/Douyin (tự tải video nền) hoặc file video trên máy
- Lên lịch hàng loạt nguyên tử vào PublishQueueRepository theo giờ Việt Nam (UTC+7)
"""

import os
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QFrame,
)

from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.domain.composer import ContentSnapshot
from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso, create_vn_datetime


class BulkImportWorker(QThread):
    """Worker luồng riêng xử lý import và tự động tải video từ link."""

    progress_updated = Signal(int, int, str)
    finished_success = Signal(int, int)
    finished_error = Signal(str)

    def __init__(
        self,
        rows: List[Dict[str, str]],
        page_repo: PageRepository,
        queue_repo: PublishQueueRepository,
        media_repo: MediaRepository,
        downloader: VideoDownloader,
        media_processor: MediaProcessor,
        download_dir: Path,
    ):
        super().__init__()
        self.rows = rows
        self.page_repo = page_repo
        self.queue_repo = queue_repo
        self.media_repo = media_repo
        self.downloader = downloader
        self.media_processor = media_processor
        self.download_dir = download_dir

    def run(self) -> None:
        total = len(self.rows)
        success_count = 0
        all_pages = self.page_repo.list_pages()
        page_id_map = {p["facebook_page_id"]: p["id"] for p in all_pages}
        all_internal_ids = [p["id"] for p in all_pages]

        try:
            for idx, row in enumerate(self.rows, start=1):
                title = row.get("TieuDe", "").strip()
                caption = row.get("NoiDung_Caption", "").strip()
                video_src = row.get("Video_Link_Hoac_File", "").strip()
                page_ids_str = row.get("Page_IDs", "").strip()
                time_str = row.get("NgayGioDang_VN", "").strip()
                post_type = row.get("LoaiDang", "reels").strip().lower() or "reels"

                self.progress_updated.emit(idx, total, f"Đang xử lý dòng {idx}/{total}: {title or 'Bài viết'}")

                # 1. Xác định Page đích (UX-01 P0: CẤM silent fallback sang toàn bộ Page)
                target_internal_page_ids = []
                raw_page_tokens = [p.strip() for p in page_ids_str.split(",") if p.strip()]

                if any(p.upper() in ["ALL", "TAT_CA", "TẤT_CẢ", "TATCA", "*"] for p in raw_page_tokens):
                    # Chỉ đăng lên tất cả Page khi người dùng chỉ định tường minh từ khóa ALL/TAT_CA
                    target_internal_page_ids = list(all_internal_ids)
                elif raw_page_tokens:
                    for fb_pid in raw_page_tokens:
                        if fb_pid in page_id_map:
                            target_internal_page_ids.append(page_id_map[fb_pid])
                else:
                    # Page_IDs rỗng: Tuyệt đối không fallback sang all_internal_ids
                    pass

                if not target_internal_page_ids:
                    # Hàng không có Page ID hợp lệ -> bỏ qua an toàn, không tạo job rác
                    continue

                # 2. Xử lý video (từ link hoặc từ file local)
                local_video_path = None
                media_id = None

                if video_src.startswith("http://") or video_src.startswith("https://"):
                    # Tải video từ link TikTok/Douyin/Bilibili
                    self.progress_updated.emit(idx, total, f"Đang tải video dòng {idx}/{total} từ link...")
                    try:
                        saved_path = self.downloader.download(video_src, self.download_dir)
                        local_video_path = str(saved_path)
                        probe = self.media_processor.inspect_video(Path(saved_path))
                        checksum = self.media_processor.calculate_sha256(Path(saved_path))
                        media_id = self.media_repo.add_media_asset(
                            local_path=Path(saved_path),
                            checksum=checksum,
                            size_bytes=os.path.getsize(saved_path) if os.path.exists(saved_path) else 0,
                            duration=probe.duration if probe else 0.0,
                            source_platform="online_link",
                            source_url=video_src,
                            width=probe.width if probe else 0,
                            height=probe.height if probe else 0,
                        )
                    except Exception as dl_err:
                        # Ghi nhận lỗi nhưng không dừng toàn bộ tiến trình
                        continue
                elif video_src and os.path.exists(video_src):
                    local_video_path = video_src
                    probe = self.media_processor.inspect_video(Path(video_src))
                    checksum = self.media_processor.calculate_sha256(Path(video_src))
                    media_id = self.media_repo.add_media_asset(
                        local_path=Path(video_src),
                        checksum=checksum,
                        size_bytes=os.path.getsize(video_src),
                        duration=probe.duration if probe else 0.0,
                        source_platform="local_file",
                        source_url=video_src,
                        width=probe.width if probe else 0,
                        height=probe.height if probe else 0,
                    )

                # 3. Phân tích thời gian hẹn giờ
                sched_utc = None
                sched_mode = "instant"
                if time_str:
                    try:
                        # Hỗ trợ định dạng: YYYY-MM-DD HH:MM hoặc DD/MM/YYYY HH:MM
                        dt_vn = None
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
                            try:
                                dt_vn = datetime.strptime(time_str, fmt)
                                break
                            except ValueError:
                                pass
                        if dt_vn:
                            dt_vn_tz = create_vn_datetime(dt_vn.year, dt_vn.month, dt_vn.day, dt_vn.hour, dt_vn.minute, dt_vn.second)
                            if dt_vn_tz > vn_now():
                                sched_utc = vn_datetime_to_utc_iso(dt_vn_tz)
                                sched_mode = "scheduled_local"
                    except Exception:
                        pass

                # 4. Tạo ContentSnapshot & Enqueue
                import uuid
                batch_id = f"batch_{uuid.uuid4().hex[:10]}"
                now_utc = vn_datetime_to_utc_iso(vn_now())
                target_sched_utc = sched_utc if sched_utc else now_utc

                from src.lovira.domain.composer import ContentType, ScheduleMode

                snapshots = []
                for pid in target_internal_page_ids:
                    snap = ContentSnapshot(
                        batch_id=batch_id,
                        page_id=pid,
                        content_type=ContentType.REELS if local_video_path else ContentType.TEXT,
                        final_caption=caption,
                        primary_media_id=media_id,
                        media_path=local_video_path,
                        scheduled_at_utc=target_sched_utc,
                        schedule_mode=ScheduleMode.LOCAL,
                    )
                    snapshots.append(snap)

                client_req_id = f"import_{uuid.uuid4().hex[:12]}"
                self.queue_repo.enqueue_batch(
                    client_request_id=client_req_id,
                    snapshots=snapshots,
                )
                success_count += 1

            self.finished_success.emit(success_count, total)
        except Exception as e:
            self.finished_error.emit(str(e))


class BulkImportDialog(QDialog):
    """Hộp thoại Nhập Lịch đăng từ Sheet mẫu Excel / CSV."""

    import_completed = Signal()

    def __init__(
        self,
        page_repo: PageRepository,
        queue_repo: PublishQueueRepository,
        media_repo: MediaRepository,
        downloader: VideoDownloader,
        media_processor: MediaProcessor,
        download_dir: Path,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.page_repo = page_repo
        self.queue_repo = queue_repo
        self.media_repo = media_repo
        self.downloader = downloader
        self.media_processor = media_processor
        self.download_dir = download_dir

        self.loaded_rows: List[Dict[str, str]] = []
        self.worker: Optional[BulkImportWorker] = None

        self.setWindowTitle("Nhập Lịch đăng Hàng loạt từ Sheet Excel / CSV")
        self.resize(920, 620)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header toolbar
        top_frame = QFrame()
        top_frame.setObjectName("cardFrame")
        top_layout = QHBoxLayout(top_frame)

        title_box = QVBoxLayout()
        lbl_title = QLabel("NHẬP NỘI DUNG VÀ LÊN LỊCH HÀNG LOẠT")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #818CF8;")
        lbl_desc = QLabel("Cho phép import file Excel/CSV chứa tiêu đề, caption, link video TikTok/Douyin và giờ đăng VN.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        btn_template = QPushButton("📄 Tải Sheet mẫu Excel (.xlsx)")
        btn_template.clicked.connect(self._export_template)
        top_layout.addWidget(btn_template)

        btn_load_file = QPushButton("📂 Chọn file để Nhập")
        btn_load_file.setObjectName("primaryButton")
        btn_load_file.clicked.connect(self._select_file_to_import)
        top_layout.addWidget(btn_load_file)

        layout.addWidget(top_frame)

        # Bảng xem trước dữ liệu (Preview Table)
        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(6)
        self.table_preview.setHorizontalHeaderLabels([
            "Tiêu đề", "Nội dung / Caption", "Video (Link hoặc File)", "Page IDs đích", "Giờ Đăng VN", "Loại"
        ])
        self.table_preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_preview.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table_preview)

        # Thanh tiến độ xử lý
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Sẵn sàng nhập file.")
        self.lbl_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        # Nút hành động dưới cùng
        bottom_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Đóng")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_start_import = QPushButton("🚀 Bắt đầu Xử lý & Lên lịch hàng loạt")
        self.btn_start_import.setObjectName("successButton")
        self.btn_start_import.setEnabled(False)
        self.btn_start_import.clicked.connect(self._start_import_process)

        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_cancel)
        bottom_row.addWidget(self.btn_start_import)
        layout.addLayout(bottom_row)

    def _export_template(self) -> None:
        """Xuất file mẫu Excel (.xlsx) kèm hướng dẫn chi tiết."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu file Sheet mẫu Excel", "Mau_Dang_Bai_Lovira.xlsx", "Excel Files (*.xlsx);;CSV Files (*.csv)"
        )
        if not file_path:
            return

        sample_data = [
            {
                "TieuDe": "Video hài hước buổi sáng",
                "NoiDung_Caption": "Chúc cả nhà ngày mới tràn đầy năng lượng! #reels #xuhuong #haihuoc",
                "Video_Link_Hoac_File": "https://www.tiktok.com/@dachshund_tieumuoi/video/7694340197269425429",
                "Page_IDs": "",
                "NgayGioDang_VN": (vn_now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
                "LoaiDang": "reels",
            },
            {
                "TieuDe": "Review sản phẩm mới",
                "NoiDung_Caption": "Mẫu sản phẩm hot nhất tuần này nhé cả nhà! Xem chi tiết tại link bio.",
                "Video_Link_Hoac_File": "D:/Videos/sample.mp4",
                "Page_IDs": "100085942398412",
                "NgayGioDang_VN": (vn_now() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M"),
                "LoaiDang": "reels",
            },
            {
                "TieuDe": "Chia sẻ kinh nghiệm làm vườn",
                "NoiDung_Caption": "Mẹo chăm sóc cây cảnh mùa hè không bị héo lá.",
                "Video_Link_Hoac_File": "https://www.douyin.com/video/71234567890",
                "Page_IDs": "",
                "NgayGioDang_VN": "",
                "LoaiDang": "reels",
            },
        ]

        try:
            if file_path.endswith(".xlsx"):
                import pandas as pd
                df = pd.DataFrame(sample_data)
                df.to_excel(file_path, index=False)
            else:
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=list(sample_data[0].keys()))
                    writer.writeheader()
                    writer.writerows(sample_data)

            QMessageBox.information(
                self,
                "Xuất file thành công",
                f"Đã tạo file mẫu thành công tại:\n{file_path}\n\nBạn có thể mở file này ra chỉnh sửa rồi bấm 'Chọn file để Nhập'!",
            )
        except Exception as e:
            QMessageBox.critical(self, "Lỗi xuất file", f"Không thể xuất file mẫu:\n{e}")

    def _select_file_to_import(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Excel hoặc CSV", "", "Spreadsheets (*.xlsx *.xls *.csv)"
        )
        if not file_path:
            return

        self.loaded_rows.clear()
        try:
            if file_path.endswith(".csv"):
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        self.loaded_rows.append(r)
            else:
                import pandas as pd
                df = pd.read_excel(file_path)
                # Chuyển nan thành chuỗi rỗng
                df = df.fillna("")
                self.loaded_rows = df.to_dict(orient="records")

            if not self.loaded_rows:
                QMessageBox.warning(self, "File rỗng", "Không tìm thấy dòng dữ liệu nào trong file.")
                return

            # Hiển thị lên bảng preview (kèm kiểm tra hợp lệ Page ID - UX-01)
            all_pages = self.page_repo.list_pages()
            known_fb_ids = {p["facebook_page_id"] for p in all_pages}
            valid_count = 0
            invalid_count = 0

            self.table_preview.setRowCount(len(self.loaded_rows))
            for row_idx, r in enumerate(self.loaded_rows):
                self.table_preview.setItem(row_idx, 0, QTableWidgetItem(str(r.get("TieuDe", ""))))
                self.table_preview.setItem(row_idx, 1, QTableWidgetItem(str(r.get("NoiDung_Caption", ""))))
                self.table_preview.setItem(row_idx, 2, QTableWidgetItem(str(r.get("Video_Link_Hoac_File", ""))))

                raw_page_ids = str(r.get("Page_IDs", "")).strip()
                tokens = [p.strip() for p in raw_page_ids.split(",") if p.strip()]
                is_all = any(t.upper() in ["ALL", "TAT_CA", "TẤT_CẢ", "TATCA", "*"] for t in tokens)
                matched = [t for t in tokens if t in known_fb_ids]

                page_item = QTableWidgetItem(raw_page_ids)
                if is_all:
                    page_item.setText("Tất cả Page (ALL)")
                    valid_count += 1
                elif matched:
                    valid_count += 1
                else:
                    invalid_count += 1
                    if not raw_page_ids:
                        page_item.setText("⚠️ Thiếu Page ID")
                    else:
                        page_item.setText(f"⚠️ {raw_page_ids} (Không tìm thấy)")

                self.table_preview.setItem(row_idx, 3, page_item)
                self.table_preview.setItem(row_idx, 4, QTableWidgetItem(str(r.get("NgayGioDang_VN", ""))))
                self.table_preview.setItem(row_idx, 5, QTableWidgetItem(str(r.get("LoaiDang", "reels"))))

            self.btn_start_import.setEnabled(valid_count > 0)
            if invalid_count > 0:
                self.lbl_status.setText(
                    f"Đã nạp {len(self.loaded_rows)} dòng ({valid_count} hợp lệ, {invalid_count} dòng thiếu/sai Page ID sẽ bị bỏ qua an toàn)."
                )
            else:
                self.lbl_status.setText(f"Đã nạp {len(self.loaded_rows)} bài viết hợp lệ. Nhấn nút bên dưới để tiến hành lên lịch!")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", f"Không thể đọc file:\n{e}")

    def _start_import_process(self) -> None:
        if not self.loaded_rows:
            return

        self.btn_start_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Đang khởi động tiến trình import...")

        self.worker = BulkImportWorker(
            rows=self.loaded_rows,
            page_repo=self.page_repo,
            queue_repo=self.queue_repo,
            media_repo=self.media_repo,
            downloader=self.downloader,
            media_processor=self.media_processor,
            download_dir=self.download_dir,
        )
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.finished_success.connect(self._on_success)
        self.worker.finished_error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int, status_msg: str) -> None:
        percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(status_msg)

    def _on_success(self, success_count: int, total: int) -> None:
        if self.worker:
            try:
                self.worker.wait(3000)
            except RuntimeError:
                pass
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"✅ Hoàn thành: Đã nhập {success_count}/{total} bài viết vào hàng đợi.")
        self.btn_start_import.setEnabled(True)
        QMessageBox.information(
            self,
            "Nhập thành công",
            f"Đã lên lịch thành công cho {success_count} bài viết/Reels!\nCác tác vụ đã được đưa vào Lịch đăng tự động.",
        )
        self.import_completed.emit()
        self.accept()

    def _on_error(self, err_msg: str) -> None:
        if self.worker:
            try:
                self.worker.wait(3000)
            except RuntimeError:
                pass
        self.btn_start_import.setEnabled(True)
        self.lbl_status.setText(f"❌ Lỗi: {err_msg}")
        QMessageBox.critical(self, "Lỗi trong tiến trình import", f"Có lỗi xảy ra:\n{err_msg}")

    def closeEvent(self, event) -> None:
        """Đảm bảo dừng worker an toàn trước khi đóng dialog."""
        if self.worker:
            try:
                if self.worker.isRunning():
                    self.worker.quit()
                    self.worker.wait(3000)
            except RuntimeError:
                pass
        super().closeEvent(event)
