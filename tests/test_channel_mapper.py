"""
Unit tests for ChannelMapper modular (initialize_from_gimbals / get_commands)
and legacy (initialize / get_gimbal_commands) paths.

These tests use a pure-Python simulation of the ChannelMapper logic so they
run on any platform without compiled Cython extensions.
"""

import sys
import types
import unittest

# ---------------------------------------------------------------------------
# Pure-Python re-implementation of the mapper logic for testing
# ---------------------------------------------------------------------------
# We duplicate the constants and algorithms here to test the *design* contract,
# not the Cython internals.

_CH_MIN = 172
_CH_MID = 992
_CH_MAX = 1811

MODE_MANUAL    = 0
MODE_STABILIZE = 1
MODE_TRACK     = 2

_MODE_LOW_THRESHOLD  = 600
_MODE_HIGH_THRESHOLD = 1400
_POI_LOCK_THRESHOLD  = 1400


def _map_channel_to_angle(raw_value, min_angle, max_angle):
    t = (raw_value - _CH_MIN) / float(_CH_MAX - _CH_MIN)
    t = max(0.0, min(1.0, t))
    return min_angle + t * (max_angle - min_angle)


class ChannelMapperSimulator:
    """
    Pure-Python simulation of the ChannelMapper cdef class.

    Mirrors initialize_from_gimbals() and get_commands() for test purposes.
    """

    def __init__(self):
        self.ch_mode_select  = 5
        self.ch_poi_lock     = 10
        self._axis_map       = {}
        self._prev_poi_raw   = 0

        # Legacy fields
        self.ch_camera_pitch    = 6
        self.ch_camera_yaw      = 7
        self.ch_spotlight_pitch = 8
        self.ch_spotlight_yaw   = 9
        self._cam_pitch_min  = -90.0; self._cam_pitch_max  =  30.0
        self._cam_yaw_min    = -90.0; self._cam_yaw_max    =  90.0
        self._spot_pitch_min = -90.0; self._spot_pitch_max =  30.0
        self._spot_yaw_min   = -180.0; self._spot_yaw_max  = 180.0

    def initialize_from_gimbals(self, gimbal_defs, mode_channel=5, poi_lock_channel=10):
        self.ch_mode_select = mode_channel
        self.ch_poi_lock    = poi_lock_channel
        self._axis_map      = {}
        for gd in gimbal_defs:
            if not gd.enabled:
                continue
            for ax in gd.axes:
                if ax.sbus_channel is None:
                    continue
                self._axis_map[(gd.id, ax.name)] = (
                    int(ax.sbus_channel),
                    float(ax.min_deg),
                    float(ax.max_deg),
                )
        return True

    def get_commands(self, sbus):
        result = {}
        for (gimbal_id, axis_name), (ch, mn, mx) in self._axis_map.items():
            angle = _map_channel_to_angle(sbus.get_channel(ch), mn, mx)
            if gimbal_id not in result:
                result[gimbal_id] = {}
            result[gimbal_id][axis_name] = angle
        return result

    def initialize(self, config):
        self.ch_camera_pitch    = config.camera_pitch
        self.ch_camera_yaw      = config.camera_yaw
        self.ch_spotlight_pitch = config.spotlight_pitch
        self.ch_spotlight_yaw   = config.spotlight_yaw
        self.ch_mode_select     = config.mode_select
        self.ch_poi_lock        = config.poi_lock
        self._cam_pitch_min  = config.camera_pitch_range[0]
        self._cam_pitch_max  = config.camera_pitch_range[1]
        self._cam_yaw_min    = config.camera_yaw_range[0]
        self._cam_yaw_max    = config.camera_yaw_range[1]
        self._spot_pitch_min = config.spotlight_pitch_range[0]
        self._spot_pitch_max = config.spotlight_pitch_range[1]
        self._spot_yaw_min   = config.spotlight_yaw_range[0]
        self._spot_yaw_max   = config.spotlight_yaw_range[1]
        return True

    def get_gimbal_commands(self, sbus):
        return {
            'camera_pitch':    _map_channel_to_angle(
                sbus.get_channel(self.ch_camera_pitch),
                self._cam_pitch_min, self._cam_pitch_max),
            'camera_yaw':      _map_channel_to_angle(
                sbus.get_channel(self.ch_camera_yaw),
                self._cam_yaw_min, self._cam_yaw_max),
            'spotlight_pitch': _map_channel_to_angle(
                sbus.get_channel(self.ch_spotlight_pitch),
                self._spot_pitch_min, self._spot_pitch_max),
            'spotlight_yaw':   _map_channel_to_angle(
                sbus.get_channel(self.ch_spotlight_yaw),
                self._spot_yaw_min, self._spot_yaw_max),
        }

    def get_mode_index(self, sbus):
        raw = sbus.get_channel(self.ch_mode_select)
        if raw < _MODE_LOW_THRESHOLD:
            return MODE_MANUAL
        elif raw > _MODE_HIGH_THRESHOLD:
            return MODE_TRACK
        else:
            return MODE_STABILIZE

    def get_poi_lock_triggered(self, sbus):
        raw = sbus.get_channel(self.ch_poi_lock)
        triggered = (self._prev_poi_raw < _POI_LOCK_THRESHOLD
                     and raw >= _POI_LOCK_THRESHOLD)
        self._prev_poi_raw = raw
        return triggered


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class _FakeSBUS:
    """SBUSReader stub with a fixed channel value table."""
    def __init__(self, channels: dict):
        self._ch = channels

    def get_channel(self, n):
        return self._ch.get(n, _CH_MID)


