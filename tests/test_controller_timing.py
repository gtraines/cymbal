"""
Unit tests for Phase 6 instrumentation:
  - CymbalController loop-timing stats fields and get_status() timing key
  - SocketTelemetryProvider max_data_age_ms high-water mark
  - Staleness transition logging (fresh→stale, stale→fresh)
  - get_status() data_age_ms and timing fields present and correct

Uses pure-Python simulations following the same conventions as
test_cymbal_controller.py and test_telemetry_provider.py so that tests
run without compiled Cython extensions or hardware.
"""

import math
import time
import unittest


# ---------------------------------------------------------------------------
# Inline deferred import helper (avoids sys.modules stub poisoning)
# ---------------------------------------------------------------------------

_ipc_cache = {}

def _schema():
    if 'schema' not in _ipc_cache:
        import sys, types
        for key in list(sys.modules):
            if key.startswith('cymbal.controller') or key == 'cymbal':
                mod = sys.modules[key]
                if isinstance(mod, types.ModuleType) and not hasattr(mod, '__file__'):
                    del sys.modules[key]
        from cymbal.controller.ipc_schemas import TelemetrySnapshotSchema
        _ipc_cache['schema'] = TelemetrySnapshotSchema
    return _ipc_cache['schema']


def _make_snap(fix_quality=1, timestamp=None):
    schema = _schema()
    if timestamp is None:
        timestamp = time.monotonic()
    return schema.pack(
        lat=33.415, lon=-111.831, alt_msl=450.0, alt_agl=150.0,
        groundspeed_ms=28.0, track_degrees=45.0,
        fix_quality=fix_quality, satellites=9,
        address="123 Test St, Mesa, AZ",
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Pure-Python simulation of the instrumented CymbalController
# ---------------------------------------------------------------------------

class _InstrumentedController:
    """
    Simulates the loop-timing fields added in Phase 6.
    This mirrors the field layout in cymbal_controller.pxd.
    """

    def __init__(self, stats_window=100):
        # Timing stats
        self._loop_count       = 0
        self._loop_elapsed_sum = 0.0
        self._loop_elapsed_min = 1e9
        self._loop_elapsed_max = 0.0
        self._stats_window     = stats_window
        self._last_mean_loop_ms = 0.0
        self._last_min_loop_ms  = 0.0
        self._last_max_loop_ms  = 0.0

        # Simple log capture
        self.debug_log = []

    def _record_iteration(self, elapsed):
        """Simulate one loop iteration recording."""
        self._loop_count       += 1
        self._loop_elapsed_sum += elapsed
        if elapsed < self._loop_elapsed_min:
            self._loop_elapsed_min = elapsed
        if elapsed > self._loop_elapsed_max:
            self._loop_elapsed_max = elapsed

        if self._loop_count >= self._stats_window:
            mean_ms = (self._loop_elapsed_sum / self._loop_count) * 1000.0
            self._last_mean_loop_ms = mean_ms
            self._last_min_loop_ms  = self._loop_elapsed_min * 1000.0
            self._last_max_loop_ms  = self._loop_elapsed_max * 1000.0
            self.debug_log.append(
                f"mean={mean_ms:.2f}ms "
                f"min={self._last_min_loop_ms:.2f}ms "
                f"max={self._last_max_loop_ms:.2f}ms"
            )
            self._loop_count       = 0
            self._loop_elapsed_sum = 0.0
            self._loop_elapsed_min = 1e9
            self._loop_elapsed_max = 0.0

    def get_status(self):
        status = {'timing': None}
        if self._last_mean_loop_ms > 0.0 or self._loop_count > 0:
            status['timing'] = {
                'mean_loop_ms': self._last_mean_loop_ms,
                'min_loop_ms':  self._last_min_loop_ms,
                'max_loop_ms':  self._last_max_loop_ms,
                'stats_window': self._stats_window,
            }
        return status


# ---------------------------------------------------------------------------
# Pure-Python simulation of SocketTelemetryProvider with max_data_age_ms
# ---------------------------------------------------------------------------

class _InstrumentedSocketProvider:
    """
    Extends the simulation from test_telemetry_provider with:
    - max_data_age_ms high-water mark
    - warning_log / info_log for transition events
    """

    def __init__(self, frame_timeout_ms=500.0):
        self.frame_timeout_ms  = frame_timeout_ms
        self.has_fix           = False
        self.fix_quality       = 0
        self.satellites        = 0
        self.latitude          = float('nan')
        self.longitude         = float('nan')
        self.altitude_msl      = float('nan')
        self.altitude_agl      = float('nan')
        self.groundspeed_ms    = float('nan')
        self.track_degrees     = float('nan')
        self.address           = "No fix"
        self.data_age_ms       = float('nan')
        self.max_data_age_ms   = 0.0
        self.last_snapshot_time = 0.0
        self._prev_has_fix     = False
        self._pending          = None
        self.warning_log       = []
        self.info_log          = []

    def feed_snapshot(self, data):
        self._pending = data

    def update(self):
        now    = time.monotonic()
        schema = _schema()
        latest = self._pending
        self._pending = None

        if latest is not None:
            snap = schema.unpack(latest)
            if snap.get('valid'):
                was_stale = not self._prev_has_fix and snap['fix_quality'] > 0
                self.has_fix        = snap['fix_quality'] > 0
                self.fix_quality    = snap['fix_quality']
                self.satellites     = snap['satellites']
                self.latitude       = snap['lat']
                self.longitude      = snap['lon']
                self.altitude_msl   = snap['alt_msl']
                self.altitude_agl   = snap['alt_agl']
                self.groundspeed_ms = snap['groundspeed_ms']
                self.track_degrees  = snap['track_degrees']
                self.address        = snap['address']
                self.last_snapshot_time = snap['timestamp']
                age_ms              = (now - snap['timestamp']) * 1000.0
                self.data_age_ms    = age_ms
                if age_ms > self.max_data_age_ms:
                    self.max_data_age_ms = age_ms
                if was_stale:
                    self.info_log.append(f"recovered age={age_ms:.1f}ms")
                self._prev_has_fix = self.has_fix
                return True
        else:
            if self.last_snapshot_time > 0.0:
                age_ms = (now - self.last_snapshot_time) * 1000.0
                self.data_age_ms = age_ms
                if age_ms > self.max_data_age_ms:
                    self.max_data_age_ms = age_ms
                if age_ms > self.frame_timeout_ms:
                    was_fresh = self._prev_has_fix
                    self.has_fix  = False
                    self.address  = "No fix"
                    if was_fresh:
                        self.warning_log.append(
                            f"stale age={age_ms:.1f}ms timeout={self.frame_timeout_ms:.0f}ms"
                        )
                        self._prev_has_fix = False
            else:
                self.data_age_ms = float('nan')
        return False


# ---------------------------------------------------------------------------
# Tests: loop-timing instrumentation
# ---------------------------------------------------------------------------

class TestLoopTimingInstrumentation(unittest.TestCase):

    def test_timing_fields_start_at_zero(self):
        ctrl = _InstrumentedController()
        self.assertEqual(ctrl._loop_count, 0)
        self.assertEqual(ctrl._last_mean_loop_ms, 0.0)
        self.assertEqual(ctrl._last_min_loop_ms,  0.0)
        self.assertEqual(ctrl._last_max_loop_ms,  0.0)

    def test_stats_window_not_triggered_before_window(self):
        ctrl = _InstrumentedController(stats_window=5)
        for _ in range(4):
            ctrl._record_iteration(0.020)   # 20 ms
        self.assertEqual(ctrl._last_mean_loop_ms, 0.0)
        self.assertEqual(len(ctrl.debug_log), 0)

    def test_stats_logged_at_window_boundary(self):
        ctrl = _InstrumentedController(stats_window=5)
        for _ in range(5):
            ctrl._record_iteration(0.020)   # 20 ms
        self.assertAlmostEqual(ctrl._last_mean_loop_ms, 20.0, places=1)
        self.assertEqual(len(ctrl.debug_log), 1)

    def test_min_max_tracked_correctly(self):
        ctrl = _InstrumentedController(stats_window=4)
        ctrl._record_iteration(0.010)   # 10 ms
        ctrl._record_iteration(0.020)   # 20 ms
        ctrl._record_iteration(0.030)   # 30 ms
        ctrl._record_iteration(0.015)   # 15 ms — triggers window
        self.assertAlmostEqual(ctrl._last_min_loop_ms, 10.0, places=1)
        self.assertAlmostEqual(ctrl._last_max_loop_ms, 30.0, places=1)

    def test_stats_reset_after_window(self):
        """After one window, internal accumulators reset for the next window."""
        ctrl = _InstrumentedController(stats_window=3)
        for _ in range(3):
            ctrl._record_iteration(0.020)
        # Accumulators reset
        self.assertEqual(ctrl._loop_count, 0)
        self.assertAlmostEqual(ctrl._loop_elapsed_sum, 0.0, places=9)

    def test_multiple_windows_accumulate(self):
        ctrl = _InstrumentedController(stats_window=3)
        for _ in range(6):
            ctrl._record_iteration(0.020)
        self.assertEqual(len(ctrl.debug_log), 2)

    def test_get_status_timing_key_absent_before_window(self):
        ctrl = _InstrumentedController(stats_window=100)
        status = ctrl.get_status()
        self.assertIsNone(status['timing'])

    def test_get_status_timing_key_present_after_window(self):
        ctrl = _InstrumentedController(stats_window=2)
        ctrl._record_iteration(0.018)
        ctrl._record_iteration(0.022)
        status = ctrl.get_status()
        t = status['timing']
        self.assertIsNotNone(t)
        self.assertIn('mean_loop_ms', t)
        self.assertIn('min_loop_ms',  t)
        self.assertIn('max_loop_ms',  t)
        self.assertIn('stats_window', t)
        self.assertEqual(t['stats_window'], 2)
        self.assertAlmostEqual(t['mean_loop_ms'], 20.0, places=0)


# ---------------------------------------------------------------------------
# Tests: IPC staleness max_data_age_ms high-water mark
# ---------------------------------------------------------------------------

class TestSocketProviderMaxDataAge(unittest.TestCase):

    def test_max_data_age_ms_starts_at_zero(self):
        p = _InstrumentedSocketProvider()
        self.assertEqual(p.max_data_age_ms, 0.0)

    def test_max_data_age_ms_updated_from_fresh_snapshot(self):
        p = _InstrumentedSocketProvider()
        old_ts = time.monotonic() - 0.1   # 100 ms old
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        self.assertGreater(p.max_data_age_ms, 90.0)

    def test_max_data_age_ms_is_high_water_mark(self):
        """max_data_age_ms never decreases even after a fresher snapshot."""
        p = _InstrumentedSocketProvider()
        # First: old snapshot
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic() - 0.3))
        p.update()
        first_max = p.max_data_age_ms
        # Second: fresh snapshot
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        self.assertEqual(p.max_data_age_ms, first_max)

    def test_max_data_age_ms_updated_during_staleness(self):
        """Even when no new data arrives, max_data_age_ms grows during stale check."""
        p = _InstrumentedSocketProvider(frame_timeout_ms=100.0)
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic() - 0.05))
        p.update()
        after_first = p.max_data_age_ms
        # No new data — age grows
        time.sleep(0.05)
        p.update()
        self.assertGreaterEqual(p.max_data_age_ms, after_first)


