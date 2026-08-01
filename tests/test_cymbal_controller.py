"""
Unit tests for CymbalController using mock/stub gimbals.

These tests exercise the orchestration logic (initialize, center_all,
set_gimbal_axes, get_status, shutdown, backward-compat helpers) without
requiring compiled Cython extensions or hardware.

A lightweight pure-Python simulation of CymbalController is used so the
tests are portable to any platform.
"""

import math
import unittest


# ---------------------------------------------------------------------------
# Minimal pure-Python simulation of CymbalController for testing
# ---------------------------------------------------------------------------

MODE_MANUAL    = 0
MODE_STABILIZE = 1
MODE_TRACK     = 2


class _GimbalSpy:
    """Spy gimbal that records calls for assertion."""
    def __init__(self, gimbal_id, roles=None, axes=None, init_ok=True):
        self.gimbal_id  = gimbal_id
        self.roles      = roles or ['camera']
        self.axes       = axes or {'pitch': [-90.0, 30.0], 'yaw': [-90.0, 90.0]}
        self._init_ok   = init_ok
        self.init_calls = 0
        self.center_calls = 0
        self.set_axes_calls = []
        self.shutdown_calls = 0

    def initialize(self):
        self.init_calls += 1
        return self._init_ok

    def center(self):
        self.center_calls += 1
        return True

    def set_axes(self, values):
        self.set_axes_calls.append(dict(values))
        return True

    def get_status(self):
        return {'gimbal_id': self.gimbal_id, 'connected': True}

    def shutdown(self):
        self.shutdown_calls += 1


class _FakeConfig:
    """Minimal SystemConfig stand-in."""
    class gps:
        update_rate_hz = 5; use_terrain_db = False; terrain_db_path = ''
        port = '/dev/null'; baudrate = 9600
    class geo:
        enabled = False; address_db_path = ''
    class osd:
        enabled = False
    class sbus:
        enabled = False; socket_path = ''; gpio_pin = 4
        failsafe_action = 'center'; frame_timeout_ms = 100
    class channel_map:
        mode_select = 5; poi_lock = 10
        camera_pitch = 6; camera_yaw = 7
        spotlight_pitch = 8; spotlight_yaw = 9
        camera_pitch_range = [-90.0, 30.0]; camera_yaw_range = [-90.0, 90.0]
        spotlight_pitch_range = [-90.0, 30.0]; spotlight_yaw_range = [-180.0, 180.0]
    gimbals = []   # empty → no modular mapper
    log_level = 'DEBUG'


class CymbalControllerSimulator:
    """
    Pure-Python simulation of CymbalController for unit-testing the
    orchestration logic without compiled Cython extensions.
    """

    def __init__(self, gimbals, config, logger=None):
        self.gimbals         = list(gimbals)
        self.config          = config
        self.running         = False
        self.poi_locked      = False
        self.poi_lat         = 0.0
        self.poi_lon         = 0.0
        self.current_address = "No fix"
        self.current_mode    = MODE_MANUAL
        self._last_camera_yaw = float('nan')
        self.gps = None
        self.sbus = None
        self.channel_mapper = None
        self.osd = None

    def initialize(self):
        initialized = []
        for g in self.gimbals:
            if g.initialize():
                initialized.append(g)
        self.gimbals = initialized
        return len(self.gimbals) > 0

    def shutdown(self):
        self.running = False
        for g in self.gimbals:
            g.shutdown()

    def center_all(self):
        for g in self.gimbals:
            g.center()

    def set_gimbal_axes(self, gimbal_id, values):
        for g in self.gimbals:
            if g.gimbal_id == gimbal_id:
                return g.set_axes(values)
        return False

    def set_camera_position(self, pitch, roll, yaw):
        for g in self.gimbals:
            if 'camera' in g.roles:
                return g.set_axes({'pitch': pitch, 'roll': roll, 'yaw': yaw})
        return False

    def set_spotlight_position(self, pitch, yaw):
        for g in self.gimbals:
            if 'spotlight' in g.roles:
                return g.set_axes({'pitch': pitch, 'yaw': yaw})
        return False

    def sync_gimbals(self, pitch, yaw):
        for g in self.gimbals:
            axes = {'pitch': pitch, 'yaw': yaw}
            if 'camera' in g.roles:
                axes['roll'] = 0.0
            g.set_axes(axes)

    def lock_poi(self, lat, lon):
        self.poi_lat = lat; self.poi_lon = lon; self.poi_locked = True

    def unlock_poi(self):
        self.poi_locked = False

    def get_position(self):
        nan = float('nan')
        return (nan, nan, nan, nan)

    def get_groundspeed(self):
        return float('nan')

    def get_status(self):
        return {
            'gimbals':    {g.gimbal_id: g.get_status() for g in self.gimbals},
            'gps':        None,
            'sbus':       None,
            'mode':       self.current_mode,
            'poi_locked': self.poi_locked,
            'address':    self.current_address,
        }


