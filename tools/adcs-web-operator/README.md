# ADCS / cFS Ground Station v2 — Web trạm mặt đất

**Xây dựng từ mã nguồn ZIP `adcs_cfs-main.zip` người dùng cung cấp**, đối chiếu `apps/*/config/`, `apps/*/fsw/inc/`, `apps/*/fsw/src/` và `docs/{imu_app,act_app}/`. Chạy SIMULATION ngay trên máy tính **không cần vệ tinh, phần cứng, Docker, Node.js hoặc thư viện Python bổ sung**. Để đọc NASA RoutingService qua ZeroMQ cần thêm **pyzmq**.

## 1. Khởi động

Cần **Python 3.9+**.

```bash
cd adcs-ground-station-v2
python server.py
```

Mở **http://127.0.0.1:8000** (không mở `index.html` theo kiểu `file://` vì frontend sử dụng API của server). Muốn đổi cổng: `python server.py --port 8080`.

Chế độ khởi động mặc định: **SIMULATION**. Backend phát dữ liệu 5 lần/giây và tự tạo 3 luồng IMU, LIGHT, ACT, có lịch sử biểu đồ. Mô phỏng chỉ là **mô hình minh họa**, không chạy các hàm C/C++ từ repository. Lệnh nhận **SIM_ACK** chứ không phải ACK thật của cFS.

## 2. Tác vụ được xác nhận từ source

| APP | CMD MID | HK TLM MID | DATA TLM MID | Các Function Code (CC) |
|---|---|---|---|---|
| IMU | `0x18D0` | `0x08D2` | `0x08D4` | NOOP 0, RESET_COUNTERS 1, PROCESS 2, DISPLAY_PARAM 3, RECALIBRATE 4, RESET_ANGLE 5 |
| LIGHT | `0x18D8` | `0x08DA` | `0x08DC` | NOOP 0, RESET_COUNTERS 1, PROCESS 2, DISPLAY_PARAM 3 |
| ACT | `0x18E0` | `0x08E2` | `0x08E4` | NOOP 0, RESET_COUNTERS 1, PROCESS 2, DISPLAY_PARAM 3, SET_WHEEL_SPEED 4, STOP_WHEEL 5 |
| ADCS | `0x18E8` | `0x08EA` | — | NOOP 0, RESET_COUNTERS 1, PROCESS 2, DISPLAY_PARAM 3 |
| CAMERA | `0x1882` | `0x0883` | — | NOOP 0, RESET_COUNTERS 1, PROCESS 2, DISPLAY_PARAM 3 |

`REQUEST_HK` trong web dùng **MID SEND_HK** riêng (IMU `0x18D1`, LIGHT `0x18D9`, ACT `0x18E1`, ADCS `0x18E9`, CAMERA `0x1883`), không phải Function Code thuộc lệnh CMD. Trong chế độ LIVE, lệnh được đóng gói qua NASA `cmdUtil` và vẫn cần kiểm tra theo build cFS thực tế.

Cấu trúc gói DATA:

- `IMU_DATA`: payload **32 byte** sau cFE telemetry header 12 byte, góc và tốc độ tính theo **rad, rad/s**. Chỉ đo **gyro Z / góc tích phân một trục**, không có Roll/Pitch/Yaw hay quaternion. Trạng thái `status=0` bình thường; `valid=1` sau hiệu chuẩn. `RECALIBRATE` mô phỏng khoảng 10 giây.
- `LIGHT_DATA`: payload **24 byte**, lux trái/phải, normalized_diff, bearing_rad, valid/status/error_valid/simulated. **Góc bearing chỉ hợp lệ khi `valid=1`**. Bản SIM dùng calibration giả lập, không dùng cho cảm biến thật.
- `WHEEL_DATA`: payload **28 byte**, cmd/target/meas omega, pfm, flags. Mô phỏng minh họa `omega_max=300 rad/s`, `slew=60 rad/s²`, `tau=0.8s` theo `apps/act_app/fsw/src/act_motor.c`. Hệ số đổi tần số `rad_s_per_hz=0.03` trong source là ước lượng chưa được đo thực nghiệm.

