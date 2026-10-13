# TIẾN ĐỘ THỰC HIỆN LOVIRA WORKSPACE 2.0 (UI/UX REDESIGN)

Tài liệu theo dõi từng task tuần tự theo mục 7 của `docs/UIUX_REDESIGN_PLANNING.md`.
Chỉ chuyển task tiếp theo khi task hiện tại đạt chuẩn **DONE** kèm bằng chứng nghiệm thu (test + screenshot).

---

## Danh mục Tasks & Trạng thái tổng quan

| Task | Tên nhiệm vụ | Mức độ | Phụ thuộc | Trạng thái | Hoàn thành |
|---|---|---|---|---|---|
| **UX-00** | Baseline Verification & Setup | P0 | — | **DONE** | 13/10/2026 |
| **UX-01** | Safety Fixes & P0 Audit | P0 | UX-00 | **DONE** | 13/10/2026 |
| **UX-02** | Design Tokens & Theme Engine | P1 | UX-00 | **DONE** | 13/10/2026 |
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
- **Scope and no-go changes:** Khởi tạo branch `feature/uiux-redesign-v2`, kiểm tra 75 tests baseline, tạo tài liệu quy chuẩn, chụp 11 snapshot screenshots.
- **Why DONE is justified:** Baseline SHA đã ghim, 75/75 tests passed, 11 ảnh baseline đã tạo, branch sẵn sàng.

---

### UX-01 — Safety Fixes & P0 Audit
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:17 — 13/10/2026 12:25
- **Baseline SHA / Commit SHA:** `487742d` / `c28d395`
- **Scope and no-go changes:** 
  - Khắc phục triệt để 3 rủi ro an toàn dữ liệu và quyền hạn (P0):
    1. `bulk_import_dialog.py`: Ngăn chặn hoàn toàn việc silent fallback sang tất cả Fanpage khi `Page_IDs` rỗng hoặc không khớp. Chỉ khi người dùng chỉ định rõ `ALL` mới đăng đa Page. Các dòng lỗi bị bỏ qua và cảnh báo trên preview table.
    2. `pages_workspace.py`: Khi kết nối direct Page token, nếu `inspect_token` thất bại hoặc không xác thực được qua mạng, lưu Page ở trạng thái `unverified` và không cấp quyền đăng bài, cảnh báo rõ ràng thay vì gán `ready`. Phân biệt rõ quyền `CREATE_CONTENT` / `MANAGE`.
    3. `app.py` & licensing: Loại bỏ hoàn toàn `MagicMock` trong production runtime. Hỗ trợ nạp `SupabaseAdapter` từ ENV hoặc fallback an toàn sang `OfflineFallbackLicenseBackend` (fail-closed, từ chối kích hoạt giả và AccessPolicyManager chặn các hành vi publish khi không có license).
- **Existing behavior to preserve:** SQLite WAL, SecretVault, ContentSnapshot, múi giờ Việt Nam, toàn bộ nghiệp vụ nền tảng.
- **Changed files:**
  - `src/lovira/licensing/client.py`: Thêm `OfflineFallbackLicenseBackend`.
  - `src/lovira/app.py`: Thay `MagicMock` bằng cấu hình Supabase thực hoặc `OfflineFallbackLicenseBackend`.
  - `src/lovira/ui/views/pages_workspace.py`: Chặn gán `status='ready'` khi token chưa được verify hoặc thiếu quyền.
  - `src/lovira/ui/views/bulk_import_dialog.py`: Kiểm tra nghiêm ngặt `Page_IDs`, loại bỏ silent fallback all pages, hiển thị cảnh báo trên preview table.
  - `tests/test_ux_enhancements.py`: Cập nhật assert status `unverified` khi token inspection trả về None.
  - `tests/test_ux01_safety_fixes.py`: Bộ test mới 4 test cases kiểm tra nghiêm ngặt 3 lỗi P0.
