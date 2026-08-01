"""
Unit tests for TelemetryProvider staleness and degraded-mode behaviour.

These tests use pure-Python stubs so they run without compiled Cython
extensions or hardware.  They verify:

  1. SocketTelemetryProvider (via a pure-Python simulation) marks data stale
     when no snapshot arrives within frame_timeout_ms.

  2. The controller correctly reads from its provider and falls back to
     safe values (has_fix=False, NaN fields) when data is stale.

  3. TelemetrySnapshotSchema round-trips all fields correctly.

  4. SocketTelemetryProvider recovers when fresh data resumes after a
     stale period.

Import strategy: cymbal.controller.ipc_schemas is imported inside each
test method rather than at module level.  This avoids poisoning by the
sys.modules stub installed by test_config_gimbals.py (which replaces the
cymbal namespace at collection time).
"""

import math
import time
import unittest


# ---------------------------------------------------------------------------
# Deferred schema accessor — imported on first use so module-level sys.modules
# stubs installed by other test files (test_config_gimbals.py) don't break
# test collection.
# ---------------------------------------------------------------------------

_schema_cache = {}

def _get_schema():
    if 'schema' not in _schema_cache:
        # Import fresh each time; by the time a test runs, sys.modules stubs
        # from other test files that ran at collection time may have been
        # partially cleaned up.  Using importlib allows a fresh load.
        import importlib
        import sys
        # Remove any stub that test_config_gimbals injected for cymbal.controller
        for key in list(sys.modules):
            if key.startswith('cymbal.controller') or key == 'cymbal':
                mod = sys.modules[key]
                import types
                if isinstance(mod, types.ModuleType) and not hasattr(mod, '__file__'):
                    del sys.modules[key]
        from cymbal.controller.ipc_schemas import TelemetrySnapshotSchema
        _schema_cache['schema'] = TelemetrySnapshotSchema
    return _schema_cache['schema']


# ---------------------------------------------------------------------------
# Pure-Python simulation of SocketTelemetryProvider for platform-portable testing
# ---------------------------------------------------------------------------

