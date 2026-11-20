"""Guard rails for the simplified frontend without a browser dependency."""
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(encoding='utf-8')


class SimplifiedUiContractTests(unittest.TestCase):
    def test_dashboard_keeps_charts(self):
        for chart in ('chartRate', 'chartWheel', 'chartLight', 'chartTlm'):
            self.assertIn('id="' + chart + '"', JS)

    def test_connection_preserves_inputs(self):
        for field in ('linkSource', 'linkTargetIp', 'linkGroundIp', 'linkCommandPort',
                      'linkTelemetryPort', 'linkAlias', 'linkBindIp', 'linkIpc', 'linkCmdUtil'):
            self.assertIn("'" + field + "'", JS)

    def test_connection_preserves_original_actions(self):
        for action in ('link-save', 'link-start', 'link-stop', 'link-arm',
                       'link-disarm', 'link-enable-tlm'):
            self.assertIn('data-action="' + action + '"', JS)

    def test_target_is_only_a_local_reference(self):
        self.assertIn("const TARGET_STORAGE_KEY='adcs.operator.target_z.deg'", JS)
        self.assertIn('clampTarget', JS)
        self.assertIn('updateTargetReference()', JS)
        self.assertNotIn('SET_YAW_TARGET', JS)
        self.assertIn("window.localStorage.setItem(TARGET_STORAGE_KEY", JS)


if __name__ == '__main__':
    unittest.main()
