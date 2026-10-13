# Hướng dẫn thiết lập Supabase Backend cho Lovira-Facebook Manager

## 1. Mục đích
Hệ thống backend quản lý:
- Bản quyền (Licenses) và thiết bị (Devices).
- Thu hồi phiên tức thời khi máy khác kích hoạt cùng License key (Atomic session generation).
- Công tắc bật/tắt chế độ miễn phí từ xa (`license_required = false`).
- Cấu hình thông tin hỗ trợ và hạn mức toàn cục.

## 2. Các bước triển khai trên Supabase
1. Đăng nhập vào [Supabase Dashboard](https://supabase.com/dashboard).
2. Tạo Project mới (hoặc chọn project hiện có).
3. Mở mục **SQL Editor**, tạo truy vấn mới và dán toàn bộ nội dung file `supabase/migrations/20261013000001_initial_supabase_schema.sql`.
4. Nhấn **Run** để khởi tạo bảng, kích hoạt RLS và tạo các hàm stored procedure (RPC).
5. Thêm cấu hình khởi tạo ban đầu:
   ```sql
   INSERT INTO public.app_config (id, license_required, session_ttl_seconds)
   VALUES (1, true, 180)
   ON CONFLICT (id) DO NOTHING;
   ```

## 3. Tạo License Key cho khách hàng
Để cấp một key mới, chạy câu lệnh SQL sau:
```sql
-- Ví dụ: Cấp key "LOVI-VIP1-2026-8888", hạn dùng 1 năm
INSERT INTO public.licenses (key_digest, key_hint, status, expires_at, max_sessions)
VALUES (
    encode(digest('LOVI-VIP1-2026-8888', 'sha256'), 'hex'),
    '8888',
    'active',
    now() + interval '1 year',
    1
);
```

## 4. Bảo mật (Section 14 & 15)
- RLS được bật cho mọi bảng. Client Anon desktop chỉ có quyền đọc `app_config`.
- Mọi thao tác kích hoạt và heartbeat bắt buộc phải đi qua các hàm `SECURITY DEFINER` RPC (`activate_license_rpc`, `heartbeat_session_rpc`).
- Không đóng gói `service_role` secret vào client desktop.