class _FakeAxis:
    def __init__(self, name, min_d, max_d, ch=None):
        self.name = name
        self.min_deg = min_d
        self.max_deg = max_d
        self.sbus_channel = ch


class _FakeGimbalDef:
    def __init__(self, gid, axes, enabled=True):
        self.id = gid
        self.axes = axes
        self.enabled = enabled


class _FakeLegacyConfig:
    camera_pitch = 6; camera_yaw = 7
    spotlight_pitch = 8; spotlight_yaw = 9
    mode_select = 5; poi_lock = 10
    camera_pitch_range = [-90.0, 30.0]; camera_yaw_range = [-90.0, 90.0]
    spotlight_pitch_range = [-90.0, 30.0]; spotlight_yaw_range = [-180.0, 180.0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChannelMapperModular(unittest.TestCase):

    def _make_standard_gimbals(self):
        return [
            _FakeGimbalDef('camera_1', [
                _FakeAxis('pitch', -90.0, 30.0, ch=6),
                _FakeAxis('roll',  -90.0, 90.0, ch=None),   # no channel
                _FakeAxis('yaw',   -90.0, 90.0, ch=7),
            ]),
            _FakeGimbalDef('spotlight_1', [
                _FakeAxis('pitch', -90.0, 30.0, ch=8),
                _FakeAxis('yaw',   -180.0, 180.0, ch=9),
            ]),
        ]

    def test_axis_map_excludes_none_channels(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        # roll has no channel → should be excluded
        self.assertNotIn(('camera_1', 'roll'), cm._axis_map)

    def test_axis_map_includes_assigned_channels(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        self.assertIn(('camera_1', 'pitch'), cm._axis_map)
        self.assertIn(('camera_1', 'yaw'), cm._axis_map)
        self.assertIn(('spotlight_1', 'pitch'), cm._axis_map)
        self.assertIn(('spotlight_1', 'yaw'), cm._axis_map)
        self.assertEqual(len(cm._axis_map), 4)

    def test_disabled_gimbal_excluded(self):
        gimbals = self._make_standard_gimbals()
        gimbals.append(_FakeGimbalDef('disabled_one', [
            _FakeAxis('pitch', -90, 30, ch=11),
        ], enabled=False))
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(gimbals)
        self.assertNotIn(('disabled_one', 'pitch'), cm._axis_map)

    def test_get_commands_structure(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        sbus = _FakeSBUS({})
        cmds = cm.get_commands(sbus)
        self.assertIn('camera_1', cmds)
        self.assertIn('spotlight_1', cmds)
        self.assertIn('pitch', cmds['camera_1'])
        self.assertIn('yaw', cmds['camera_1'])
        self.assertNotIn('roll', cmds.get('camera_1', {}))

    def test_min_channel_gives_min_angle(self):
        """Channel at Futaba min (172) should produce min_angle."""
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        sbus = _FakeSBUS({6: _CH_MIN})   # camera pitch channel at minimum
        cmds = cm.get_commands(sbus)
        self.assertAlmostEqual(cmds['camera_1']['pitch'], -90.0, places=1)

    def test_max_channel_gives_max_angle(self):
        """Channel at Futaba max (1811) should produce max_angle."""
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        sbus = _FakeSBUS({8: _CH_MAX})   # spotlight pitch channel at max
        cmds = cm.get_commands(sbus)
        self.assertAlmostEqual(cmds['spotlight_1']['pitch'], 30.0, places=1)

    def test_center_channel_gives_midpoint(self):
        """Channel at Futaba center (992) should produce midpoint angle."""
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals())
        sbus = _FakeSBUS({7: _CH_MID})   # camera yaw at center
        cmds = cm.get_commands(sbus)
        expected_mid = (-90.0 + 90.0) / 2.0   # = 0.0
        self.assertAlmostEqual(cmds['camera_1']['yaw'], expected_mid, places=0)

    def test_mode_channel_respected(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals(), mode_channel=3)
        self.assertEqual(cm.ch_mode_select, 3)

    def test_poi_lock_channel_respected(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(self._make_standard_gimbals(), poi_lock_channel=11)
        self.assertEqual(cm.ch_poi_lock, 11)

    def test_get_commands_empty_when_no_gimbals(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals([])
        cmds = cm.get_commands(_FakeSBUS({}))
        self.assertEqual(cmds, {})

    def test_single_combined_payload_gimbal(self):
        """A gimbal with roles=[camera, spotlight] is handled correctly."""
        gimbals = [_FakeGimbalDef('combo_1', [
            _FakeAxis('pitch', -90, 30, ch=6),
            _FakeAxis('yaw',   -180, 180, ch=7),
        ])]
        gimbals[0].id = 'combo_1'
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals(gimbals)
        sbus = _FakeSBUS({})
        cmds = cm.get_commands(sbus)
        self.assertIn('combo_1', cmds)
        self.assertIn('pitch', cmds['combo_1'])
        self.assertIn('yaw', cmds['combo_1'])


class TestChannelMapperModeAndPOI(unittest.TestCase):

    def _make_cm(self):
        cm = ChannelMapperSimulator()
        cm.initialize_from_gimbals([], mode_channel=5, poi_lock_channel=10)
        return cm

    def test_mode_manual(self):
        cm = self._make_cm()
        sbus = _FakeSBUS({5: 200})   # < 600
        self.assertEqual(cm.get_mode_index(sbus), MODE_MANUAL)

    def test_mode_stabilize(self):
        cm = self._make_cm()
        sbus = _FakeSBUS({5: 1000})  # 600 <= raw <= 1400
        self.assertEqual(cm.get_mode_index(sbus), MODE_STABILIZE)

    def test_mode_track(self):
        cm = self._make_cm()
        sbus = _FakeSBUS({5: 1811})  # > 1400
        self.assertEqual(cm.get_mode_index(sbus), MODE_TRACK)

    def test_poi_lock_rising_edge(self):
        cm = self._make_cm()
        cm._prev_poi_raw = 500
        sbus = _FakeSBUS({10: 1600})
        self.assertTrue(cm.get_poi_lock_triggered(sbus))
        # second call: no edge
        self.assertFalse(cm.get_poi_lock_triggered(sbus))

    def test_poi_lock_no_edge_when_already_high(self):
        cm = self._make_cm()
        cm._prev_poi_raw = 1700
        sbus = _FakeSBUS({10: 1800})
        self.assertFalse(cm.get_poi_lock_triggered(sbus))


class TestChannelMapperLegacy(unittest.TestCase):
    """Verify backward compat: legacy initialize + get_gimbal_commands."""

    def test_legacy_keys_present(self):
        cm = ChannelMapperSimulator()
        cm.initialize(_FakeLegacyConfig())
        sbus = _FakeSBUS({})
        cmds = cm.get_gimbal_commands(sbus)
        self.assertIn('camera_pitch', cmds)
        self.assertIn('camera_yaw', cmds)
        self.assertIn('spotlight_pitch', cmds)
        self.assertIn('spotlight_yaw', cmds)

    def test_legacy_channel_assignment(self):
        cm = ChannelMapperSimulator()
        cm.initialize(_FakeLegacyConfig())
        self.assertEqual(cm.ch_camera_pitch, 6)
        self.assertEqual(cm.ch_spotlight_yaw, 9)
        self.assertEqual(cm.ch_mode_select, 5)

    def test_legacy_angle_at_min(self):
        cm = ChannelMapperSimulator()
        cm.initialize(_FakeLegacyConfig())
        sbus = _FakeSBUS({6: _CH_MIN})
        cmds = cm.get_gimbal_commands(sbus)
        self.assertAlmostEqual(cmds['camera_pitch'], -90.0, places=1)

    def test_legacy_angle_at_max(self):
        cm = ChannelMapperSimulator()
        cm.initialize(_FakeLegacyConfig())
        sbus = _FakeSBUS({6: _CH_MAX})
        cmds = cm.get_gimbal_commands(sbus)
        self.assertAlmostEqual(cmds['camera_pitch'], 30.0, places=1)


if __name__ == '__main__':
    unittest.main()
