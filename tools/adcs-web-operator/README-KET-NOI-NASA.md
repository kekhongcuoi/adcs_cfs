# ADCS Ground Station Web v2 — Kết nối NASA cFS-GroundSystem

Đây là **Web v2 gốc** (Tổng quan / Ứng dụng cFS / Điều khiển / Telemetry / Sự kiện / Cấu hình & kết nối) được thêm mô-đun kết nối NASA cFS. **Không phải phần mềm điều khiển đã được kiểm nghiệm trên Raspberry Pi 3 thực tế.** Cổng, Message ID, cấu trúc CCSDS, kiểu dữ liệu payload phải khớp bản `adcs_cfs` trên Pi/Ubuntu.

## Chạy ngay trên Ubuntu VirtualBox (chưa có Pi)

```bash
cd ~/adcs-ground-station-v2
python3 server.py
```

Mở **http://127.0.0.1:8000** trên trình duyệt **trong Ubuntu**. Ban đầu mặc định là **SIMULATION**, không gửi lệnh thật.

Trong trang **Cấu hình & kết nối** có hai cách nhận dữ liệu:

### A. NASA GroundSystem (ZeroMQ) — khuyên dùng khi NASA GUI đã chạy

1. Trong một Terminal Ubuntu, chạy NASA GroundSystem từ bản fork:

   ```bash
   cd ~/adcs_cfs/tools/cFS-GroundSystem
   python3 GroundSystem.py
   ```

2. Trong Terminal thứ hai, đảm bảo `pyzmq` có thể import bằng đúng Python chạy Web:

   ```bash
   python3 -c 'import zmq; print(zmq.__version__)'
   ```

   Nếu thiếu, cài trong Python/venv phù hợp (Ubuntu distro có thể có `python3-zmq`; hoặc `python3 -m pip install -r requirements-nasa.txt` trong venv). **Không cần chạy lại NASA RoutingService từ Web:** NASA `GroundSystem.py` đã mở UDP port 2234 và xuất telemetry ra **`ipc:///tmp/GroundSystem-<user>`**. Web chỉ kết nối ZeroMQ SUB để đọc, không chiếm cổng 2234.

3. Mở trang Web **Cấu hình & kết nối**, chọn **LIVE**, **NASA GroundSystem (ZeroMQ)**; nhập:
   - `IP RASPBERRY PI / cFS`: `127.0.0.1` khi thử cFS cùng Ubuntu, hoặc IP Pi qua Wi-Fi.
   - `UDP COMMAND PORT`: `1234` (kiểm tra cấu hình CI_LAB).
   - `UDP TELEMETRY PORT`: `2234` trong cấu hình NASA fork này.
   - `IP UBUNTU`: IP máy trạm để TO_LAB gửi về; cùng máy dùng `127.0.0.1`, khác máy dùng IP LAN của Ubuntu.
   - `NASA ALIAS`: `Spacecraft1` (thường là host đầu tiên được NASA RoutingService phát hiện), hoặc `All` nếu chưa rõ alias.
   - `NASA IPC ROUTING`: thông thường `ipc:///tmp/GroundSystem-vboxuser` trên máy ảo bạn (thay `vboxuser` theo `whoami`). **NASA GUI và Web phải chạy cùng user**.
   - `cmdUtil`: đường dẫn tuyệt đối đến `~/adcs_cfs/tools/cFS-GroundSystem/Subsystems/cmdUtil/cmdUtil` (ký tự `~` cũng được hỗ trợ).
4. Nhấn **Lưu IP / Cổng** → **Kết nối**. Trạng thái **LISTENING** nghĩa là Web đã khởi động SUB, **chưa chứng minh đã có telemetry**. Chỉ khi nhận và giải mã được gói ADCS, Web chuyển **RECEIVING**.
5. CFS TO_LAB phải được cấu hình gửi gói UDP về địa chỉ Ubuntu ở port 2234. Với nguồn NASA, GroundSystem.py phải chạy; nếu không status sẽ tiếp tục LISTENING.

### B. UDP trực tiếp — không mở NASA GUI

1. Chọn **LIVE → UDP trực tiếp**.
2. Điền `IP Raspberry Pi / cFS`, `UDP TELEMETRY PORT` (ví dụ `2234`), `UDP LISTEN IP=0.0.0.0`, `IP UBUNTU` thực.
3. Nhấn **Lưu** → **Kết nối**. Web bind socket UDP và giải mã CCSDS trực tiếp. **Không chạy NASA GroundSystem.py cùng lúc trên port 2234** để tránh tranh cổng.
4. Cấu hình TO_LAB trên Pi gửi về `IP UBUNTU:2234`, kiểm tra `RECEIVING` và số `DECODED ADCS` tăng.