- **UI states implemented:**
  - Connect Page: Trạng thái cảnh báo khi token không xác thực được (`unverified`), trạng thái cảnh báo khi token thiếu quyền (`insufficient_permissions`).
  - Bulk Import Preview: Đánh dấu `⚠️ Thiếu Page ID` hoặc `⚠️ Page ID lạ`, vô hiệu hóa import khi không có dòng hợp lệ nào.
  - Licensing: Fail-closed rõ ràng khi chưa có backend hoặc offline.
- **Exact tests executed and results:**
  - `pytest tests/test_ux01_safety_fixes.py -v`: 4 passed in 1.67s.
  - `pytest tests/ -v`: 79 passed in 5.73s (toàn bộ 79/79 test suites xanh).
- **Security & concurrency self-review:**
  - Token Facebook không bao giờ bị log/leak, luôn lưu qua SecretVault.
  - Không thể vô tình đăng bài lên Fanpage không chủ ý do lỗi nhập liệu trong sheet Excel.
  - Không có backdoor/bypass license trong runtime desktop.
- **Why DONE is justified:** Cả 3 lỗi P0 chỉ định trong planning đã được sửa đúng root-cause, có test failure/regression bảo vệ, và toàn bộ 79 tests đều pass 100%.

---

### UX-02 — Design Tokens & Theme Engine
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:24 — 13/10/2026 12:28
- **Baseline SHA / Commit SHA:** `89e796c` / `4c34f19`
- **Scope and no-go changes:**
  - Xây dựng hệ thống Design Tokens chuẩn hóa cho Desktop PySide6 (`tokens.py`):
    - Dark Palette (Slate / Indigo) và Light Palette (WCAG AA).
    - Typography Segoe UI chuẩn desktop scale (28px hero, 22px title, 17px section, 14px body).
    - Thang đo khoảng cách Spacing & Radius (card 12px, button 8px, chip pill 999px).
    - Quản lý 2 chế độ Mật độ: Comfortable (mặc định) và Compact.
  - Xây dựng bộ Vector Icon Registry (`icons.py`) dạng SVG nội bộ (Lucide style) cho toàn bộ 10 route và action, render sắc nét ở mọi DPI qua `QSvgRenderer`.
  - Xây dựng `ThemeManager` (`theme_manager.py`) tạo QSS Stylesheet phân tầng động, **loại bỏ triệt để selector trùng lặp (khắc phục lỗi audit A-08)**.
  - Refactor `src/lovira/ui/theme.py` chuyển tiếp an toàn sang Theme Engine mới.
- **Existing behavior to preserve:** Toàn bộ component và style hiện có tiếp tục hoạt động trơn tru.
- **Changed files:**
  - `src/lovira/ui/design/tokens.py` (new)
  - `src/lovira/ui/design/icons.py` (new)
  - `src/lovira/ui/design/theme_manager.py` (new)
  - `src/lovira/ui/theme.py` (refactored)
  - `tests/test_ux02_tokens_and_theme.py` (new)
- **UI states implemented:** Dark Theme, Light Theme, Comfortable Density, Compact Density, vector icons render test.
- **Exact tests executed and results:**
  - `pytest tests/test_ux02_tokens_and_theme.py -v`: 5 passed in 0.23s.
  - `pytest tests/ -v`: 84 passed in 6.34s (toàn bộ 84/84 tests xanh).
- **Security & a11y self-review:**
  - Tương phản màu text_primary trên canvas/surface đạt >= 4.5:1 (chuẩn WCAG AA).
  - Focus ring bàn phím rõ ràng (`#9B93FA` / `#4F46E5`).
  - Linter duyệt toàn bộ rules QSS bảo đảm 0 duplicate selectors.
- **Why DONE is justified:** Design Tokens, SVG Icon registry và ThemeManager đều đã hoàn thành và được kiểm chứng qua 5 tests chuyên biệt + full suite 84 tests.
- **Next unblocked task:** UX-03 — Desktop Shell & 10 Routes.
