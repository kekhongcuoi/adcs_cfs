#!/usr/bin/env python3
"""ADCS ground-station demo, grounded in vuluongd/adcs_cfs apps.

No third-party dependencies. Simulation is default. External commands are OFF
unless the operator explicitly enables cmdUtil with environment variables.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import shutil
import socket
import struct
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from cfs_link import CfsLink

ROOT = Path(__file__).resolve().parent

def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

APP_DEFS = [
    dict(id='imu_app', label='IMU', subtitle='MPU6050 / Gyro trục Z', description='Lọc tốc độ góc, hiệu chuẩn bias và tích phân góc tương đối.', color='#a6e3a1', cmd_mid='0x18D0', hk_mid='0x08D2', data_mid='0x08D4', wakeup_mid='0x18D3', commands=['NOOP','RESET_COUNTERS','PROCESS','DISPLAY_PARAM','RECALIBRATE','RESET_ANGLE'], file='apps/imu_app/fsw/inc/imu_data.h'),
    dict(id='light_app', label='LIGHT', subtitle='Sun sensor / 2 kênh', description='Đo lux trái/phải, hiệu chuẩn góc tới và độ lệch ánh sáng.', color='#f3c98b', cmd_mid='0x18D8', hk_mid='0x08DA', data_mid='0x08DC', wakeup_mid='0x18DB', commands=['NOOP','RESET_COUNTERS','PROCESS','DISPLAY_PARAM'], file='apps/light_app/fsw/inc/light_tracking.h'),
    dict(id='act_app', label='ACT', subtitle='Reaction wheel / Nidec', description='Setpoint tốc độ bánh đà, giới hạn tốc độ, slew, phanh.', color='#7cbbf8', cmd_mid='0x18E0', hk_mid='0x08E2', data_mid='0x08E4', wakeup_mid='0x18E3', commands=['NOOP','RESET_COUNTERS','PROCESS','DISPLAY_PARAM','SET_WHEEL_SPEED','STOP_WHEEL'], file='apps/act_app/fsw/inc/act_data.h'),
    dict(id='adcs_app', label='ADCS', subtitle='Attitude control / sample', description='Nhận LIGHT_DATA; hiện chưa xuất gói trạng thái attitude riêng.', color='#c4a3ff', cmd_mid='0x18E8', hk_mid='0x08EA', data_mid=None, wakeup_mid=None, commands=['NOOP','RESET_COUNTERS','PROCESS','DISPLAY_PARAM'], file='apps/adcs_app/fsw/src/adcs_app_dispatch.c'),
    dict(id='camera_app', label='CAMERA', subtitle='Camera / sample', description='Các lệnh cơ bản và housekeeping; chưa có khung ảnh telemetry.', color='#f48dac', cmd_mid='0x1882', hk_mid='0x0883', data_mid=None, wakeup_mid=None, commands=['NOOP','RESET_COUNTERS','PROCESS','DISPLAY_PARAM'], file='apps/camera_app/fsw/src/camera_app_dispatch.c'),
]
APPS = {a['id']: a for a in APP_DEFS}
BASE_CMDS = dict(NOOP=0, RESET_COUNTERS=1, PROCESS=2, DISPLAY_PARAM=3)
CMD_DESCRIPTIONS = {
    'NOOP': ('Kiểm tra phản hồi', 'Không có tham số'),
    'RESET_COUNTERS': ('Xóa bộ đếm lệnh của app', 'Không có tham số'),
    'PROCESS': ('Chạy xử lý bảng ví dụ', 'Không có tham số · không phải chế độ ADCS'),
    'DISPLAY_PARAM': ('Gửi và hiển thị tham số', 'ValU32 · ValI16 · ValStr[10]'),
    'RECALIBRATE': ('Hiệu chuẩn lại IMU', 'Giữ cố định IMU khoảng 10 giây'),
    'RESET_ANGLE': ('Đặt lại góc IMU về 0', 'Góc tích phân trục Z'),
    'SET_WHEEL_SPEED': ('Đặt tốc độ bánh đà', 'float omega_rad_s, giới hạn ±300 rad/s'),
    'STOP_WHEEL': ('Giảm về 0 và phanh', 'Không có tham số'),
    'REQUEST_HK': ('Yêu cầu housekeeping', 'MID riêng SEND_HK, không phải CC'),
}
for a in APP_DEFS:
    a['command_items'] = []
    for c in a['commands']:
        code = BASE_CMDS.get(c, {'RECALIBRATE':4,'RESET_ANGLE':5,'SET_WHEEL_SPEED':4,'STOP_WHEEL':5}.get(c))
        a['command_items'].append(dict(name=c, cc=code, description=CMD_DESCRIPTIONS[c][0], payload=CMD_DESCRIPTIONS[c][1]))

DATA_LAYOUTS = {
    0x08D4: ('imu_app', '<ffffffIBBBB', ['raw_rate_rad_s','rate_rad_s','angle_rad','bias_rad_s','temp_c','dt_s','sample_counter','valid','status','stationary','simulated']),
    0x08DC: ('light_app', '<ffffIBBBB', ['left_lux','right_lux','normalized_diff','bearing_rad','sample_counter','valid','status','simulated','error_valid']),
    0x08E4: ('act_app', '<ffffIBBBBBBbB', ['cmd_omega_rad_s','target_omega_rad_s','meas_omega_rad_s','pfm_hz','sample_counter','valid','status','saturated','simulated','enabled','braking','direction','measured']),
}
HK_LAYOUTS = {int(a['hk_mid'], 16): a['id'] for a in APP_DEFS}


def parse_ccsds(datagram: bytes):
    """Decode candidate cFS packets with 12-byte cFE telemetry headers.
    Assumes CCSDS big-endian primary header and little-endian native payload
    as in the provided repo's docs. Must be checked against deployment config.
    """
    out = []
    off = 0
    while off + 6 <= len(datagram):
        mid, seq, length = struct.unpack_from('>HHH', datagram, off)
        total = length + 7
        if total < 12 or off + total > len(datagram):
            break
        pkt = datagram[off:off+total]
        if mid in DATA_LAYOUTS:
            app, fmt, fields = DATA_LAYOUTS[mid]
            size = struct.calcsize(fmt)
            if len(pkt) >= 12 + size:
                payload = dict(zip(fields, struct.unpack_from(fmt, pkt, 12)))
                if all(math.isfinite(v) for v in payload.values() if isinstance(v, float)):
                    out.append((app, payload, mid))
        elif mid in HK_LAYOUTS and len(pkt) >= 14:
            out.append((HK_LAYOUTS[mid], {'CommandCounter':pkt[12], 'CommandErrorCounter':pkt[13]}, mid))
        off += total
    return out


class GroundState:
    def __init__(self):
        self.lock = threading.RLock()
        self.mode = 'simulation'
        self.running = True
        self.scenario = 'normal'
        self.sim_t = 12.0  # starts after the demo's nominal 10 s IMU calibration
        self.angle = 0.0
        self.bias = 0.00367
        self.cal_until = 0.0
        self.wheel_cmd = 0.0
        self.wheel_target = 0.0
        self.wheel_meas = 0.0
        self.wheel_direction = 0
        self.packet_count = 0
        self.hk_last_second = -1
        self.seq = 0
        self.history = deque(maxlen=180)
        self.events = deque(maxlen=200)
        self.apps = {a['id']: dict(command_counter=0, command_error_counter=0, packets=0, last_seen=None) for a in APP_DEFS}
        self.telemetry = {'imu_app':{}, 'light_app':{}, 'act_app':{}, 'adcs_app':{}, 'camera_app':{}}
        self.last_result = None
        self._log('system', 'INFO', 'Kích hoạt SIMULATION. Không kết nối phần cứng.', None)
        self._tick(0.2)

    def _log(self, source, level, message, detail):
        self.seq += 1
        self.events.appendleft(dict(id=self.seq, time=utc(), source=source, level=level, message=message, detail=detail))

    def _update_packet(self, app, payload, mid=None):
        if app not in self.apps:
            return
        now = utc()
        if mid in HK_LAYOUTS or 'CommandCounter' in payload or 'CommandErrorCounter' in payload:
            self.apps[app]['command_counter'] = payload.get('CommandCounter', self.apps[app]['command_counter'])
            self.apps[app]['command_error_counter'] = payload.get('CommandErrorCounter', self.apps[app]['command_error_counter'])
        else:
            self.telemetry[app] = dict(payload)
        self.apps[app]['packets'] += 1
        self.apps[app]['last_seen'] = now
        self.packet_count += 1

    def _tick(self, dt):
        self.sim_t += dt
        t = self.sim_t
        in_cal = t < self.cal_until
        # A one-axis demo, not a three-axis attitude estimator.
        burst = 0.52 * math.sin((t % 40 - 25)/4*math.pi) if 25 <= t % 40 <= 29 else 0
        rate = burst + 0.018 * math.sin(t / 2.7)
        if self.scenario == 'stationary':
            rate = 0.0
        if in_cal:
            rate = 0.0
        self.angle += rate * dt
        imu = dict(raw_rate_rad_s=rate+self.bias+random.uniform(-.0006,.0006), rate_rad_s=rate, angle_rad=self.angle,
                   bias_rad_s=self.bias, temp_c=27.4 + 0.6*math.sin(t/21), dt_s=dt,
                   sample_counter=int(t*5), valid=0 if in_cal else 1, status=1 if in_cal else 0,
                   stationary=1 if abs(rate)<0.002 else 0, simulated=1)
        self._update_packet('imu_app',imu)
        # Model-inspired example: max=300, slew=60 rad/s², first-order tau=.8s.
        desired = max(-300.0, min(300.0, self.wheel_cmd))
        if desired and self.wheel_target * desired < 0 and abs(self.wheel_meas)>2:
            desired = 0.0
        dv = max(-60 * dt, min(60*dt, desired - self.wheel_target))
        self.wheel_target += dv
        self.wheel_meas += (self.wheel_target-self.wheel_meas)*min(1,dt/0.8)
        enable = int(abs(self.wheel_target) >= 2 or abs(self.wheel_meas) >= 2)
        direction = 1 if self.wheel_target>1 else (-1 if self.wheel_target < -1 else 0)
        wheel = dict(cmd_omega_rad_s=self.wheel_cmd, target_omega_rad_s=self.wheel_target,
                     meas_omega_rad_s=self.wheel_meas, pfm_hz=min(10000, max(300,abs(self.wheel_target)/0.03)) if enable else 0,
                     sample_counter=int(t*5), valid=1, status=3 if abs(self.wheel_cmd)>300 else 0,
                     saturated=int(abs(self.wheel_cmd)>300), simulated=1, enabled=enable,
                     braking=1-enable, direction=direction, measured=0)
        self._update_packet('act_app',wheel)
        # Demo bearing is synthetic & calibrated by the synthetic calibration only.
        bearing = 0.523599*math.sin(t/12)
        err = math.sin(bearing)*0.94
        sum_lux = 900 + 60*math.sin(t/5)
        left, right = max(0, sum_lux*(1-err)/2), max(0,sum_lux*(1+err)/2)
        status, valid, err_valid = 0,1,1
        if self.scenario == 'dark': left,right,status,valid,err_valid=0.3,0.4,1,0,0
        if self.scenario == 'light_error': left,right,status,valid,err_valid=0,0,4,0,0
        if self.scenario == 'light_saturated': left,right,status,valid,err_valid=65000,65530,2,0,0
        light = dict(left_lux=left,right_lux=right,normalized_diff=err if err_valid else 0,
                     bearing_rad=bearing if valid else 0, sample_counter=int(t*5), valid=valid,
                     status=status, simulated=1, error_valid=err_valid)
        self._update_packet('light_app',light)
        if int(t) != self.hk_last_second:
            self.hk_last_second = int(t)
            for a in APP_DEFS:
                app = a['id']
                counters = self.apps[app]
                self._update_packet(app, {'CommandCounter': counters['command_counter'],
                                          'CommandErrorCounter': counters['command_error_counter']},int(a['hk_mid'],16))
        self.history.append(dict(time=utc(), t=round(t,1), rate_rad_s=imu['rate_rad_s'], angle_rad=imu['angle_rad'],
                                 wheel_rad_s=wheel['meas_omega_rad_s'], wheel_set=wheel['cmd_omega_rad_s'],
                                 light_error=light['normalized_diff'], light_angle_rad=light['bearing_rad'],
                                 light_valid=light['valid']))

    def worker(self):
        last = time.monotonic()
        while True:
            time.sleep(0.2)
            now = time.monotonic(); dt = min(0.3, now-last); last = now
            with self.lock:
                if self.mode == 'simulation' and self.running:
                    self._tick(dt)

    def get_state(self):
        with self.lock:
            return dict(mode=self.mode, running=self.running, scenario=self.scenario,
                        time=utc(), sim_seconds=round(self.sim_t,1), packets=self.packet_count,
                        apps={k:dict(v) for k,v in self.apps.items()},
                        telemetry={k:dict(v) for k,v in self.telemetry.items()},
                        history=list(self.history), events=list(self.events)[:90], last_result=self.last_result,
                        uplink_configured=is_uplink_ready(), udp_enabled=bool(LINK.status()['running'] and LINK.status()['config']['source']=='direct_udp'))

    def set_mode(self, mode):
        if mode not in ('simulation','live','replay'):
            raise ValueError('Chế độ không hợp lệ')
        with self.lock:
            if self.mode != mode:
                self.mode = mode
                self.running = mode == 'simulation'
                self.history.clear()
                self.packet_count = 0
                self.last_result = None
                self.telemetry = {app:{} for app in APPS}
                for x in self.apps.values(): x['last_seen']=None; x['packets']=0
                self._log('system','WARN' if mode=='live' else 'INFO',f'Chuyển sang {mode.upper()}.',None)
                if mode=='simulation': self._tick(0.2)

    def control(self, data):
        with self.lock:
            if 'running' in data:
                if self.mode != 'simulation': raise ValueError('Chỉ phát/tạm dừng được mô phỏng')
                if type(data['running']) is not bool: raise ValueError('running phải là boolean')
                self.running = data['running']
                self._log('simulator','INFO','Bắt đầu mô phỏng' if self.running else 'Tạm dừng mô phỏng',None)
            if 'scenario' in data:
                if self.mode != 'simulation': raise ValueError('Chỉ áp dụng tình huống trong mô phỏng')
                if data['scenario'] not in ('normal','stationary','dark','light_error','light_saturated'):
                    raise ValueError('Tình huống không hợp lệ')
                self.scenario=data['scenario']
                self._log('simulator','INFO',f'Tình huống: {self.scenario}',None)

    def ingest(self, app, payload, mid=None):
        if app not in APPS: raise ValueError('Ứng dụng không tồn tại')
        if not isinstance(payload,dict): raise ValueError('payload phải là object')
        for key,val in payload.items():
            if isinstance(val,float) and not math.isfinite(val): raise ValueError('Giá trị không hữu hạn')
        with self.lock:
            if self.mode == 'simulation': raise ValueError('Chuyển sang LIVE/REPLAY trước khi nhận telemetry')
            self._update_packet(app,payload,mid)
            i=self.telemetry.get('imu_app') or {}
            a=self.telemetry.get('act_app') or {}
            l=self.telemetry.get('light_app') or {}
            self.history.append(dict(time=utc(), t=self.packet_count, rate_rad_s=i.get('rate_rad_s'),
                                     angle_rad=i.get('angle_rad'),wheel_rad_s=a.get('meas_omega_rad_s'),
                                     wheel_set=a.get('cmd_omega_rad_s'),light_error=l.get('normalized_diff'),
                                     light_angle_rad=l.get('bearing_rad'),light_valid=l.get('valid')))

    def command(self, data):
        app = data.get('app'); name = data.get('name'); params = data.get('params',{})
        if app not in APPS or (name not in APPS[app]['commands'] and name != 'REQUEST_HK'):
            raise ValueError('App hoặc tên lệnh không khớp mã nguồn')
        if not isinstance(params,dict): raise ValueError('params phải là object')
        cc = next((c['cc'] for c in APPS[app]['command_items'] if c['name']==name),None)
        val = None
        if name=='SET_WHEEL_SPEED':
            try: val=float(params['omega_rad_s'])
            except (ValueError,TypeError,KeyError): raise ValueError('omega_rad_s phải là số')
            if not math.isfinite(val) or abs(val)>10000: raise ValueError('omega_rad_s phải hữu hạn, |giá trị| ≤ 10000')
        if name=='DISPLAY_PARAM':
            try: u=int(params['ValU32']); i=int(params['ValI16']); s=str(params['ValStr'])
            except (ValueError,TypeError,KeyError): raise ValueError('Thiếu ValU32 / ValI16 / ValStr')
            if not (0<=u<=4294967295 and -32768<=i<=32767) or len(s.encode('utf-8'))>9:
                raise ValueError('ValU32: uint32, ValI16: int16, ValStr: tối đa 9 byte UTF-8')
        with self.lock:
            if self.mode=='replay': raise ValueError('Chế độ REPLAY không hỗ trợ gửi lệnh')
            if self.mode=='simulation':
                if name=='RESET_COUNTERS': self.apps[app]['command_counter']=0; self.apps[app]['command_error_counter']=0
                elif name!='REQUEST_HK': self.apps[app]['command_counter']=(self.apps[app]['command_counter']+1)%256
                if name=='SET_WHEEL_SPEED': self.wheel_cmd=val
                elif name=='STOP_WHEEL': self.wheel_cmd=0.0
                elif name=='RESET_ANGLE': self.angle=0.0; self.telemetry['imu_app']['angle_rad']=0.0
                elif name=='RECALIBRATE': self.cal_until=self.sim_t+10.0
                result='SIM_ACK'; message='Mô phỏng đã xử lý lệnh (không phải ACK từ cFS)'
                if name=='REQUEST_HK':
                    self._update_packet(app, {'CommandCounter':self.apps[app]['command_counter'],
                                              'CommandErrorCounter':self.apps[app]['command_error_counter']}, int(APPS[app]['hk_mid'],16))
                    message=f'HK mô phỏng: Cmd={self.apps[app]["command_counter"]} Err={self.apps[app]["command_error_counter"]}'
                elif name=='SET_WHEEL_SPEED' and abs(val)>300: message='SIM_ACK: đặt lệnh; mô hình giới hạn ±300 rad/s'
            else:
                if not data.get('confirm_live') is True:
                    raise ValueError('Lệnh LIVE cần confirm_live=true')
                result, message=LINK.send(app,name,cc,val,confirmed=data.get('confirm_live'))
            resp=dict(id=self.seq+1,time=utc(),app=app,name=name,cc=cc,cmd_mid=APPS[app]['cmd_mid'],
                      params=params,status=result,message=message,mode=self.mode)
            self.last_result=resp
            self._log(app,'COMMAND',f'{name} · {result}',dict(cmd_mid=resp['cmd_mid'],cc=cc,params=params))
            return resp


def is_uplink_ready():
    return LINK.status()['cmdutil_ready'] and LINK.status()['uplink_enabled']


STATE = GroundState()
LINK = CfsLink(STATE, parse_ccsds)


class Handler(BaseHTTPRequestHandler):
    server_version='ADCSGroundStation/2.0'
    def log_message(self, fmt, *args):
        if os.getenv('ADCS_HTTP_LOG')=='1': super().log_message(fmt,*args)

    def respond(self, data, status=200):
        blob=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(blob)))
        self.end_headers(); self.wfile.write(blob)

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/state':
            snapshot=STATE.get_state(); snapshot['connection']=LINK.status()
            return self.respond(snapshot)
        if path=='/api/connection': return self.respond(LINK.status())
        if path=='/api/health': return self.respond({'ok':True,'mode':STATE.mode,'time':utc()})
        if path=='/api/catalog':
            return self.respond({'apps':APP_DEFS, 'source':'adcs_cfs-main.zip · apps/*/config, fsw/inc, fsw/src, docs/*',
                                 'notes':['Một trục IMU Z, không có quaternion/RPY telemetry','ACK trong SIM chỉ là phản hồi mô phỏng','ACT wheel max ±300 rad/s, slew 60 rad/s² (tham số demo)']})
        if path=='/api/export.csv':
            with STATE.lock: rows=list(STATE.history)
            fields=['time','t','rate_rad_s','angle_rad','wheel_rad_s','wheel_set','light_error','light_angle_rad','light_valid']
            buff=io.StringIO(); writer=csv.DictWriter(buff, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            blob=buff.getvalue().encode('utf-8-sig')
            self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="adcs_telemetry.csv"')
            self.send_header('Content-Length',str(len(blob))); self.end_headers(); self.wfile.write(blob); return
        if path=='/' : path='/index.html'
        if path not in ('/index.html','/static/app.css','/static/app.js'):
            return self.respond({'error':'Không tìm thấy'},404)
        f=ROOT/path.lstrip('/')
        if not f.is_file():return self.respond({'error':'File không tồn tại'},404)
        mime='text/html' if path.endswith('html') else 'text/css' if path.endswith('css') else 'text/javascript'
        blob=f.read_bytes(); self.send_response(200); self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob)

    def do_POST(self):
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            return self.respond({'error':'Content-Type phải là application/json'},415)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=1024*1024: raise ValueError('Dung lượng body vượt giới hạn hoặc rỗng')
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict): raise ValueError('Body phải là object')
            path=urlparse(self.path).path
            if path=='/api/mode':
                if data.get('mode') not in ('simulation','live','replay'): raise ValueError('Chế độ không hợp lệ')
                if data.get('mode') != 'live': LINK.stop()
                STATE.set_mode(data.get('mode'))
                return self.respond({'ok':True,'mode':STATE.mode})
            if path.startswith('/api/connection/'):
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    return self.respond({'error':'Cấu hình NASA/cFS chỉ cho phép trên máy cục bộ'},403)
                if path=='/api/connection/config': return self.respond(LINK.configure(data))
                if path=='/api/connection/start': return self.respond(LINK.start())
                if path=='/api/connection/stop': return self.respond(LINK.stop())
                if path=='/api/connection/arm': return self.respond(LINK.arm(data.get('enabled')))
                if path=='/api/connection/enable-tlm': return self.respond(LINK.enable_tlm(data.get('confirm_live')))
                return self.respond({'error':'Endpoint không tồn tại'},404)
            if path=='/api/sim': STATE.control(data); return self.respond({'ok':True})
            if path=='/api/command':
                if STATE.mode=='live' and self.client_address[0] not in ('127.0.0.1','::1'):
                    return self.respond({'error':'LIVE uplink chỉ cho phép từ localhost'},403)
                return self.respond(STATE.command(data))
            if path=='/api/ingest':
                token=os.getenv('ADCS_INGEST_TOKEN','')
                if token and self.headers.get('X-ADCS-Token')!=token: return self.respond({'error':'Token không hợp lệ'},403)
                STATE.ingest(data.get('app'),data.get('payload')); return self.respond({'ok':True})
            if path=='/api/replay':
                packets=data.get('packets')
                if not isinstance(packets,list) or len(packets)>5000: raise ValueError('packets phải là list tối đa 5000 phần tử')
                LINK.stop()
                STATE.set_mode('replay')
                for packet in packets:
                    if not isinstance(packet,dict):raise ValueError('Gói replay không hợp lệ')
                    STATE.ingest(packet.get('app'),packet.get('payload'))
                with STATE.lock: STATE._log('replay','INFO',f'Đã nhập {len(packets)} gói JSON',None)
                return self.respond({'ok':True,'imported':len(packets)})
            return self.respond({'error':'Không tìm thấy'},404)
        except (ValueError,KeyError,TypeError) as exc:
            with STATE.lock: STATE._log('api','ERROR',str(exc),None)
            return self.respond({'error':str(exc)},400)
        except json.JSONDecodeError:
            return self.respond({'error':'JSON không hợp lệ'},400)


def main():
    ap=argparse.ArgumentParser(description='ADCS / cFS Ground Station simulator')
    ap.add_argument('--host',default='127.0.0.1',help='Mặc định chỉ truy cập từ máy cục bộ')
    ap.add_argument('--port',type=int,default=8000)
    args=ap.parse_args()
    if args.host not in ('127.0.0.1','localhost','::1') and not os.getenv('ADCS_INGEST_TOKEN'):
        ap.error('Khi lắng nghe mạng LAN cần đặt ADCS_INGEST_TOKEN (đồng thời cần bảo vệ API lệnh)')
    threading.Thread(target=STATE.worker,daemon=True).start()
    print(f'ADCS Ground Station: http://{args.host}:{args.port} | SIMULATION | uplink={"enabled" if is_uplink_ready() else "disabled"}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()

if __name__=='__main__':main()
