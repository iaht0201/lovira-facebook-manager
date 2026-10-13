# Lovira-Facebook Manager

Tài liệu phân tích chức năng và thiết kế kỹ thuật đề xuất

| Thuộc tính | Nội dung |
| --- | --- |
| Phiên bản tài liệu | 0.2 — đã tự phản biện thiết kế, chỉnh sửa UX và bổ sung tình huống lỗi |
| Ngày lập | 13/10/2026 |
| Ngôn ngữ giao diện | Tiếng Việt |
| Loại sản phẩm | Ứng dụng desktop Python, có cửa sổ riêng |
| Hệ điều hành mục tiêu | Windows và Linux |
| Múi giờ nghiệp vụ | Việt Nam — `Asia/Ho_Chi_Minh` |
| Repo tham khảo | `sonnpham24/facebook-automation` |
| Trạng thái | Chưa triển khai; chưa kiểm thử với tài khoản Facebook hoặc Supabase của chủ sản phẩm |

**Yêu cầu đã xác nhận: đây là tool cài trên máy.** Người dùng quản lý Page, xem video, soạn bài và đặt lịch ngay trong ứng dụng. Không yêu cầu mở giao diện quản lý trên trình duyệt. Khi chọn kết nối Facebook bằng OAuth, ứng dụng có thể mở trình duyệt hệ thống để cấp quyền rồi quay lại tool.

Tài liệu phân biệt bốn loại thông tin:

- **Đã xác nhận:** yêu cầu được người dùng nêu rõ.
- **Đề xuất:** phương án thiết kế để xem xét, chưa phải lựa chọn đã được duyệt.
- **Cần chốt:** còn thiếu thông tin có thể làm thay đổi thiết kế.
- **Phụ thuộc nền tảng:** phải xác nhận bằng quyền, API và kiểm thử thực tế tại thời điểm triển khai.

Các giá trị cấu hình, tên bảng, API nội bộ và tiêu chí hiệu năng bên dưới là đặc tả đề xuất; không phải mô tả một phần mềm đã hoàn thiện.

**Mục lục**

- [1. Mục tiêu và phạm vi](#1-mục-tiêu-và-phạm-vi)
- [2. Đánh giá repo tham khảo](#2-đánh-giá-repo-tham-khảo)
- [3. Kiến trúc desktop đề xuất](#3-kiến-trúc-desktop-đề-xuất)
- [4. Thiết kế giao diện và điều hướng](#4-thiết-kế-giao-diện-và-điều-hướng)
- [5. Tài khoản Facebook và quản lý Page](#5-tài-khoản-facebook-và-quản-lý-page)
- [6. Quản lý bài viết, Reels và bình luận](#6-quản-lý-bài-viết-reels-và-bình-luận)
- [7. Soạn bài và đăng lên nhiều Page](#7-soạn-bài-và-đăng-lên-nhiều-page)
- [8. Tải video và thư viện media](#8-tải-video-và-thư-viện-media)
- [9. Hẹn giờ theo múi giờ Việt Nam](#9-hẹn-giờ-theo-múi-giờ-việt-nam)
- [10. Chạy nền và sử dụng tài nguyên](#10-chạy-nền-và-sử-dụng-tài-nguyên)
- [11. License, thiết bị và đăng nhập](#11-license-thiết-bị-và-đăng-nhập)
- [12. Chế độ miễn phí và cấu hình Supabase](#12-chế-độ-miễn-phí-và-cấu-hình-supabase)
- [13. Thiết kế dữ liệu local](#13-thiết-kế-dữ-liệu-local)
- [14. Thiết kế dữ liệu và API license](#14-thiết-kế-dữ-liệu-và-api-license)
- [15. Bảo mật và quyền riêng tư](#15-bảo-mật-và-quyền-riêng-tư)
- [16. Lỗi, thông báo và khả năng phục hồi](#16-lỗi-thông-báo-và-khả-năng-phục-hồi)
- [17. Cấu trúc mã và đóng gói đề xuất](#17-cấu-trúc-mã-và-đóng-gói-đề-xuất)
- [18. Lộ trình triển khai](#18-lộ-trình-triển-khai)
- [19. Tiêu chí nghiệm thu](#19-tiêu-chí-nghiệm-thu)
- [20. Điểm cần chốt và giả định đang dùng](#20-điểm-cần-chốt-và-giả-định-đang-dùng)
- [21. Ma trận phụ thuộc và rủi ro còn lại](#21-ma-trận-phụ-thuộc-và-rủi-ro-còn-lại)
- [22. Nguồn tham khảo và giới hạn bằng chứng](#22-nguồn-tham-khảo-và-giới-hạn-bằng-chứng)
- [23. Tự phản biện và các sửa đổi đã áp dụng](#23-tự-phản-biện-và-các-sửa-đổi-đã-áp-dụng)

*(Chi tiết đầy đủ nội dung theo đặc tả của dự án)*
