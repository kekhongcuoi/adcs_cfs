"""Local-only NASA cFS-GroundSystem connectivity for the Web v2 dashboard.

Telemetry options:
  * NASA RoutingService SUB over local ZeroMQ ipc (does NOT bind UDP 2234), or
  * direct UDP CCSDS listener (do NOT also start NASA RoutingService on same port).

Commands use the *existing* NASA cmdUtil executable, never an invented CCSDS
uplink encoder. Sending a UDP command does not prove cFS accepted it.
"""
from __future__ import annotations

import getpass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / 'connection.local.json'
DEFAULT_IPC = f'ipc:///tmp/GroundSystem-{getpass.getuser()}'
KNOWN_HK_CMD = {
    'imu_app': 0x18D1, 'light_app': 0x18D9, 'act_app': 0x18E1,
    'adcs_app': 0x18E9, 'camera_app': 0x1883,
}
LIVE_SENSITIVE = {'SET_WHEEL_SPEED', 'RESET_ANGLE', 'RECALIBRATE'}
LIVE_ALLOWED = {
    'imu_app': {'NOOP', 'RESET_COUNTERS', 'RECALIBRATE', 'RESET_ANGLE', 'REQUEST_HK'},
    'light_app': {'NOOP', 'RESET_COUNTERS', 'REQUEST_HK'},
    'act_app': {'NOOP', 'RESET_COUNTERS', 'SET_WHEEL_SPEED', 'STOP_WHEEL', 'REQUEST_HK'},
    'adcs_app': {'NOOP', 'RESET_COUNTERS', 'REQUEST_HK'},
    'camera_app': {'NOOP', 'RESET_COUNTERS', 'REQUEST_HK'},
}


def _private_ip(value, *, allow_any=False):
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ValueError('Địa chỉ IP phải là IPv4 hợp lệ') from exc
    if ip.version != 4 or ip.is_multicast or ip.is_reserved or (ip.is_unspecified and not allow_any):
        raise ValueError('Chỉ cho phép IPv4 nội bộ hoặc loopback')
    if not (ip.is_private or ip.is_loopback or ip.is_link_local or (allow_any and ip.is_unspecified)):
        raise ValueError('Chỉ cho phép IPv4 LAN/loopback (không gửi ra Internet)')
    return str(ip)


def _port(value):
    if isinstance(value, bool):
        raise ValueError('UDP port không hợp lệ')
    try:
        p = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('UDP port phải là số') from exc
    if not 1 <= p <= 65535:
        raise ValueError('UDP port phải nằm trong 1–65535')
    return p


def _defaults():
    return {
        'source': 'nasa_zmq',
        'target_ip': os.getenv('ADCS_TARGET_HOST', '127.0.0.1'),
        'command_port': os.getenv('ADCS_TARGET_PORT', '1234'),
        'telemetry_port': os.getenv('ADCS_UDP_TLM_PORT', '2234'),
        'bind_ip': '0.0.0.0',
        'ground_ip': '127.0.0.1',
        'spacecraft_alias': 'Spacecraft1',
        'nasa_ipc': DEFAULT_IPC,
        'cmdutil_path': os.getenv('ADCS_CMDUTIL_PATH', str(Path.home() / 'adcs_cfs/tools/cFS-GroundSystem/Subsystems/cmdUtil/cmdUtil')),
    }


