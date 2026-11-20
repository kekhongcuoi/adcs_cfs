# UI giám sát ADCS — bản gọn (web)

Bản này dựa trên file ZIP Web Ground Station v2 của người dùng, **không thay đổi** `server.py`, `cfs_link.py`, giao thức UDP/ZeroMQ, lệnh cmdUtil, MID/CC, backend whitelist hay kiểm tra ARM.

## Đã đổi gì?

- Giữ đủ 4 chỉ số chính: gyro Z, góc tích phân Z, wheel speed, packet count.
- Giữ **3 biểu đồ** IMU, reaction wheel, light sensor và Telemetry Explorer.
- Bổ sung **Target Z [-180°, +180°]** trong Tổng quan, có ô số, thanh kéo, Reset 0°. Lưu tham chiếu bằng `localStorage` trong trình duyệt; **không gửi lệnh đến Pi**.
- Hiển thị sai lệch góc ngắn nhất `wrap(target_deg − imu_angle_rad × 180/π)` chỉ khi telemetry IMU mới (<4,5 giây), valid=1, status=0 và ở LIVE không phải simulated. Sai lệch chỉ tham khảo, không có PD hay attitude hold.
- Thu gọn trạng thái ứng dụng và sự kiện ở dưới màn Tổng quan (vẫn xem được khi mở), giữ trang ứng dụng và nhật ký.
- **Cấu hình & kết nối**: mặc định chỉ hiển thị nguồn telemetry, IP Raspberry Pi, IP Ubuntu, nút Lưu/Kết nối/Ngắt và trạng thái gói. Port, alias, UDP bind IP, IPC, cmdUtil được giữ nguyên trong `Cấu hình nâng cao`.
- ARM/DISARM 60 giây vẫn tồn tại trong nhóm `Điều khiển LIVE nâng cao`; TO_LAB Enable TLM vẫn giữ nguyên nhưng có guard từ backend và xác nhận.
- Tuỳ chọn mô phỏng, bridge API, nguồn gốc dữ liệu được thu vào các phần có thể mở khi cần.

## Chạy thử

```bash
cd adcs-ground-station-ui-simplified
python3 server.py
# vào http://127.0.0.1:8000
```

Chế độ SIMULATION là mặc định. Với Raspberry Pi thật, trước tiên xác nhận IP/cổng, file cmdUtil và luồng telemetry; đừng dùng giá trị Target Z như lệnh cFS.

Chạy kiểm thử backend có sẵn:

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
```

**An toàn:** Đây là công cụ phòng lab, chưa có kiểm thử HIL Raspberry Pi 3. `SENT_UNCONFIRMED` không phải ACK; cần giám sát HK counters và phương án dừng phần cứng độc lập.

`preview-original-v2.png` là ảnh giao diện **trước khi chỉnh sửa**, chỉ để so sánh. Bản giao diện mới hiển thị khi khởi chạy `server.py`.
