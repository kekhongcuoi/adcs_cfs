# ADCS Operator UI — giao diện lab

Khởi chạy như cũ trên Ubuntu (không thay backend hoặc cổng):

```bash
sudo apt install -y python3-pyqt5 python3-zmq libcanberra-gtk-module build-essential
cd tools/cFS-GroundSystem
make -C Subsystems/cmdUtil
python3 GroundSystem.py
```

Giao diện mới thay bố cục **cửa sổ chính PyQt5** bằng bảng điều hành (dark UI) lấy cảm hứng từ giao diện tham khảo người dùng cung cấp. **Không thay** RoutingService, NASA Command System, NASA Telemetry System, các decoder, cmdUtil, các MID/CC, đường UDP/ZeroMQ hay firmware trên Raspberry Pi.

- **Spacecraft:** Danh sách IP tự phát hiện vẫn cập nhật từ RoutingService; chọn All hoặc IP cụ thể để lọc Telemetry System.
- **Telemetry:** Nút “Mở Telemetry System” vẫn gọi `start_tlm_system()` cũ.
- **Command:** Nút “Mở Command System” vẫn gọi `start_cmd_system()` cũ. Trong NASA Command System, dùng **Enable Tlm** để bật TO, với **IP máy trạm nhận UDP**, không nhầm thành IP Pi.
- **FDL/FUL:** Nút mới chỉ gọi hàm `start_fdl_system()` có sẵn, cần chọn một spacecraft cụ thể.
- **Packet header:** TLM/CMD versions 1/2/Custom và primary/secondary offsets vẫn là các widget gốc, giữ nguyên logic `save_offsets()` và `/tmp/OffsetData-<username>`.
- **Target Z:** Góc tham chiếu do người dùng nhập trong khoảng **−180 đến +180°** (bước 0,1°), có dial và nút reset về 0°. Góc chỉ được lưu bằng `QSettings('cFS', 'GroundSystem-Operator')` trên máy trạm. **Không phát command**; không có `SET_YAW_TARGET` trong source đã kiểm tra.

## Phân biệt target và góc đo

**Target Z** chỉ là giá trị mong muốn do operator ghi nhớ; **không phải** góc thật đang đo. Muốn quan sát góc thực hãy dùng telemetry IMU `0x08D4` qua NASA Telemetry System hoặc một dashboard được nối với backend đọc dữ liệu. Trên phần cứng hiện có chỉ có góc tích phân một trục Z; không suy diễn Roll/Pitch/Yaw đầy đủ hay attitude hold.

Chức năng giữ góc PD trong trình duyệt, nếu có ở frontend tham khảo, chỉ dùng cho **SIMULATION**, không được dùng điều khiển phần cứng thời gian thực. LIVE vẫn phải có ARM, xác nhận, telemetry hợp lệ và giới hạn tốc độ actuator ở tầng backend nếu dùng bộ web operator tương ứng. **SENT_UNCONFIRMED** chỉ cho biết lệnh đã gửi, không xác nhận cFS nhận hoặc thực thi. Các nút NASA gốc trong GUI là công cụ lab nên người vận hành phải tự kiểm tra an toàn trước khi gửi lệnh.

## Kiểm tra

```bash
python3 -m py_compile GroundSystem.py OperatorDashboard.py
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python3 -m unittest test_operator_dashboard.py -v
```

Lệnh kiểm tra PyQt5 cuối cần môi trường Ubuntu có `python3-pyqt5` tương ứng; kiểm thử với RPi3/actuator thật chưa được thực hiện. Bản sửa không tự bật uplink hoặc vận hành actuator.