> Chú ý: status LISTENING không có nghĩa đã kết nối được Pi. IP Pi dùng cho **command destination**, trong chế độ UDP trực tiếp cũng lọc địa chỉ nguồn của datagram. IP Ubuntu là **đích nhận telemetry**, không phải IP Pi.

## Raspberry Pi 3 qua Wi-Fi

- Cho Raspberry Pi và máy Windows cùng Wi-Fi. VirtualBox Ubuntu nên dùng **Bridged Adapter** (nếu card mạng/Access Point hỗ trợ).
- Kiểm tra địa chỉ trên mỗi máy bằng `hostname -I`, thử `ping <IP_PI>` từ Ubuntu.
- Ở mục Kết nối, `IP RASPBERRY PI / cFS` là IP của Pi, `IP UBUNTU` là IP của Ubuntu.
- Port lệnh ví dụ `1234` cho `CI_LAB`; port telemetry `2234` cho `TO_LAB`/NASA GroundSystem. **Không phải tất cả mission build đều dùng các cổng mặc định này.**

## Gửi lệnh NASA cmdUtil (chỉ khi thực sự cần)

Mặc định **khóa uplink thật**. Để chủ động cho phép trong một phiên lab, dừng Web và chạy:

```bash
cd ~/adcs-ground-station-v2
export ADCS_UPLINK_ENABLED=1
python3 server.py
```

Web vẫn chỉ truy cập từ **localhost** theo mặc định. Chỉ bật uplink sau khi đã xác minh đường dẫn `cmdUtil` thực sự tồn tại, là file có quyền chạy và đúng mission cFS. Trong **LIVE**, nhấn **Kết nối**. Sau đó:

- Trong trang **Điều khiển**, gửi `NOOP`/`RESET_COUNTERS` hoặc `REQUEST_HK` (được whitelist). `DISPLAY_PARAM` và `PROCESS` không được gửi từ Web trong LIVE.
- Trước lệnh nhạy cảm (`SET_WHEEL_SPEED`, `RESET_ANGLE`, `RECALIBRATE`), nhấn **ARM 60 giây** ở trang Kết nối. Trạm từ chối nếu không có telemetry cFS **mới và hợp lệ, nhận qua NASA/UDP** (`valid=1`, `simulated=0`, `status=0`), không chấp nhận dữ liệu do `/api/ingest` tự đưa vào để mở khóa lệnh nhạy cảm và giới hạn tốc độ bánh đà LIVE ±60 rad/s.
- **Gửi TO_LAB ENABLE TLM** tạo lệnh `0x1880 CC 6`, chứa địa chỉ IP Ubuntu, dựa trên script `to-enable-tlm.sh` trong GroundSystem. Lệnh gửi không đồng nghĩa việc TO_LAB chấp nhận.
- `SENT_UNCONFIRMED` chỉ có nghĩa `cmdUtil` trả exit code 0. **Hãy đối chiếu housekeeping, Event hoặc hành vi cFS** trước khi coi lệnh là thành công.

Tất cả hành động cấu hình/Kết nối và gửi lệnh thật đều bị hạn chế với request HTTP từ `127.0.0.1`. Không mở web server trên địa chỉ public. Không vượt qua các interlock cơ khí/điện khi vận hành bánh đà.

## Hạn chế kỹ thuật

- Parser minh họa cho `adcs_cfs` này giả định CCSDS primary header 6 byte, cFE telemetry header 12 byte và payload Little Endian. MID IMU `0x08D4`, LIGHT `0x08DC`, ACT `0x08E4`; telemetry HK riêng. Nếu build bạn dùng khác version/header, Web có thể báo datagram nhận nhưng decoded bằng 0.
- NASA GroundSystem RoutingService cấp alias Spacecraft1, Spacecraft2 theo thứ tự phát hiện host, không nhất thiết là ID cố định. Để chẩn đoán, chọn alias `All` và nhìn `NASA TOPIC`.
- Chưa có test phần cứng Raspberry Pi 3/IMU/bánh đà. Không có quaternion / Roll/Pitch/Yaw thực; đồ họa góc Z và dữ liệu SIM được phân biệt rõ.
- `connection.local.json` do Web tạo chỉ lưu địa chỉ/cổng và đường dẫn, **không chứa mật khẩu**. File được thêm vào `.gitignore` để không push đường dẫn máy cá nhân.
- Bắt đầu kết nối không tự khởi động NASA GroundSystem.py, cũng không tự cấu hình mạng Wi-Fi. Chỉ có luồng đọc qua IPC hoặc UDP và luồng gửi lệnh riêng qua cmdUtil.

## Kiểm thử

```bash
python3 -m unittest discover -s tests -v
```