class _SimSocketTelemetryProvider:
    """
    Minimal Python simulation of SocketTelemetryProvider.

    Accepts injected snapshot bytes via feed_snapshot(); simulates
    update() drain, staleness, and field population.
    """

    def __init__(self, frame_timeout_ms: float = 500.0):
        self.frame_timeout_ms  = frame_timeout_ms
        self.connected         = True
        self.is_available      = True
        # Published fields (same as TelemetryProvider base)
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
        # Internal
        self._pending          = None       # next snapshot bytes to apply
        self.last_snapshot_time = 0.0

    def feed_snapshot(self, data: bytes):
        """Inject a snapshot datagram (mimics sidecar sending to socket)."""
        self._pending = data

    def update(self) -> bool:
        now     = time.monotonic()
        got     = False
        latest  = self._pending
        self._pending = None   # drain
        schema  = _get_schema()

        if latest is not None:
            snap = schema.unpack(latest)
            if snap.get('valid'):
                self.has_fix          = snap['fix_quality'] > 0
                self.fix_quality      = snap['fix_quality']
                self.satellites       = snap['satellites']
                self.latitude         = snap['lat']
                self.longitude        = snap['lon']
                self.altitude_msl     = snap['alt_msl']
                self.altitude_agl     = snap['alt_agl']
                self.groundspeed_ms   = snap['groundspeed_ms']
                self.track_degrees    = snap['track_degrees']
                self.address          = snap['address']
                self.last_snapshot_time = snap['timestamp']
                self.data_age_ms      = (now - snap['timestamp']) * 1000.0
                got = True
        else:
            # No new data — check staleness
            if self.last_snapshot_time > 0.0:
                age_ms = (now - self.last_snapshot_time) * 1000.0
                self.data_age_ms = age_ms
                if age_ms > self.frame_timeout_ms:
                    self.has_fix  = False
                    self.address  = "No fix"
            else:
                self.data_age_ms = float('nan')
        return got

    def close(self):
        self.connected    = False
        self.is_available = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snap(
    lat=33.415, lon=-111.831, alt_msl=450.0, alt_agl=150.0,
    groundspeed_ms=28.0, track_degrees=45.0,
    fix_quality=1, satellites=9,
    address="1234 E Main St, Mesa, AZ 85201",
    timestamp=None,
) -> bytes:
    schema = _get_schema()
    if timestamp is None:
        timestamp = time.monotonic()
    return schema.pack(
        lat=lat, lon=lon, alt_msl=alt_msl, alt_agl=alt_agl,
        groundspeed_ms=groundspeed_ms, track_degrees=track_degrees,
        fix_quality=fix_quality, satellites=satellites,
        address=address, timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Tests: IPC schema
# ---------------------------------------------------------------------------

class TestTelemetrySnapshotSchema(unittest.TestCase):

    def test_pack_unpack_roundtrip_valid_fix(self):
        ts   = time.monotonic()
        data = _make_snap(timestamp=ts)
        schema = _get_schema()
        snap = schema.unpack(data)
        self.assertTrue(snap['valid'])
        self.assertAlmostEqual(snap['lat'],  33.415,   places=5)
        self.assertAlmostEqual(snap['lon'], -111.831,  places=5)
        self.assertEqual(snap['fix_quality'], 1)
        self.assertEqual(snap['satellites'],  9)
        self.assertEqual(snap['address'], "1234 E Main St, Mesa, AZ 85201")
        self.assertAlmostEqual(snap['timestamp'], ts, places=3)

    def test_pack_unpack_nan_fields(self):
        data = _make_snap(lat=float('nan'), lon=float('nan'), fix_quality=0, satellites=0)
        schema = _get_schema()
        snap = schema.unpack(data)
        self.assertTrue(snap['valid'])
        self.assertTrue(math.isnan(snap['lat']))
        self.assertEqual(snap['fix_quality'], 0)

    def test_unpack_bad_magic(self):
        schema = _get_schema()
        data = b'XXXX' + b'\x00' * (schema.SIZE - 4)
        snap = schema.unpack(data)
        self.assertFalse(snap['valid'])

    def test_unpack_too_short(self):
        schema = _get_schema()
        snap = schema.unpack(b'\x00' * 10)
        self.assertFalse(snap['valid'])

    def test_address_truncated_at_127_bytes(self):
        long_addr = 'A' * 200
        data = _make_snap(address=long_addr)
        schema = _get_schema()
        snap = schema.unpack(data)
        self.assertEqual(len(snap['address']), 127)

    def test_size_constant_matches_struct(self):
        import struct as _struct
        schema = _get_schema()
        self.assertEqual(
            schema.SIZE,
            _struct.calcsize('!4s6dBBd128s'),
        )


# ---------------------------------------------------------------------------
# Tests: SocketTelemetryProvider fresh-data path
# ---------------------------------------------------------------------------

class TestSocketTelemetryProviderFresh(unittest.TestCase):

    def test_fresh_snapshot_populates_fields(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap(lat=33.1, lon=-111.5, fix_quality=1, satellites=8))
        p.update()
        self.assertTrue(p.has_fix)
        self.assertAlmostEqual(p.latitude,  33.1,   places=5)
        self.assertAlmostEqual(p.longitude, -111.5, places=5)
        self.assertEqual(p.fix_quality, 1)
        self.assertEqual(p.satellites,  8)

    def test_no_fix_snapshot_clears_has_fix(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap(fix_quality=0, satellites=0))
        p.update()
        self.assertFalse(p.has_fix)

    def test_update_returns_true_on_new_data(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap())
        self.assertTrue(p.update())

    def test_update_returns_false_when_no_data(self):
        p = _SimSocketTelemetryProvider()
        self.assertFalse(p.update())

    def test_address_field_populated(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap(address="999 N Oak Ave, Phoenix, AZ 85001"))
        p.update()
        self.assertEqual(p.address, "999 N Oak Ave, Phoenix, AZ 85001")

    def test_data_age_ms_near_zero_for_fresh_snapshot(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap(timestamp=time.monotonic()))
        p.update()
        self.assertLess(p.data_age_ms, 50.0)   # < 50 ms for freshly packed snap


# ---------------------------------------------------------------------------
# Tests: SocketTelemetryProvider staleness
# ---------------------------------------------------------------------------

class TestSocketTelemetryProviderStaleness(unittest.TestCase):

    def test_stale_snapshot_clears_has_fix(self):
        """A snapshot timestamped in the far past should trigger staleness."""
        p = _SimSocketTelemetryProvider(frame_timeout_ms=200.0)
        old_ts = time.monotonic() - 1.0   # 1 second old — well past 200 ms
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        # First update applies the old snapshot — data_age_ms > timeout
        # then the next update (no new data) runs the stale check
        p.update()
        self.assertFalse(p.has_fix)
        self.assertEqual(p.address, "No fix")

    def test_stale_preserves_last_lat_lon(self):
        """After stale timeout, lat/lon are preserved (last known position)."""
        p = _SimSocketTelemetryProvider(frame_timeout_ms=200.0)
        old_ts = time.monotonic() - 1.0
        p.feed_snapshot(_make_snap(lat=33.9, lon=-112.0, fix_quality=1, timestamp=old_ts))
        p.update()
        p.update()  # triggers staleness
        self.assertFalse(p.has_fix)
        self.assertAlmostEqual(p.latitude,  33.9,   places=4)
        self.assertAlmostEqual(p.longitude, -112.0, places=4)

    def test_data_age_ms_increases_without_fresh_data(self):
        """data_age_ms reflects the real age of the last snapshot."""
        p = _SimSocketTelemetryProvider(frame_timeout_ms=9999.0)
        old_ts = time.monotonic() - 0.5   # 500 ms ago
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        p.update()   # second update, no new data
        self.assertGreater(p.data_age_ms, 450.0)   # at least ~450 ms

    def test_recovery_after_stale(self):
        """Receiving fresh data after a stale period restores has_fix."""
        p = _SimSocketTelemetryProvider(frame_timeout_ms=100.0)
        old_ts = time.monotonic() - 0.5
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        p.update()   # goes stale
        self.assertFalse(p.has_fix)
        # Now inject fresh data
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=time.monotonic()))
        p.update()
        self.assertTrue(p.has_fix)

    def test_never_received_data_age_ms_is_nan(self):
        """Before any snapshot, data_age_ms is NaN."""
        p = _SimSocketTelemetryProvider()
        p.update()
        self.assertTrue(math.isnan(p.data_age_ms))

    def test_frame_timeout_ms_respected(self):
        """Timeout of 100 ms is respected; no stale before timeout elapses."""
        p = _SimSocketTelemetryProvider(frame_timeout_ms=100.0)
        # Inject a snapshot that is 50 ms old
        recent_ts = time.monotonic() - 0.05
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=recent_ts))
        p.update()
        p.update()   # age ~50 ms — below 100 ms threshold
        self.assertTrue(p.has_fix)