**Lưu ý** `adcs_app` hiện mới subscribe `LIGHT_APP_DATA_MID` và xử lý dữ liệu ánh sáng; chưa thấy lệnh điều khiển attitude nhiều chế độ hay gói trạng thái ADCS chuyên biệt. `camera_app` hiện mới có các lệnh khung và HK. Vì vậy web **không tự bịa ra** các lệnh SET_ATTITUDE, SAFE_MODE, chụp ảnh hoặc trạng thái 3 trục.

## 3. Tính năng web

- Tổng quan: tốc độ góc, góc tương đối, tốc độ bánh đà, số packet, biểu đồ liên tục, trạng thái 5 ứng dụng.
- Ứng dụng: tra CMD/HK/DATA MID và số packet nhận.
- Điều khiển: danh sách đúng CC theo từng app, nhập `omega_rad_s` hoặc `DISPLAY_PARAM`, gửi lệnh mô phỏng, hiển thị SIM_ACK, nhật ký chi tiết.
- Telemetry: xem payload gốc theo SI, biểu đồ, xuất CSV/JSON và nhập replay JSON.
- Sự kiện: log lệnh, cảnh báo, INFO, xuất JSON.
- Cấu hình: 3 mode (Simulation / Live / Replay), tình huống Normal, Stationary, DARK, I/O Error, SATURATED; **cấu hình IP Raspberry Pi / Wi-Fi, NASA ZeroMQ / UDP trực tiếp, cmdUtil, ARM, ENABLE TLM**.

## 4. Nhập replay trước khi có dữ liệu thật

Ở tab **Telemetry**, chọn file JSON có định dạng:

```json
[
  {"app":"imu_app","payload":{"rate_rad_s":0.03,"angle_rad":0.14,"valid":1,"status":0,"simulated":1}},
  {"app":"act_app","payload":{"cmd_omega_rad_s":120,"target_omega_rad_s":50,"meas_omega_rad_s":45,"valid":1,"simulated":1}},
  {"app":"light_app","payload":{"left_lux":250,"right_lux":400,"normalized_diff":0.23,"bearing_rad":0.1,"valid":1,"simulated":1}}
]
```

Có thể chuyển sang **Replay** và gửi JSON từ ứng dụng trung gian qua `POST /api/ingest`.

## 5. Kết nối cFS thật qua Wi-Fi / NASA GroundSystem

**Đọc hướng dẫn riêng:** [`README-KET-NOI-NASA.md`](README-KET-NOI-NASA.md), giải thích chi tiết hai lựa chọn NASA RoutingService ZeroMQ và UDP trực tiếp, kết nối cFS trên Ubuntu và Raspberry Pi 3 qua Wi-Fi, cấu hình IP/port trong trang Web.

Mặc định mở web trong Ubuntu:

```bash
python3 server.py
```

- Chọn **Cấu hình & kết nối → LIVE**.
- Với **NASA GroundSystem (ZeroMQ)**, cần chạy `GroundSystem.py` riêng (cùng user) và có `pyzmq`; Web **không bind** cổng UDP 2234 trong chế độ này, chỉ subscribe `ipc:///tmp/GroundSystem-<user>`.
- Với **UDP trực tiếp**, **không chạy NASA GroundSystem.py cùng lúc** trên cổng telemetry mà Web đang bind.
- Nhập IP Pi (`127.0.0.1` nếu cFS cùng máy), IP Ubuntu nhận telemetry, CMD port (ví dụ `1234`), TLM port (ví dụ `2234`) → **Lưu IP / Cổng → Kết nối**.
- Chỉ khi **RECEIVING** và `DECODED ADCS` tăng mới xác nhận Web thực sự đã nhận telemetry cFS đúng định dạng. `LISTENING` chỉ nghĩa là bộ nhận đang chạy.

