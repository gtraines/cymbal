"""
Unit tests for Phase 2 config additions:
  GimbalDef, AxisConfig, VideoOutputConfig, and SystemConfig.gimbals / video fields.

These tests load config.pyx as plain Python (it has no C-typed declarations)
so they run without compiled Cython extensions.
"""

import json
import os
import sys
import types
import tempfile
import unittest


def _load_config_module():
    """Load cymbal/utils/config.pyx as a plain Python module."""
    # Stub packages that would trigger Cython import chain, then restore
    # sys.modules so later tests can still import the real cymbal package.
    stub_names = [
        'cymbal', 'cymbal.camera_gimbal', 'cymbal.camera_gimbal.storm32_controller',
        'cymbal.spotlight_gimbal', 'cymbal.spotlight_gimbal.servo_controller',
        'cymbal.sensors', 'cymbal.sensors.mpu6050',
        'cymbal.utils', 'cymbal.utils.config',
    ]
    saved = {name: sys.modules.get(name) for name in stub_names}
    for name in stub_names:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    mod = sys.modules['cymbal.utils.config']
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyx_path = os.path.join(root, 'cymbal', 'utils', 'config.pyx')
    with open(pyx_path) as f:
        exec(compile(f.read(), pyx_path, 'exec'), mod.__dict__)

    # Restore sys.modules to avoid polluting the real cymbal package for
    # tests that run later in the same session.
    for name, old in saved.items():
        if old is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old

    return mod


_mod = _load_config_module()

SystemConfig = _mod.SystemConfig
AxisConfig = _mod.AxisConfig
GimbalDef = _mod.GimbalDef
VideoOutputConfig = _mod.VideoOutputConfig
CameraGimbalConfig = _mod.CameraGimbalConfig
SpotlightGimbalConfig = _mod.SpotlightGimbalConfig
ChannelMapConfig = _mod.ChannelMapConfig
_legacy_to_gimbal_defs = _mod._legacy_to_gimbal_defs


class TestAxisConfig(unittest.TestCase):

    def test_defaults(self):
        ax = AxisConfig('pitch', -90.0, 30.0)
        self.assertIsNone(ax.sbus_channel)

    def test_with_channel(self):
        ax = AxisConfig('yaw', -180.0, 180.0, sbus_channel=7)
        self.assertEqual(ax.sbus_channel, 7)

    def test_round_trip(self):
        ax = AxisConfig('roll', -45.0, 45.0, sbus_channel=3)
        ax2 = AxisConfig.from_dict(ax.to_dict())
        self.assertEqual(ax2.name, 'roll')
        self.assertAlmostEqual(ax2.min_deg, -45.0)
        self.assertAlmostEqual(ax2.max_deg, 45.0)
        self.assertEqual(ax2.sbus_channel, 3)

    def test_from_dict_defaults(self):
        ax = AxisConfig.from_dict({'name': 'pitch'})
        self.assertAlmostEqual(ax.min_deg, -90.0)
        self.assertAlmostEqual(ax.max_deg, 90.0)
        self.assertIsNone(ax.sbus_channel)


class TestGimbalDef(unittest.TestCase):

    def _make_def(self):
        return GimbalDef(
            id='cam_1',
            backend_type='storm32',
            roles=['camera'],
            axes=[
                AxisConfig('pitch', -90.0, 30.0, sbus_channel=6),
                AxisConfig('roll',  -90.0, 90.0, sbus_channel=None),
                AxisConfig('yaw',   -90.0, 90.0, sbus_channel=7),
            ],
            hardware={'serial_port': '/dev/ttyAMA0', 'baudrate': 115200},
        )

    def test_get_axes_dict(self):
        gd = self._make_def()
        axes = gd.get_axes_dict()
        self.assertIn('pitch', axes)
        self.assertIn('roll', axes)
        self.assertIn('yaw', axes)
        self.assertEqual(axes['pitch'], [-90.0, 30.0])

    def test_round_trip(self):
        gd = self._make_def()
        gd2 = GimbalDef.from_dict(gd.to_dict())
        self.assertEqual(gd2.id, 'cam_1')
        self.assertEqual(gd2.backend_type, 'storm32')
        self.assertEqual(gd2.roles, ['camera'])
        self.assertEqual(len(gd2.axes), 3)
        self.assertEqual(gd2.hardware['baudrate'], 115200)

    def test_enabled_defaults_true(self):
        gd = GimbalDef.from_dict({'id': 'x', 'backend_type': 'servo_gpio',
                                   'roles': [], 'axes': []})
        self.assertTrue(gd.enabled)

    def test_disabled_flag(self):
        gd = GimbalDef.from_dict({'id': 'x', 'backend_type': 'servo_gpio',
                                   'roles': [], 'axes': [], 'enabled': False})
        self.assertFalse(gd.enabled)


