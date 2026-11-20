"""Connection tests use loopback/mock only; no Raspberry Pi or real cmdUtil."""
import os
import socket
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cfs_link
import server


def imu_packet(angle=0.5):
    payload = struct.pack('<ffffffIBBBB', 0.1,0.2,angle,0.0,23.2,0.2,7,1,0,0,0)
    count = 12 + len(payload)
    return struct.pack('>HHH', 0x08D4,0xC001,count-7)+bytes(6)+payload


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.state = server.GroundState()
        self.state.set_mode('live')
        self.link = cfs_link.CfsLink(self.state, server.parse_ccsds)
        self.tmp = tempfile.TemporaryDirectory()
        self.cfgpatch = patch.object(cfs_link, 'CONFIG_FILE', Path(self.tmp.name)/'connection.local.json')
        self.cfgpatch.start()

    def tearDown(self):
        self.link.stop()
        self.cfgpatch.stop()
        self.tmp.cleanup()

    def test_validation_and_persistence(self):
        with self.assertRaises(ValueError):
            self.link.configure({'target_ip':'8.8.8.8'})
        with self.assertRaises(ValueError):
            self.link.configure({'command_port':65536})
        with self.assertRaises(ValueError):
            self.link.configure({'nasa_ipc':'tcp://8.8.8.8:5556'})
        with self.assertRaises(ValueError):
            self.link.configure({'cmdutil_path':'/bin/bash'})
        conf = self.link.configure({'source':'direct_udp','spacecraft_alias':'All','target_ip':'127.0.0.1'})
        self.assertEqual(conf['config']['source'],'direct_udp')
        self.assertTrue(cfs_link.CONFIG_FILE.is_file())

    def test_direct_udp_receive_and_decode(self):
        probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
        probe.close()
        self.link.configure({'source':'direct_udp','target_ip':'127.0.0.1',
                             'bind_ip':'127.0.0.1','telemetry_port':port})
        self.link.start()
        sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            for _ in range(25):
                sock.sendto(imu_packet(),('127.0.0.1',port))
                if self.link.status()['decoded_packets']:
                    break
                time.sleep(.03)
            status=self.link.status()
            self.assertEqual(status['status'],'RECEIVING',status)
            self.assertGreater(status['decoded_packets'],0)
            self.assertAlmostEqual(self.state.telemetry['imu_app']['angle_rad'],.5)
            self.assertEqual(self.state.telemetry['imu_app']['simulated'],0)
        finally:
            sock.close()
        self.link.stop()
        self.assertEqual(self.link.status()['status'],'STOPPED')

    def test_live_command_safe_guard_and_cmdutil(self):
        cmdutil=Path(self.tmp.name)/'cmdUtil'
        cmdutil.write_text('#!/bin/sh\nexit 0\n')
        cmdutil.chmod(0o755)
        self.link.configure({'cmdutil_path':str(cmdutil)})
        self.link.running=True  # mock linked receiver; command never sends on network
        with patch.dict(os.environ, {'ADCS_UPLINK_ENABLED':'1'}):
            with self.assertRaisesRegex(ValueError,'ARM'):
                self.link.send('act_app','SET_WHEEL_SPEED',4,20,confirmed=True)
            self.link.arm(True)
            with self.assertRaisesRegex(ValueError,'telemetry'):
                self.link.send('act_app','SET_WHEEL_SPEED',4,20,confirmed=True)
            self.state.ingest('act_app',{'valid':1,'simulated':0,'status':0})
            # Synthetic HTTP /api/ingest is deliberately insufficient for motor control.
            with self.assertRaisesRegex(ValueError,'NASA/UDP'):
                self.link.send('act_app','SET_WHEEL_SPEED',4,20,confirmed=True)
            self.link.app_rx['act_app'] = time.monotonic()  # mock verified RX for cmdUtil-only unit test
            with self.assertRaisesRegex(ValueError,'giới hạn'):
                self.link.send('act_app','SET_WHEEL_SPEED',4,100,confirmed=True)
            with patch.object(cfs_link.subprocess,'run') as runner:
                runner.return_value.returncode=0
                status, message=self.link.send('act_app','SET_WHEEL_SPEED',4,20,confirmed=True)
                self.assertEqual(status,'SENT_UNCONFIRMED')
                argv=runner.call_args.args[0]
                self.assertIn('--pktid=0x18E0',argv)
                self.assertIn('--float=20',argv)
                self.assertFalse(self.link.status()['armed'])
                self.link.send('imu_app','REQUEST_HK',None,None,confirmed=True)
                argv=runner.call_args.args[0]
                self.assertIn('--pktid=0x18D1',argv)
                self.assertIn('--cmdcode=0',argv)
        self.link.running=False

    def test_nasa_topic_filter(self):
        try:
            import zmq
        except ImportError:
            self.skipTest('pyzmq not installed')
        path=f'ipc:///tmp/GroundSystem-test-adcs-{os.getpid()}'
        context=zmq.Context()
        pub=context.socket(zmq.PUB)
        pub.bind(path)
        self.link.configure({'source':'nasa_zmq', 'nasa_ipc':path, 'spacecraft_alias':'Spacecraft1'})
        self.link.start()
        try:
            time.sleep(.2)
            for _ in range(20):
                pub.send_multipart([b'GroundSystem.Spacecraft1.TelemetryPackets.0x8d4',imu_packet()])
                if self.link.status()['decoded_packets']:
                    break
                time.sleep(.04)
            self.assertGreater(self.link.status()['decoded_packets'],0)
            self.assertEqual(self.link.status()['status'],'RECEIVING')
        finally:
            self.link.stop()
            pub.close(0)
            context.term()


if __name__ == '__main__': unittest.main()