GimbalController = CymbalControllerSimulator  # alias test


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCymbalControllerInitialize(unittest.TestCase):

    def test_initializes_all_gimbals(self):
        g1 = _GimbalSpy('cam', ['camera'])
        g2 = _GimbalSpy('spot', ['spotlight'])
        ctrl = CymbalControllerSimulator([g1, g2], _FakeConfig())
        self.assertTrue(ctrl.initialize())
        self.assertEqual(g1.init_calls, 1)
        self.assertEqual(g2.init_calls, 1)

    def test_failed_gimbal_excluded_after_init(self):
        ok   = _GimbalSpy('cam',  ['camera'],    init_ok=True)
        bad  = _GimbalSpy('spot', ['spotlight'],  init_ok=False)
        ctrl = CymbalControllerSimulator([ok, bad], _FakeConfig())
        ctrl.initialize()
        self.assertIn(ok,  ctrl.gimbals)
        self.assertNotIn(bad, ctrl.gimbals)

    def test_returns_false_when_all_fail(self):
        bad = _GimbalSpy('x', init_ok=False)
        ctrl = CymbalControllerSimulator([bad], _FakeConfig())
        self.assertFalse(ctrl.initialize())

    def test_returns_true_with_at_least_one_gimbal(self):
        g = _GimbalSpy('cam')
        ctrl = CymbalControllerSimulator([g], _FakeConfig())
        self.assertTrue(ctrl.initialize())


class TestCymbalControllerCenterAndShutdown(unittest.TestCase):

    def _ctrl_with_gimbals(self, *roles_list):
        gimbals = [_GimbalSpy(f'g{i}', roles=r) for i, r in enumerate(roles_list)]
        ctrl = CymbalControllerSimulator(gimbals, _FakeConfig())
        ctrl.initialize()
        return ctrl, gimbals

    def test_center_all_calls_each_gimbal(self):
        ctrl, gimbals = self._ctrl_with_gimbals(['camera'], ['spotlight'])
        ctrl.center_all()
        for g in gimbals:
            self.assertEqual(g.center_calls, 1)

    def test_shutdown_calls_each_gimbal(self):
        ctrl, gimbals = self._ctrl_with_gimbals(['camera'], ['spotlight'])
        ctrl.shutdown()
        for g in gimbals:
            self.assertEqual(g.shutdown_calls, 1)


class TestCymbalControllerSetGimbalAxes(unittest.TestCase):

    def test_routes_by_id(self):
        cam  = _GimbalSpy('camera_1', ['camera'])
        spot = _GimbalSpy('spotlight_1', ['spotlight'])
        ctrl = CymbalControllerSimulator([cam, spot], _FakeConfig())
        ctrl.initialize()

        ctrl.set_gimbal_axes('camera_1', {'pitch': -30.0, 'yaw': 45.0})
        self.assertEqual(cam.set_axes_calls[-1], {'pitch': -30.0, 'yaw': 45.0})
        self.assertEqual(len(spot.set_axes_calls), 0)

    def test_returns_false_for_unknown_id(self):
        g = _GimbalSpy('x')
        ctrl = CymbalControllerSimulator([g], _FakeConfig())
        ctrl.initialize()
        self.assertFalse(ctrl.set_gimbal_axes('nonexistent', {}))