class TestVideoOutputConfig(unittest.TestCase):

    def test_defaults(self):
        v = VideoOutputConfig()
        self.assertEqual(v.mode, 'headless')
        self.assertEqual(v.width, 640)
        self.assertEqual(v.height, 480)
        self.assertAlmostEqual(v.fps, 30.0)

    def test_round_trip(self):
        v = VideoOutputConfig(mode='display', width=1280, height=720, fps=25.0)
        v2 = VideoOutputConfig.from_dict(v.to_dict())
        self.assertEqual(v2.mode, 'display')
        self.assertEqual(v2.width, 1280)
        self.assertEqual(v2.height, 720)
        self.assertAlmostEqual(v2.fps, 25.0)

    def test_from_empty_dict(self):
        v = VideoOutputConfig.from_dict({})
        self.assertEqual(v.mode, 'headless')


class TestSystemConfigGimbals(unittest.TestCase):

    def test_default_load_synthesises_two_gimbals(self):
        cfg = SystemConfig.load('/nonexistent/config.json')
        self.assertEqual(len(cfg.gimbals), 2)
        self.assertEqual(cfg.gimbals[0].id, 'camera_1')
        self.assertEqual(cfg.gimbals[0].backend_type, 'storm32')
        self.assertEqual(cfg.gimbals[1].id, 'spotlight_1')
        self.assertEqual(cfg.gimbals[1].backend_type, 'servo_gpio')

    def test_default_load_has_video_config(self):
        cfg = SystemConfig.load('/nonexistent/config.json')
        self.assertIsInstance(cfg.video, VideoOutputConfig)
        self.assertEqual(cfg.video.mode, 'headless')

    def test_from_dict_with_gimbals_list(self):
        data = {
            'gimbals': [
                {'id': 'g1', 'backend_type': 'storm32', 'roles': ['camera'],
                 'axes': [{'name': 'pitch', 'min_deg': -90, 'max_deg': 30}],
                 'hardware': {}},
                {'id': 'g2', 'backend_type': 'servo_gpio', 'roles': ['spotlight'],
                 'axes': [{'name': 'yaw', 'min_deg': -180, 'max_deg': 180}],
                 'hardware': {}},
            ],
        }
        cfg = SystemConfig.from_dict(data)
        self.assertEqual(len(cfg.gimbals), 2)
        self.assertEqual(cfg.gimbals[0].id, 'g1')
        self.assertEqual(cfg.gimbals[1].id, 'g2')

    def test_from_dict_single_gimbal_combined_payload(self):
        data = {
            'gimbals': [
                {'id': 'combo_1', 'backend_type': 'servo_gpio',
                 'roles': ['camera', 'spotlight'],
                 'axes': [
                     {'name': 'pitch', 'min_deg': -90, 'max_deg': 30},
                     {'name': 'yaw', 'min_deg': -180, 'max_deg': 180},
                 ], 'hardware': {}},
            ],
        }
        cfg = SystemConfig.from_dict(data)
        self.assertEqual(len(cfg.gimbals), 1)
        self.assertIn('camera', cfg.gimbals[0].roles)
        self.assertIn('spotlight', cfg.gimbals[0].roles)

    def test_round_trip_preserves_gimbals(self):
        cfg = SystemConfig.load('/nonexistent/config.json')
        d = cfg.to_dict()
        self.assertIn('gimbals', d)
        self.assertEqual(len(d['gimbals']), 2)
        cfg2 = SystemConfig.from_dict(d)
        self.assertEqual(len(cfg2.gimbals), 2)

    def test_load_from_json_file_with_gimbals_key(self):
        data = {
            'gimbals': [
                {'id': 'storm_cam', 'backend_type': 'storm32', 'roles': ['camera'],
                 'axes': [{'name': 'pitch', 'min_deg': -90, 'max_deg': 30,
                           'sbus_channel': 6}],
                 'hardware': {'serial_port': '/dev/ttyAMA1', 'baudrate': 57600}},
            ],
            'video': {'mode': 'composite', 'fps': 24.0},
            'log_level': 'DEBUG',
        }
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            cfg = SystemConfig.load(tmp)
            self.assertEqual(len(cfg.gimbals), 1)
            self.assertEqual(cfg.gimbals[0].id, 'storm_cam')
            self.assertEqual(cfg.gimbals[0].hardware['baudrate'], 57600)
            self.assertEqual(cfg.video.mode, 'composite')
            self.assertAlmostEqual(cfg.video.fps, 24.0)
            self.assertEqual(cfg.log_level, 'DEBUG')
        finally:
            os.unlink(tmp)

    def test_legacy_keys_still_load_with_deprecation(self):
        """Old JSON with only camera_gimbal/spotlight_gimbal keys must still load."""
        data = {
            'camera_gimbal': {'serial_port': '/dev/ttyAMA0', 'baudrate': 115200,
                              'timeout': 1.0},
            'spotlight_gimbal': {'pitch_pin': 17, 'yaw_pin': 27,
                                 'i2c_address': 104, 'i2c_bus': 1,
                                 'use_stabilization': True},
        }
        cfg = SystemConfig.from_dict(data)
        # Should auto-synthesise
        self.assertEqual(len(cfg.gimbals), 2)
        self.assertEqual(cfg.gimbals[0].backend_type, 'storm32')
        self.assertEqual(cfg.gimbals[1].backend_type, 'servo_gpio')