def validate_config(data):
    if not isinstance(data, dict):
        raise ValueError('Cấu hình phải là JSON object')
    source = str(data.get('source', '')).strip()
    if source not in ('nasa_zmq', 'direct_udp'):
        raise ValueError('Nguồn telemetry phải là nasa_zmq hoặc direct_udp')
    alias = str(data.get('spacecraft_alias', '')).strip()
    if alias != 'All' and not re.fullmatch(r'Spacecraft[1-9][0-9]{0,4}', alias):
        raise ValueError('Alias cần có dạng Spacecraft1, hoặc All để nhận tất cả')
    ipc = str(data.get('nasa_ipc', '')).strip()
    # Limit ZMQ to the local NASA GroundSystem IPC convention. Never connect
    # to arbitrary remote tcp endpoints from a browser-supplied config.
    if not re.fullmatch(r'ipc:///tmp/GroundSystem-[A-Za-z0-9_.-]{1,80}', ipc):
        raise ValueError('NASA IPC phải có dạng ipc:///tmp/GroundSystem-<user>')
    cmdutil_path = str(data.get('cmdutil_path', '')).strip()
    if len(cmdutil_path) > 500 or (cmdutil_path and Path(cmdutil_path).name != 'cmdUtil'):
        raise ValueError('Đường dẫn phải trỏ tới executable tên cmdUtil')
    return {
        'source': source,
        'target_ip': _private_ip(data.get('target_ip')),
        'command_port': _port(data.get('command_port')),
        'telemetry_port': _port(data.get('telemetry_port')),
        'bind_ip': _private_ip(data.get('bind_ip'), allow_any=True),
        'ground_ip': _private_ip(data.get('ground_ip')),
        'spacecraft_alias': alias,
        'nasa_ipc': ipc,
        'cmdutil_path': cmdutil_path,
    }


