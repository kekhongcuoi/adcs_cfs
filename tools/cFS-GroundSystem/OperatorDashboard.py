"""Operator-focused PyQt shell for NASA cFS GroundSystem.

Presentation only: the existing Qt widgets and callbacks retain their identities.
The target angle is a local reference, NEVER a flight command.
"""

from PyQt5 import QtCore, QtWidgets


STYLE = """
QMainWindow, QWidget#operatorRoot, QScrollArea, QWidget#contentBody {
    background: #080f1d; color: #e7effb;
}
QFrame#sidebar { background: #0c1628; border-right: 1px solid #26374e; }
QFrame#card { background: #101d30; border: 1px solid #253750;
              border-radius: 12px; }
QLabel { color: #dfe9f5; background: transparent; }
QLabel#brand { color: #f4f8ff; font-size: 19px; font-weight: 800; }
QLabel#eyebrow { color: #50d9c5; font-size: 10px; font-weight: 800; }
QLabel#heading { color: #f4f8ff; font-size: 24px; font-weight: 800; }
QLabel#muted { color: #94a9c4; font-size: 12px; }
QLabel#metric { color: #6de4d3; font-size: 19px; font-weight: 700; }
QLabel#warning { color: #ffc78e; font-size: 12px; }
QLabel#pill { color: #81e8d9; background: #183b42; border-radius: 8px;
               padding: 7px 11px; font-weight: 700; }
QPushButton { background: #1a3047; color: #e6f2ff;
              border: 1px solid #34506b; border-radius: 8px;
              padding: 11px 13px; font-weight: 700; }
QPushButton:hover { background: #24405b; border-color: #57cbbd; }
QPushButton:focus { border: 2px solid #67ddcd; }
QPushButton#primary { background: #4dd5c1; color: #091c27; border: 0; }
QPushButton#primary:hover { background: #83e9da; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #0b1727; color: #eaf3ff;
     border: 1px solid #39506b; border-radius: 7px; padding: 7px;
     min-height: 23px; selection-background-color: #2e837d; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #101e30; color: #eaf3ff;
                               selection-background-color: #265654; }
QSpinBox:disabled { color: #7c91a8; background: #101a27; }
QDial { background: transparent; }
QScrollBar:vertical { background: #0b1727; width: 10px; }
QScrollBar::handle:vertical { background: #36506a; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _label(text, role=None, wrap=False):
    label = QtWidgets.QLabel(text)
    if role:
        label.setObjectName(role)
    label.setWordWrap(wrap)
    return label


def _card(title, description=None):
    card = QtWidgets.QFrame()
    card.setObjectName('card')
    layout = QtWidgets.QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 20)
    layout.setSpacing(10)
    layout.addWidget(_label(title, 'eyebrow'))
    if description:
        layout.addWidget(_label(description, 'muted', wrap=True))
    return card, layout


def _field(layout, title, widget, row):
    label = _label(title, 'muted')
    label.setBuddy(widget)
    layout.addWidget(label, row, 0)
    layout.addWidget(widget, row, 1)


def install_operator_dashboard(window):
    """Relayout existing controls; keep NASA callbacks, offsets and routing intact."""
    old_central = window.takeCentralWidget()
    window.setWindowTitle('ADCS | cFS Ground Operator')
    window.resize(1100, 790)
    window.setMinimumSize(800, 610)
    window.setStyleSheet(STYLE)

    root = QtWidgets.QWidget(window)
    root.setObjectName('operatorRoot')
    root_layout = QtWidgets.QHBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    sidebar = QtWidgets.QFrame(root)
    sidebar.setObjectName('sidebar')
    sidebar.setFixedWidth(225)
    side = QtWidgets.QVBoxLayout(sidebar)
    side.setContentsMargins(20, 27, 20, 21)
    side.setSpacing(13)
    side.addWidget(_label('◈  ORBITAL.', 'brand'))
    side.addWidget(_label('GROUND SYSTEMS / cFS', 'eyebrow'))
    side.addSpacing(32)
    side.addWidget(_label('WORKSPACE  /  01', 'eyebrow'))
    side.addWidget(_label('01   Tổng quan & kết nối', 'muted'))
    side.addWidget(_label('02   Telemetry / NASA', 'muted'))
    side.addWidget(_label('03   Command / NASA', 'muted'))
    side.addSpacing(24)
    side.addWidget(_label('LAB WORKSTATION', 'eyebrow'))
    window.routing_indicator = _label('Chờ khởi tạo RoutingService', 'muted', True)
    side.addWidget(window.routing_indicator)
    side.addStretch(1)
    side.addWidget(_label('GÓC TARGET CHỈ LÀ THAM CHIẾU\nKHÔNG GỬI LỆNH LÊN Pi', 'warning', True))
    side.addWidget(_label('NASA cFS-GroundSystem • Lab tool', 'muted', True))
    root_layout.addWidget(sidebar)

    scroll = QtWidgets.QScrollArea(root)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    body = QtWidgets.QWidget()
    body.setObjectName('contentBody')
    content = QtWidgets.QVBoxLayout(body)
    content.setContentsMargins(28, 24, 28, 26)
    content.setSpacing(17)
    content.addWidget(_label('MISSION  /  GROUND CONTROL', 'eyebrow'))
    content.addWidget(_label('Trạm mặt đất ADCS', 'heading'))
    content.addWidget(_label('Giữ nguyên NASA RoutingService, Command System và Telemetry System.', 'muted', True))

    status_card, status_layout = _card('KẾT NỐI / SPACECRAFT',
        'NASA nhận UDP telemetry → RoutingService → ZeroMQ IPC. Chọn spacecraft để lọc Telemetry System.')
    status_grid = QtWidgets.QGridLayout()
    status_grid.setColumnStretch(1, 1)
    _field(status_grid, 'Địa chỉ đã phát hiện', window.combo_box_ip_addresses, 0)
    window.spacecraft_summary = _label('All • chưa có telemetry', 'pill')
    status_grid.addWidget(window.spacecraft_summary, 1, 0, 1, 2)
    status_layout.addLayout(status_grid)
    content.addWidget(status_card)

    launch_card, launch_layout = _card('BẢNG ĐIỀU HÀNH / NASA TOOLS',
        'Cửa sổ chính phải luôn mở để RoutingService tiếp nhận và chuyển tiếp telemetry.')
    actions = QtWidgets.QGridLayout()
    actions.setSpacing(10)
    window.push_button_start_tlm.setText('◫   Mở Telemetry System')
    window.push_button_start_tlm.setToolTip('Hiển thị telemetry theo spacecraft được chọn qua NASA ZeroMQ.')
    window.push_button_start_cmd.setObjectName('primary')
    window.push_button_start_cmd.setText('⌘   Mở Command System')
    window.push_button_start_cmd.setToolTip('Mở NASA Command System; chỉ gửi lệnh sau khi kiểm tra cấu hình.')
    actions.addWidget(window.push_button_start_tlm, 0, 0)
    actions.addWidget(window.push_button_start_cmd, 0, 1)
    window.push_button_start_fdl = QtWidgets.QPushButton('⇄   Mở FDL/FUL Manager')
    window.push_button_start_fdl.setToolTip('Chỉ khả dụng khi đã chọn một spacecraft cụ thể.')
    actions.addWidget(window.push_button_start_fdl, 1, 0, 1, 2)
    launch_layout.addLayout(actions)
    launch_layout.addWidget(_label('Bật telemetry bằng Command System → Enable Tlm và nhập IP máy trạm nhận UDP, không phải mặc định IP Pi.', 'warning', True))
    content.addWidget(launch_card)

    target_card, target_layout = _card('TARGET Z / GÓC MỤC TIÊU',
        'Giá trị tham chiếu cục bộ cho người vận hành • trục Z, đơn vị độ (°). Không phải SET_YAW_TARGET.')
    target_row = QtWidgets.QHBoxLayout()
    target_row.setSpacing(20)
    window.target_dial = QtWidgets.QDial()
    window.target_dial.setRange(-1800, 1800)
    window.target_dial.setNotchesVisible(True)
    window.target_dial.setWrapping(False)
    window.target_dial.setFixedSize(120, 120)
    window.target_dial.setAccessibleName('Góc target Z, chỉ hiển thị')
    target_row.addWidget(window.target_dial, 0, QtCore.Qt.AlignCenter)
    target_values = QtWidgets.QVBoxLayout()
    target_values.addWidget(_label('TARGET Z / REFERENCE', 'eyebrow'))
    window.target_angle = QtWidgets.QDoubleSpinBox()
    window.target_angle.setRange(-180.0, 180.0)
    window.target_angle.setDecimals(1)
    window.target_angle.setSingleStep(1.0)
    window.target_angle.setSuffix(' °')
    window.target_angle.setAccessibleName('Nhập góc target Z tham chiếu bằng độ')
    window.target_angle.setToolTip('Chỉ lưu cục bộ trên máy trạm; không phát command/UDP.')
    target_values.addWidget(window.target_angle)
    window.target_preview = _label('+0.0°', 'metric')
    target_values.addWidget(window.target_preview)
    zero_button = QtWidgets.QPushButton('Đặt lại 0°')
    zero_button.clicked.connect(lambda: window.target_angle.setValue(0.0))
    target_values.addWidget(zero_button)
    target_row.addLayout(target_values, 1)
    target_layout.addLayout(target_row)
    target_layout.addWidget(_label('LIVE: chưa có command giữ góc trong firmware. Target Z KHÔNG được gửi, không có vòng PD trong GUI. Phải quan sát telemetry thực để biết góc đo.', 'warning', True))
    content.addWidget(target_card)

    offset_card, offset_layout = _card('CẤU HÌNH PACKET / HEADER OFFSETS',
        'Các phiên bản và offset vẫn dùng đúng logic NASA; offset Custom tính bằng byte.')
    offset_grid = QtWidgets.QGridLayout()
    offset_grid.setHorizontalSpacing(13)
    offset_grid.setVerticalSpacing(10)
    offset_grid.addWidget(_label('Phiên bản TLM', 'muted'), 0, 0)
    offset_grid.addWidget(window.cb_tlm_header_ver, 0, 1)
    offset_grid.addWidget(_label('Offset TLM', 'muted'), 0, 2)
    offset_grid.addWidget(window.sb_tlm_offset, 0, 3)
    offset_grid.addWidget(_label('Phiên bản CMD', 'muted'), 1, 0)
    offset_grid.addWidget(window.cb_cmd_header_ver, 1, 1)
    offset_grid.addWidget(_label('Primary', 'muted'), 1, 2)
    offset_grid.addWidget(window.sb_cmd_offset_pri, 1, 3)
    offset_grid.addWidget(_label('Secondary', 'muted'), 2, 2)
    offset_grid.addWidget(window.sb_cmd_offset_sec, 2, 3)
    offset_layout.addLayout(offset_grid)
    content.addWidget(offset_card)

    bottom = QtWidgets.QHBoxLayout()
    bottom.addWidget(_label('Lưu ý: UDP gửi thành công ≠ cFS đã thực thi. Kiểm tra HK counters / events.', 'muted', True), 1)
    window.push_button.setText('Đóng GroundSystem')
    bottom.addWidget(window.push_button)
    content.addLayout(bottom)
    content.addStretch(1)
    scroll.setWidget(body)
    root_layout.addWidget(scroll, 1)
    window.setCentralWidget(root)
    if old_central is not None:
        old_central.deleteLater()

    # Local-only target: no connection to RoutingService, cmdUtil or NASA commands.
    settings = QtCore.QSettings('cFS', 'GroundSystem-Operator')
    try:
        saved = float(settings.value('reference_target_z_deg', 0.0))
    except (TypeError, ValueError):
        saved = 0.0
    saved = min(180.0, max(-180.0, saved))
    window.target_angle.setValue(saved)
    window.target_dial.setValue(round(saved * 10))

    def change_target(value):
        window.target_dial.setValue(round(value * 10))
        window.target_preview.setText('{:+.1f}°'.format(value))
        settings.setValue('reference_target_z_deg', value)

    window.target_angle.valueChanged.connect(change_target)
    window.target_dial.valueChanged.connect(lambda value: window.target_angle.setValue(value / 10.0))
    change_target(saved)
    window.combo_box_ip_addresses.currentTextChanged.connect(
        lambda ip: window.spacecraft_summary.setText('Spacecraft: ' + ip))
    return window