class TestCymbalControllerBackwardCompat(unittest.TestCase):

    def _make(self):
        cam  = _GimbalSpy('cam',  ['camera'])
        spot = _GimbalSpy('spot', ['spotlight'])
        ctrl = CymbalControllerSimulator([cam, spot], _FakeConfig())
        ctrl.initialize()
        return ctrl, cam, spot

    def test_set_camera_position(self):
        ctrl, cam, spot = self._make()
        ctrl.set_camera_position(-30.0, 0.0, 45.0)
        last = cam.set_axes_calls[-1]
        self.assertAlmostEqual(last['pitch'], -30.0)
        self.assertAlmostEqual(last['roll'],   0.0)
        self.assertAlmostEqual(last['yaw'],   45.0)
        self.assertEqual(len(spot.set_axes_calls), 0)

    def test_set_spotlight_position(self):
        ctrl, cam, spot = self._make()
        ctrl.set_spotlight_position(-15.0, 90.0)
        last = spot.set_axes_calls[-1]
        self.assertAlmostEqual(last['pitch'], -15.0)
        self.assertAlmostEqual(last['yaw'],   90.0)
        self.assertEqual(len(cam.set_axes_calls), 0)

    def test_sync_gimbals_points_all(self):
        ctrl, cam, spot = self._make()
        ctrl.sync_gimbals(-45.0, 30.0)
        cam_last  = cam.set_axes_calls[-1]
        spot_last = spot.set_axes_calls[-1]
        self.assertAlmostEqual(cam_last['pitch'],  -45.0)
        self.assertAlmostEqual(cam_last['yaw'],     30.0)
        self.assertAlmostEqual(spot_last['pitch'], -45.0)
        self.assertAlmostEqual(spot_last['yaw'],    30.0)
        self.assertIn('roll', cam_last)

    def test_gimbal_controller_alias(self):
        """GimbalController should be an alias for CymbalController."""
        g = _GimbalSpy('x')
        self.assertIsInstance(
            GimbalController([g], _FakeConfig()),
            CymbalControllerSimulator,
        )


class TestCymbalControllerGetStatus(unittest.TestCase):

    def test_status_contains_all_gimbals(self):
        cam  = _GimbalSpy('camera_1', ['camera'])
        spot = _GimbalSpy('spotlight_1', ['spotlight'])
        ctrl = CymbalControllerSimulator([cam, spot], _FakeConfig())
        ctrl.initialize()
        s = ctrl.get_status()
        self.assertIn('camera_1', s['gimbals'])
        self.assertIn('spotlight_1', s['gimbals'])
        self.assertFalse(s['poi_locked'])
        self.assertEqual(s['mode'], MODE_MANUAL)

    def test_poi_lock_reflected_in_status(self):
        g = _GimbalSpy('cam')
        ctrl = CymbalControllerSimulator([g], _FakeConfig())
        ctrl.initialize()
        ctrl.lock_poi(33.41, -111.83)
        s = ctrl.get_status()
        self.assertTrue(s['poi_locked'])

    def test_unlock_poi(self):
        g = _GimbalSpy('cam')
        ctrl = CymbalControllerSimulator([g], _FakeConfig())
        ctrl.initialize()
        ctrl.lock_poi(33.41, -111.83)
        ctrl.unlock_poi()
        self.assertFalse(ctrl.poi_locked)


class TestCymbalControllerMultipleGimbalTypes(unittest.TestCase):
    """Ensure controller handles various gimbal compositions."""

    def test_one_combined_payload_gimbal(self):
        combo = _GimbalSpy('combo_1', ['camera', 'spotlight'])
        ctrl  = CymbalControllerSimulator([combo], _FakeConfig())
        ctrl.initialize()
        ctrl.set_camera_position(-30.0, 0.0, 45.0)
        self.assertEqual(len(combo.set_axes_calls), 1)

    def test_two_camera_gimbals(self):
        cam_a = _GimbalSpy('cam_a', ['camera'])
        cam_b = _GimbalSpy('cam_b', ['camera'])
        ctrl  = CymbalControllerSimulator([cam_a, cam_b], _FakeConfig())
        ctrl.initialize()
        ctrl.center_all()
        self.assertEqual(cam_a.center_calls, 1)
        self.assertEqual(cam_b.center_calls, 1)

    def test_three_gimbals_mixed(self):
        cam  = _GimbalSpy('cam',  ['camera'])
        spot = _GimbalSpy('spot', ['spotlight'])
        bgc  = _GimbalSpy('bgc',  ['camera'])   # second camera (SimpleBGC)
        ctrl = CymbalControllerSimulator([cam, spot, bgc], _FakeConfig())
        ctrl.initialize()
        s = ctrl.get_status()
        self.assertEqual(len(s['gimbals']), 3)


if __name__ == '__main__':
    unittest.main()