class CfsLink:
    def __init__(self, state, decoder):
        self.state = state
        self.decoder = decoder
        self.lock = threading.RLock()
        self.config = validate_config(_defaults())
        self.thread = None
        self.stop_event = None
        self.running = False
        self.last_error = ''
        self.rx_raw = 0
        self.rx_decoded = 0
        self.app_rx = {}  # Actual decoded CCSDS via this link, not HTTP /api/ingest
        self.last_packet_time = None
        self.last_packet_mono = 0.0
        self.last_sender = ''
        self.last_topic = ''
        self.armed_until = 0.0
        self.last_command = None
        if CONFIG_FILE.is_file():
            try:
                saved = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
                self.config = validate_config({**self.config, **saved})
            except (OSError, ValueError, TypeError):
                self.last_error = 'Không đọc được connection.local.json; dùng cấu hình mặc định'

    def _cmdutil_ready(self):
        p = Path(self.config['cmdutil_path']).expanduser()
        return p.is_file() and os.access(p, os.X_OK)

    def _uplink_enabled(self):
        return os.getenv('ADCS_UPLINK_ENABLED') == '1'

    def status(self):
        with self.lock:
            armed = max(0.0, self.armed_until - time.monotonic())
            receiving = self.running and self.last_packet_mono and time.monotonic() - self.last_packet_mono < 5
            return {
                'config': dict(self.config),
                'running': self.running,
                'status': 'RECEIVING' if receiving else ('LISTENING' if self.running else ('ERROR' if self.last_error else 'STOPPED')),
                'last_error': self.last_error,
                'received_datagrams': self.rx_raw,
                'decoded_packets': self.rx_decoded,
                'last_packet_time': self.last_packet_time,
                'last_sender': self.last_sender,
                'last_topic': self.last_topic,
                'cmdutil_ready': self._cmdutil_ready(),
                'uplink_enabled': self._uplink_enabled(),
                'armed': armed > 0,
                'arm_seconds_left': round(armed),
                'last_command': self.last_command,
                'pyzmq_available': self._zmq_available(),
            }

    @staticmethod
    def _zmq_available():
        try:
            import zmq  # noqa: F401
            return True
        except ImportError:
            return False

    def configure(self, data):
        with self.lock:
            if self.running:
                raise ValueError('Hãy Ngắt kết nối trước khi thay đổi cấu hình')
            validated = validate_config({**self.config, **data})
            self.config = validated
            self.armed_until = 0
            self.last_error = ''
            CONFIG_FILE.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return self.status()

    def start(self):
        if self.state.mode != 'live':
            raise ValueError('Hãy chọn chế độ LIVE trước khi kết nối')
        with self.lock:
            if self.running:
                return self.status()
            if self.config['source'] == 'nasa_zmq' and not self._zmq_available():
                raise ValueError('Thiếu pyzmq: chạy python3 -m pip install pyzmq (hoặc chọn UDP trực tiếp)')
            stop = threading.Event()
            self.stop_event = stop
            self.running = True
            self.last_error = ''
            self.armed_until = 0
            self.rx_raw = 0
            self.rx_decoded = 0
            self.app_rx = {}
            self.last_packet_time = None
            self.last_packet_mono = 0
            self.last_sender = ''
            self.last_topic = ''
            config = dict(self.config)
            self.thread = threading.Thread(
                target=self._run_nasa if config['source'] == 'nasa_zmq' else self._run_udp,
                args=(stop, config), daemon=True, name='cfs-telemetry',
            )
            self.thread.start()
            self.state._log('cfs-link', 'INFO', f'Bắt đầu lắng nghe {config["source"]}', None)
            return self.status()

    def stop(self):
        with self.lock:
            self.armed_until = 0
            if self.stop_event is not None:
                self.stop_event.set()
            thread = self.thread
            self.running = False
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self.lock:
            self.thread = None
            self.stop_event = None
            return self.status()

    def _fail(self, exc, stop):
        with self.lock:
            if self.stop_event is stop and not stop.is_set():
                self.last_error = str(exc)[:250]
                self.state._log('cfs-link', 'ERROR', self.last_error, None)
                self.running = False
                self.armed_until = 0

    def _accept(self, data, sender, topic, config):
        try:
            messages = self.decoder(data)
        except (ValueError, TypeError, OSError):
            messages = []
        with self.lock:
            self.rx_raw += 1
            self.last_sender = sender
            if topic:
                self.last_topic = topic
            # RX status means *decoded ADCS telemetry*, not merely any UDP bytes.
            if messages:
                from datetime import datetime, timezone
                self.rx_decoded += len(messages)
                self.last_packet_mono = time.monotonic()
                self.last_packet_time = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for app, payload, mid in messages:
            try:
                if self.state.mode == 'live':
                    self.state.ingest(app, payload, mid)
                    with self.lock:
                        self.app_rx[app] = time.monotonic()
            except ValueError:
                pass

    def _run_udp(self, stop, config):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Bind exclusively: do not share NASA RoutingService UDP port.
            sock.bind((config['bind_ip'], config['telemetry_port']))
            sock.settimeout(0.3)
            while not stop.is_set():
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                # Ignore UDP injected from IPs other than the configured Pi/cFS target.
                if addr[0] != config['target_ip']:
                    continue
                self._accept(data, addr[0], '', config)
        except OSError as exc:
            self._fail(exc, stop)
        finally:
            sock.close()

    def _run_nasa(self, stop, config):
        try:
            import zmq
            ctx = zmq.Context()
            sub = ctx.socket(zmq.SUB)
            sub.setsockopt(zmq.SUBSCRIBE, b'GroundSystem.')
            sub.setsockopt(zmq.RCVTIMEO, 250)
            sub.setsockopt(zmq.LINGER, 0)
            sub.connect(config['nasa_ipc'])
            try:
                while not stop.is_set():
                    try:
                        parts = sub.recv_multipart()
                    except zmq.Again:
                        continue
                    if len(parts) != 2:
                        continue
                    topic_bytes, data = parts
                    topic = topic_bytes.decode('utf-8', errors='replace')
                    fields = topic.split('.')
                    if len(fields) < 4 or fields[0] != 'GroundSystem' or fields[2] != 'TelemetryPackets':
                        continue
                    if config['spacecraft_alias'] != 'All' and fields[1] != config['spacecraft_alias']:
                        continue
                    self._accept(data, fields[1], topic, config)
            finally:
                sub.close(0)
                ctx.term()
        except Exception as exc:  # a broken ZMQ IPC/socket should show error instead of killing server
            self._fail(exc, stop)

    def arm(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('arm phải là true hoặc false')
        with self.lock:
            if enabled and not (self.state.mode == 'live' and self.running and self._uplink_enabled() and self._cmdutil_ready()):
                raise ValueError('Chỉ ARM trong LIVE khi đang kết nối và cmdUtil đã bật')
            self.armed_until = time.monotonic() + 60 if enabled else 0.0
            self.state._log('cfs-link', 'WARN' if enabled else 'INFO', 'ARM 60 giây' if enabled else 'DISARM', None)
            return self.status()

    def _execute(self, argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f'cmdUtil thất bại: {exc}') from exc
        if result.returncode != 0:
            raise ValueError(f'cmdUtil lỗi ({result.returncode}): {(result.stderr or result.stdout)[:240]}')

    def _ready(self, confirmed):
        if self.state.mode != 'live' or not self.running:
            raise ValueError('Phải bật LIVE và Kết nối trước khi gửi lệnh thật')
        if confirmed is not True:
            raise ValueError('Lệnh LIVE cần confirm_live=true')
        if not self._uplink_enabled() or not self._cmdutil_ready():
            raise ValueError('Uplink khóa: cần ADCS_UPLINK_ENABLED=1 và cmdUtil hợp lệ')

    def send(self, app, name, cc, val, confirmed=False):
        with self.lock:
            self._ready(confirmed)
            if app not in LIVE_ALLOWED or name not in LIVE_ALLOWED[app]:
                raise ValueError('Lệnh chưa được xác minh qua cmdUtil trong LIVE')
            if name in LIVE_SENSITIVE:
                if time.monotonic() >= self.armed_until:
                    raise ValueError('Lệnh cần ARM 60 giây trong mục Kết nối')
                if time.monotonic() - self.app_rx.get(app, 0.0) > 5:
                    raise ValueError(f'Thiếu telemetry {app} nhận thật qua NASA/UDP trong 5 giây (không chấp nhận /api/ingest)')
                last_seen = self.state.apps[app]['last_seen']
                if not last_seen:
                    raise ValueError(f'Chưa nhận telemetry {app} để kiểm tra an toàn')
                from datetime import datetime, timezone
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_seen)).total_seconds()
                except ValueError:
                    age = 999
                tlm = self.state.telemetry.get(app, {})
                if age > 5 or tlm.get('valid') != 1 or tlm.get('simulated') != 0 or tlm.get('status') != 0:
                    raise ValueError(f'Telemetry {app} chưa mới/hợp lệ (valid=1, simulated=0, status=0)')
            if name == 'SET_WHEEL_SPEED' and (val is None or not math.isfinite(val) or abs(val) > 60):
                raise ValueError('Giới hạn LIVE bánh đà ±60 rad/s; không áp dụng giới hạn SIM')
            mid = KNOWN_HK_CMD[app] if name == 'REQUEST_HK' else int(self.state_app_mid(app), 16)
            code = 0 if name == 'REQUEST_HK' else cc
            argv = [str(Path(self.config['cmdutil_path']).expanduser()),
                    f'--host={self.config["target_ip"]}', f'--port={self.config["command_port"]}',
                    '--protocol=cfsv1', f'--pktid=0x{mid:04X}', f'--cmdcode={code}', '--endian=LE']
            if name == 'SET_WHEEL_SPEED':
                argv.append(f'--float={float(val):.8g}')
            self._execute(argv)
            if name in LIVE_SENSITIVE:
                self.armed_until = 0
            info = {'status': 'SENT_UNCONFIRMED', 'message': f'cmdUtil đã gửi UDP tới {self.config["target_ip"]}:{self.config["command_port"]}; chờ HK/event xác nhận'}
            self.last_command = {'app': app, 'name': name, **info}
            return info['status'], info['message']

    @staticmethod
    def state_app_mid(app):
        # Supplied cFS command MIDs, validated by server app catalog.
        return {'imu_app': '0x18D0', 'light_app': '0x18D8', 'act_app': '0x18E0',
                'adcs_app': '0x18E8', 'camera_app': '0x1882'}[app]

    def enable_tlm(self, confirmed):
        with self.lock:
            self._ready(confirmed)
            ground_ip = self.config['ground_ip']
            if self.config['source'] == 'nasa_zmq' and self.config['telemetry_port'] != 2234:
                raise ValueError('NASA RoutingService trong fork này nghe UDP 2234; hãy chỉnh cấu hình đúng')
            argv = [str(Path(self.config['cmdutil_path']).expanduser()),
                    f'--host={self.config["target_ip"]}', f'--port={self.config["command_port"]}',
                    '--protocol=cfsv1', '--pktid=0x1880', '--cmdcode=6', '--endian=LE',
                    f'--string=17:{ground_ip}']
            self._execute(argv)
            msg = f'TO_LAB ENABLE OUTPUT đã gửi tới Pi; yêu cầu trả telemetry về {ground_ip}:2234 (chưa xác nhận)'
            self.last_command = {'app': 'to_lab', 'name': 'ENABLE_TLM', 'status': 'SENT_UNCONFIRMED', 'message': msg}
            self.state._log('to_lab', 'COMMAND', msg, None)
            return self.last_command
