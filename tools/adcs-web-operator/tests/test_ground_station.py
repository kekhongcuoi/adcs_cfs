"""Run: python -m unittest discover -s tests -v"""
import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class GroundTests(unittest.TestCase):
    def setUp(self):
        self.s = server.GroundState()

    def test_original_app_catalog_and_mid(self):
        self.assertEqual(len(server.APP_DEFS), 5)
        self.assertEqual(server.APPS['imu_app']['cmd_mid'],'0x18D0')
        self.assertEqual(server.APPS['act_app']['data_mid'],'0x08E4')
        self.assertEqual(server.APPS['camera_app']['hk_mid'],'0x0883')
        self.assertFalse('SET_ATTITUDE' in server.APPS['adcs_app']['commands'])

    def test_payload_sizes_match_headers(self):
        self.assertEqual([struct.calcsize(layout[1]) for layout in server.DATA_LAYOUTS.values()],[32,24,28])

    def test_set_speed_and_sim_ack(self):
        result=self.s.command({'app':'act_app','name':'SET_WHEEL_SPEED','params':{'omega_rad_s':120}})
        self.assertEqual(result['status'],'SIM_ACK')
        self.assertEqual(result['cc'],4)
        self.assertEqual(self.s.wheel_cmd,120)
        for _ in range(8):self.s._tick(.2)
        self.assertGreater(self.s.telemetry['act_app']['meas_omega_rad_s'],0)
        self.assertEqual(self.s.telemetry['act_app']['simulated'],1)
        self.assertLessEqual(self.s.telemetry['act_app']['target_omega_rad_s'],96)
        self.s.command({'app':'act_app','name':'STOP_WHEEL'})
        self.assertEqual(self.s.wheel_cmd,0)

    def test_imu_recalibrate_reset_angle(self):
        self.s.angle=1.4
        self.s.command({'app':'imu_app','name':'RESET_ANGLE'})
        self.assertEqual(self.s.angle,0)
        self.s.command({'app':'imu_app','name':'RECALIBRATE'})
        self.s._tick(.2)
        self.assertEqual(self.s.telemetry['imu_app']['status'],1)
        self.assertEqual(self.s.telemetry['imu_app']['valid'],0)

    def test_reset_counter_and_request_hk(self):
        self.s.command({'app':'adcs_app','name':'NOOP'})
        self.assertEqual(self.s.apps['adcs_app']['command_counter'],1)
        self.s.command({'app':'adcs_app','name':'RESET_COUNTERS'})
        self.assertEqual(self.s.apps['adcs_app']['command_counter'],0)
        result=self.s.command({'app':'adcs_app','name':'REQUEST_HK'})
        self.assertEqual(result['cc'],None)
        self.assertIn('HK mô phỏng',result['message'])

    def test_input_validation(self):
        for cmd in ({'app':'adcs_app','name':'SET_ATTITUDE'},
                    {'app':'act_app','name':'SET_WHEEL_SPEED','params':{'omega_rad_s':'nan'}},
                    {'app':'act_app','name':'DISPLAY_PARAM','params':{'ValU32':5,'ValI16':0,'ValStr':'12345678910'}}):
            with self.assertRaises(ValueError):self.s.command(cmd)

    def test_switch_mode_reject_simulated_commands(self):
        self.s.set_mode('replay')
        with self.assertRaises(ValueError):self.s.command({'app':'imu_app','name':'NOOP'})
        self.s.ingest('imu_app',{'rate_rad_s':0.22,'angle_rad':1.3,'valid':1,'simulated':0})
        self.assertEqual(self.s.telemetry['imu_app']['rate_rad_s'],0.22)
        self.assertEqual(self.s.mode,'replay')
        self.s.set_mode('live')
        with self.assertRaisesRegex(ValueError,'confirm_live'):
            self.s.command({'app':'imu_app','name':'NOOP'})

    def test_parse_ccsds_imu_and_housekeeping(self):
        fmt=server.DATA_LAYOUTS[0x08D4][1]
        values=(0.1,0.2,0.3,0.4,22.5,0.1,99,1,0,0,1)
        payload=struct.pack(fmt,*values)
        total=12+len(payload)
        packet=struct.pack('>HHH',0x08D4,0xC001,total-7) + bytes(6) + payload
        result=server.parse_ccsds(packet)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][0],'imu_app')
        self.assertAlmostEqual(result[0][1]['rate_rad_s'],0.2)
        hk=struct.pack('>HHH',0x08EA,0xC001,14-7) + bytes(6)+bytes([7,3])
        result=server.parse_ccsds(hk)
        self.assertEqual(result[0][1],{'CommandCounter':7,'CommandErrorCounter':3})

    def test_scenarios(self):
        self.s.control({'scenario':'dark'})
        self.s._tick(.2)
        self.assertEqual(self.s.telemetry['light_app']['status'],1)
        self.assertEqual(self.s.telemetry['light_app']['valid'],0)
        self.s.control({'running':False})
        self.assertFalse(self.s.running)

if __name__=='__main__':unittest.main()
