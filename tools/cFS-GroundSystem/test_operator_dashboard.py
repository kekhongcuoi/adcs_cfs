"""Qt smoke regression for operator shell (requires PyQt5)."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PyQt5.QtWidgets import QApplication, QMainWindow
    from UiMainWindow import UiMainWindow
    from OperatorDashboard import install_operator_dashboard
except ImportError:
    QApplication = QMainWindow = UiMainWindow = install_operator_dashboard = None


@unittest.skipIf(QApplication is None, 'PyQt5 is required for GUI test')
class OperatorDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QMainWindow()
        self.ui = UiMainWindow()
        self.ui.setupUi(self.window)
        # Production shell is a QMainWindow mixed with UiMainWindow.
        for name in ('combo_box_ip_addresses', 'cb_tlm_header_ver', 'cb_cmd_header_ver',
                     'sb_tlm_offset', 'sb_cmd_offset_pri', 'sb_cmd_offset_sec',
                     'push_button_start_tlm', 'push_button_start_cmd', 'push_button'):
            setattr(self.window, name, getattr(self.ui, name))
        install_operator_dashboard(self.window)

    def tearDown(self):
        self.window.close()

    def test_existing_controls_survive(self):
        self.assertIsNotNone(self.window.combo_box_ip_addresses)
        self.assertEqual(self.window.cb_tlm_header_ver.count(), 3)
        self.assertEqual(self.window.cb_cmd_header_ver.count(), 3)
        self.assertTrue(self.window.push_button_start_tlm.isEnabled())
        self.assertTrue(self.window.push_button_start_cmd.isEnabled())

    def test_target_is_bounded_and_local(self):
        self.window.target_angle.setValue(250.0)
        self.assertEqual(self.window.target_angle.value(), 180.0)
        self.window.target_angle.setValue(-45.5)
        self.assertEqual(self.window.target_dial.value(), -455)
        self.window.target_dial.setValue(900)
        self.assertEqual(self.window.target_angle.value(), 90.0)


if __name__ == '__main__':
    unittest.main()
