# TIẾN ĐỘ THỰC HIỆN LOVIRA WORKSPACE 2.0 (UI/UX REDESIGN)

Tài liệu theo dõi từng task tuần tự theo mục 7 của `docs/UIUX_REDESIGN_PLANNING.md`.
Chỉ chuyển task tiếp theo khi task hiện tại đạt chuẩn **DONE** kèm bằng chứng nghiệm thu (test + screenshot).

---

## Danh mục Tasks & Trạng thái tổng quan

| Task | Tên nhiệm vụ | Mức độ | Phụ thuộc | Trạng thái | Hoàn thành |
|---|---|---|---|---|---|
| **UX-00** | Baseline Verification & Setup | P0 | — | **DONE** | 13/10/2026 |
| **UX-01** | Safety Fixes & P0 Audit | P0 | UX-00 | TODO | — |
| **UX-02** | Design Tokens & Theme Engine | P1 | UX-00 | TODO | — |
| **UX-03** | Desktop Shell & 10 Routes | P0 | UX-02 | TODO | — |
| **UX-04** | Shared UI Primitives | P1 | UX-03 | TODO | — |
| **UX-05** | Dashboard 2.0 | P1 | UX-04 | TODO | — |
| **UX-06** | Fanpage Workspace 2.0 | P0 | UX-04, UX-01 | TODO | — |
| **UX-07** | Unified Post Composer 2.0 | P0 | UX-06 | TODO | — |
| **UX-08** | Schedule Workspace 2.0 | P0 | UX-07 | TODO | — |
| **UX-09** | Media Library & Video Downloader 2.0 | P1 | UX-07 | TODO | — |
| **UX-10** | Bulk Import Excel/CSV Wizard 2.0 | P0 | UX-06, UX-09 | TODO | — |
| **UX-11** | Comments & Interaction Workspace 2.0 | P1 | UX-04, UX-06 | TODO | — |
| **UX-12** | Settings & Activity Log Center 2.0 | P1 | UX-04 | TODO | — |
| **UX-13** | Final QA, Regression & Verification | P0 | UX-05..12 | TODO | — |

---

## Chi tiết từng Task

### UX-00 — Baseline Verification & Setup
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:00 — 13/10/2026 12:15
- **Baseline SHA:** `4959814229ce2d39c06332ab9ce91030fa6e04da`
- **Scope and no-go changes:** 
  - Khởi tạo nhánh `feature/uiux-redesign-v2` từ commit baseline `4959814`.
  - Chạy full test suite để xác minh 100% xanh trước khi can thiệp.
  - Thiết lập tài liệu tracking: `UIUX_REDESIGN_PLANNING.md`, `UIUX_PROGRESS.md`, `UIUX_VERIFICATION.md`.
  - Chụp snapshot baseline đầy đủ 11 màn hình/dialog hiện trạng của ứng dụng để làm đối chiếu.
  - Không thay đổi bất kỳ file mã nguồn logic nào trong task này.
- **Existing behavior to preserve:** Toàn bộ 75 tests pass và các workflow cơ bản đang chạy.
- **Changed files:**
  - `docs/UIUX_REDESIGN_PLANNING.md` (tài liệu quy hoạch)
  - `docs/UIUX_PROGRESS.md` (theo dõi tiến độ từng task)
  - `docs/UIUX_VERIFICATION.md` (bằng chứng kiểm thử)
  - `scripts/capture_baseline_ui.py` (script chụp ảnh baseline)
  - `docs/baseline_screenshots/*` (11 ảnh baseline)
- **UI states implemented:** Baseline snapshot các view & dialogs:
  - `01_overview_dashboard.png`: Dashboard 4 cards + quick actions + recent jobs
  - `02_fanpage_workspace.png`: Danh sách Page & actions
  - `03_video_workspace.png`: Download tab & media library
  - `04_schedule_workspace.png`: Danh sách lịch đặt & bộ lọc
  - `05_comments_placeholder.png`: Màn hình bình luận hiện trạng (placeholder QLabel)
  - `06_settings_workspace.png`: Cài đặt & backup SQLite
  - `07_post_composer_workspace.png`: Trình soạn thảo bài viết đầy đủ
  - `08_quick_post_dialog.png`: Popup tạo bài nhanh
  - `09_connect_page_dialog.png`: Dialog kết nối Fanpage (Direct token / User scan)
  - `10_bulk_import_dialog.png`: Dialog nhập file Excel/CSV
  - `11_license_dialog.png`: Dialog kích hoạt bản quyền
- **Exact tests executed and results:**
  - `pytest tests/ -v`: 75 passed in 5.24s.
- **Critical bugs identified for UX-01:**
  1. `src/lovira/app.py`: `MagicMock` khởi tạo license backend startup.
  2. `src/lovira/ui/views/pages_workspace.py`: Fallback gán `status='ready'` khi `inspect_token` thất bại/timeout.
  3. `src/lovira/ui/views/bulk_import_dialog.py`: Worker tự động fallback sang "tất cả Pages" khi `Page_IDs` rỗng hoặc không khớp.
  4. `src/lovira/ui/main_window.py`: Route comments bị rỗng; composer view thiếu nav entry trên sidebar.
- **Why DONE is justified:** Baseline SHA đã ghim, 75/75 tests passed, 11 ảnh baseline đã tạo, tài liệu tracking đầy đủ, branch `feature/uiux-redesign-v2` đã sẵn sàng.
- **Next unblocked task:** UX-01 — Safety Fixes & P0 Audit.