# ---------------------------------------------------------------------------
# Tests: staleness transition logging
# ---------------------------------------------------------------------------

class TestStalenessTransitionLogging(unittest.TestCase):

    def test_no_warning_logged_when_never_had_fix(self):
        p = _InstrumentedSocketProvider(frame_timeout_ms=100.0)
        for _ in range(3):
            p.update()   # no data, no fix
        self.assertEqual(len(p.warning_log), 0)

    def test_warning_logged_on_fresh_to_stale_transition(self):
        p = _InstrumentedSocketProvider(frame_timeout_ms=100.0)
        # Establish a fix
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        self.assertTrue(p.has_fix)
        # Let it go stale (inject an old timestamp and drain buffer)
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic() - 1.0))
        p.update()   # applies old snapshot (data_age > timeout)
        p.update()   # second update triggers stale check
        self.assertFalse(p.has_fix)
        self.assertGreater(len(p.warning_log), 0)
        self.assertIn('stale', p.warning_log[0])

    def test_warning_logged_only_once_per_stale_period(self):
        """warning_log should have exactly one entry per fresh→stale transition."""
        p = _InstrumentedSocketProvider(frame_timeout_ms=100.0)
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        old_ts = time.monotonic() - 1.0
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        # Multiple stale updates — warning should only fire once
        for _ in range(5):
            p.update()
        self.assertEqual(len(p.warning_log), 1)

    def test_info_logged_on_recovery(self):
        p = _InstrumentedSocketProvider(frame_timeout_ms=100.0)
        # Go stale
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic() - 1.0))
        p.update()
        p.update()   # goes stale
        self.assertFalse(p.has_fix)
        # Recover
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        self.assertTrue(p.has_fix)
        self.assertGreater(len(p.info_log), 0)
        self.assertIn('recovered', p.info_log[0])