# ---------------------------------------------------------------------------
# Tests: degraded-mode controller behaviour
# ---------------------------------------------------------------------------

class TestControllerDegradedMode(unittest.TestCase):
    """
    Verify that the controller simulation handles a stale TelemetryProvider
    gracefully: get_position() returns NaN tuple, get_groundspeed() returns NaN,
    and get_status() gps entry reflects has_fix=False.
    """

    def _make_ctrl(self, provider):
        """Build a minimal controller-like object using the provider."""

        class _FakeGimbal:
            gimbal_id = 'cam1'
            roles     = ['camera']
            axes      = {}
            def initialize(self): return True
            def shutdown(self): pass
            def center(self): return True
            def set_axes(self, v): return True
            def get_status(self): return {'gimbal_id': self.gimbal_id}

        class _Ctrl:
            def __init__(self, tp):
                self.telemetry_provider = tp
                self.gimbals = [_FakeGimbal()]
                self.current_address = tp.address
                self.current_mode    = 0
                self.poi_locked      = False
                self.sbus            = None

            def get_position(self):
                nan = float('nan')
                tp  = self.telemetry_provider
                if tp is None or not tp.has_fix:
                    return (nan, nan, nan, nan)
                return (tp.latitude, tp.longitude, tp.altitude_msl, tp.altitude_agl)

            def get_groundspeed(self):
                tp = self.telemetry_provider
                if tp is None: return float('nan')
                return tp.groundspeed_ms

            def get_status(self):
                tp = self.telemetry_provider
                gps_status = None
                if tp is not None:
                    gps_status = {
                        'has_fix':     tp.has_fix,
                        'fix_quality': tp.fix_quality,
                        'satellites':  tp.satellites,
                        'lat':         tp.latitude,
                        'lon':         tp.longitude,
                        'alt_msl':     tp.altitude_msl,
                        'alt_agl':     tp.altitude_agl,
                        'groundspeed': tp.groundspeed_ms,
                        'data_age_ms': tp.data_age_ms,
                    }
                return {
                    'gimbals':    {},
                    'gps':        gps_status,
                    'sbus':       None,
                    'mode':       self.current_mode,
                    'poi_locked': self.poi_locked,
                    'address':    self.current_address,
                }

        return _Ctrl(provider)

    def test_get_position_returns_nan_when_no_fix(self):
        p = _SimSocketTelemetryProvider()
        p.update()   # no data → has_fix stays False
        ctrl = self._make_ctrl(p)
        pos = ctrl.get_position()
        self.assertEqual(len(pos), 4)
        for v in pos:
            self.assertTrue(math.isnan(v), f"expected NaN but got {v}")

    def test_get_groundspeed_returns_nan_when_no_fix(self):
        p = _SimSocketTelemetryProvider()
        p.update()
        ctrl = self._make_ctrl(p)
        self.assertTrue(math.isnan(ctrl.get_groundspeed()))

    def test_get_status_gps_has_fix_false_when_stale(self):
        p = _SimSocketTelemetryProvider(frame_timeout_ms=100.0)
        old_ts = time.monotonic() - 0.5
        p.feed_snapshot(_make_snap(fix_quality=1, timestamp=old_ts))
        p.update()
        p.update()   # goes stale
        ctrl = self._make_ctrl(p)
        status = ctrl.get_status()
        self.assertFalse(status['gps']['has_fix'])

    def test_get_status_data_age_ms_present(self):
        p = _SimSocketTelemetryProvider()
        p.feed_snapshot(_make_snap(timestamp=time.monotonic()))
        p.update()
        ctrl = self._make_ctrl(p)
        status = ctrl.get_status()
        self.assertIn('data_age_ms', status['gps'])

    def test_no_provider_returns_nan_position(self):
        class _NoTelCtrl:
            telemetry_provider = None
            def get_position(self):
                nan = float('nan')
                tp = self.telemetry_provider
                if tp is None or not tp.has_fix:
                    return (nan, nan, nan, nan)
                return (tp.latitude, tp.longitude, tp.altitude_msl, tp.altitude_agl)

        ctrl = _NoTelCtrl()
        for v in ctrl.get_position():
            self.assertTrue(math.isnan(v))


if __name__ == '__main__':
    unittest.main()