class TestLegacyToGimbalDefs(unittest.TestCase):

    def test_two_gimbals_produced(self):
        cam = CameraGimbalConfig(serial_port='/dev/ttyAMA0', baudrate=115200)
        spot = SpotlightGimbalConfig(pitch_pin=17, yaw_pin=27)
        ch = ChannelMapConfig()
        defs = _legacy_to_gimbal_defs(cam, spot, ch)
        self.assertEqual(len(defs), 2)

    def test_camera_has_three_axes(self):
        cam = CameraGimbalConfig()
        spot = SpotlightGimbalConfig()
        ch = ChannelMapConfig()
        defs = _legacy_to_gimbal_defs(cam, spot, ch)
        cam_axes = {a.name for a in defs[0].axes}
        self.assertIn('pitch', cam_axes)
        self.assertIn('roll', cam_axes)
        self.assertIn('yaw', cam_axes)

    def test_spotlight_sbus_channels_mapped(self):
        cam = CameraGimbalConfig()
        spot = SpotlightGimbalConfig()
        ch = ChannelMapConfig(spotlight_pitch=8, spotlight_yaw=9)
        defs = _legacy_to_gimbal_defs(cam, spot, ch)
        spot_axes = {a.name: a.sbus_channel for a in defs[1].axes}
        self.assertEqual(spot_axes['pitch'], 8)
        self.assertEqual(spot_axes['yaw'], 9)

    def test_hardware_dict_populated(self):
        cam = CameraGimbalConfig(serial_port='/dev/ttyAMA1', baudrate=57600)
        spot = SpotlightGimbalConfig(pitch_pin=22, yaw_pin=23)
        defs = _legacy_to_gimbal_defs(cam, spot, ChannelMapConfig())
        self.assertEqual(defs[0].hardware['serial_port'], '/dev/ttyAMA1')
        self.assertEqual(defs[0].hardware['baudrate'], 57600)
        self.assertEqual(defs[1].hardware['pitch_pin'], 22)
        self.assertEqual(defs[1].hardware['yaw_pin'], 23)


if __name__ == '__main__':
    unittest.main()