## 6. Gửi lệnh LIVE — khóa mặc định

Uplink chỉ được mở khi operator chủ động chạy backend với biến môi trường **`ADCS_UPLINK_ENABLED=1`**, và nhập đường dẫn thực đến `cmdUtil` đã build. Ngoài ra Web yêu cầu xác nhận trước lệnh thật. Các lệnh nhạy cảm phải **ARM 60 giây**, có telemetry thật mới/hợp lệ và giới hạn bánh đà **±60 rad/s**. `DISPLAY_PARAM` và `PROCESS` bị khóa trong LIVE; `REQUEST_HK`, `NOOP`, `RESET_COUNTERS` và các lệnh chuyên biệt đã whitelist dùng `cmdUtil`. Sau khi gửi thành công, trạng thái **SENT_UNCONFIRMED** *không phải ACK từ cFS*. Hãy xem HK và Event.

Để xem hướng dẫn đầy đủ các bước cho Ubuntu và Pi 3, mở [`README-KET-NOI-NASA.md`](README-KET-NOI-NASA.md). Không mở backend lên Internet công cộng.

## 7. API

| Method | Path | Ý nghĩa |
|---|---|---|
| GET | `/api/catalog` | Danh mục app, CC, MIDs |
| GET | `/api/state` | Telemetry hiện tại + 180 mẫu gần nhất + logs |
| GET | `/api/health` | Kiểm tra backend |
| GET | `/api/connection` | Trạng thái kết nối NASA/UDP và cmdUtil |
| GET | `/api/export.csv` | Xuất telemetry history |
| POST | `/api/connection/config` | Lưu IP, port, NASA IPC, alias và đường dẫn cmdUtil (localhost) |
| POST | `/api/connection/start` | Bắt đầu nhận telemetry LIVE (localhost) |
| POST | `/api/connection/stop` | Ngắt bộ nhận (localhost) |
| POST | `/api/connection/arm` | ARM/DISARM 60 giây cho lệnh nhạy cảm (localhost) |
| POST | `/api/connection/enable-tlm` | Gửi TO_LAB ENABLE_TLM qua cmdUtil (localhost) |
| POST | `/api/mode` | `{ "mode":"simulation" / "live" / "replay" }` |
| POST | `/api/sim` | `{ "running":true }` hoặc `{ "scenario":"dark" }` |
| POST | `/api/command` | `{ "app":"act_app", "name":"SET_WHEEL_SPEED", "params":{"omega_rad_s":120} }` |
| POST | `/api/ingest` | `{ "app":"imu_app", "payload":{...} }` |
| POST | `/api/replay` | `{ "packets": [ {"app":"imu_app","payload":{...}} ] }` |

## 8. Test

```bash
python -m unittest discover -s tests -v
```

## 9. Cấu trúc thư mục

```text
adcs-ground-station-v2/
  server.py                Python HTTP server, simulator, API và CCSDS decoder
  cfs_link.py              NASA ZeroMQ SUB, UDP direct, cấu hình và cmdUtil
  README-KET-NOI-NASA.md   Cách kết nối cFS Raspberry Pi qua Wi-Fi
  index.html               Ứng dụng web
  static/app.css           Giao diện dark mission control, responsive
  static/app.js            Biểu đồ canvas, điều khiển, replay, export
  tests/test_ground_station.py
  tests/test_connection.py
  README.md
```

---

Dự án này là **mẫu trạm mặt đất dùng để phát triển và học tập** theo mã nguồn hiện có, không phải phần mềm mặt đất đã được chứng nhận cho nhiệm vụ không gian.

### Mẹo chạy nhanh

- **Windows:** giải nén ZIP, chạy `start.bat` (yêu cầu đã cài Python và `py` hoặc `python` trong PATH).
- **Linux / macOS:** chạy `./start.sh` hoặc `python3 server.py`.
- **Replay mẫu:** vào Telemetry → nhập file `sample_replay.json` kèm trong gói.