# ---------------------------------------------------------------------------
# Tests: get_status() data_age_ms field
# ---------------------------------------------------------------------------

class TestGetStatusDataAge(unittest.TestCase):
    """Verify the data_age_ms field propagates correctly through get_status()."""

    def _make_ctrl(self, provider):
        class _Ctrl:
            def __init__(self, tp):
                self.telemetry_provider = tp
                self._last_mean_loop_ms = 0.0
                self._last_min_loop_ms  = 0.0
                self._last_max_loop_ms  = 0.0
                self._stats_window      = 100
                self._loop_count        = 0

            def get_status(self):
                tp = self.telemetry_provider
                status = {'gps': None, 'timing': None}
                if tp is not None:
                    status['gps'] = {
                        'has_fix':     tp.has_fix,
                        'data_age_ms': tp.data_age_ms,
                    }
                if self._last_mean_loop_ms > 0.0 or self._loop_count > 0:
                    status['timing'] = {
                        'mean_loop_ms': self._last_mean_loop_ms,
                        'min_loop_ms':  self._last_min_loop_ms,
                        'max_loop_ms':  self._last_max_loop_ms,
                        'stats_window': self._stats_window,
                    }
                return status
        return _Ctrl(provider)

    def test_data_age_ms_in_gps_status_after_snapshot(self):
        p = _InstrumentedSocketProvider()
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        ctrl = self._make_ctrl(p)
        status = ctrl.get_status()
        self.assertIn('data_age_ms', status['gps'])
        self.assertLess(status['gps']['data_age_ms'], 50.0)

    def test_data_age_ms_nan_before_any_snapshot(self):
        p = _InstrumentedSocketProvider()
        p.update()
        ctrl = self._make_ctrl(p)
        status = ctrl.get_status()
        self.assertTrue(math.isnan(status['gps']['data_age_ms']))

    def test_timing_key_none_before_window(self):
        p = _InstrumentedSocketProvider()
        ctrl = self._make_ctrl(p)
        status = ctrl.get_status()
        self.assertIsNone(status['timing'])


if __name__ == '__main__':
    unittest.main()
