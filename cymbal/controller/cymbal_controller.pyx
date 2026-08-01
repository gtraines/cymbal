"""
CymbalController — modular orchestrator for the Cymbal gimbal system.

This class replaces the monolithic GimbalController in cymbal/main.pyx.
Key differences from the old design:

  * All gimbal objects are **injected** at construction time rather than
    being instantiated internally.  This makes the controller embeddable
    inside any Python or Cython application.

  * No ``signal.signal()`` calls — process-level concerns belong in the
    application entry point (cymbal/main.pyx), not the library.

  * No ``logging.basicConfig()`` — callers configure logging.  The controller
    uses a passed-in logger or falls back to ``logging.getLogger(__name__)``.

  * Gimbals are managed by their GimbalDef id string, and channel commands
    use the new ``ChannelMapper.get_commands()`` path.

  * Telemetry (GPS, terrain, address) is provided via an injected
    ``TelemetryProvider``.  The default (when no provider is supplied) is
    ``InProcessTelemetryProvider`` which wraps the existing subsystems
    in-process.  In Phase 3, a ``SocketTelemetryProvider`` will be injected
    instead so telemetry runs in a separate sidecar process.

  * The legacy ``set_camera_position()``, ``set_spotlight_position()``, and
    ``sync_gimbals()`` convenience methods are preserved for backward
    compatibility (they delegate to ``set_gimbal_axes`` by role lookup).

Backward compatibility alias::

    from cymbal.controller import CymbalController
    # or the legacy name:
    GimbalController = CymbalController

Usage::

    from cymbal.gimbals import Storm32GimbalAdapter, ServoGimbalAdapter
    from cymbal.controller import CymbalController
    from cymbal.config.config import SystemConfig

    config = SystemConfig.load('/etc/cymbal/config.json')

    gimbals = [
        Storm32GimbalAdapter('camera_1', port='/dev/ttyAMA0'),
        ServoGimbalAdapter('spotlight_1', pitch_pin=17, yaw_pin=27),
    ]

    ctrl = CymbalController(gimbals, config)
    ctrl.initialize()
    ctrl.run()          # blocks until ctrl.shutdown() is called
    ctrl.shutdown()
"""

import math
import time
import logging

from cymbal.controller.telemetry_provider cimport TelemetryProvider, InProcessTelemetryProvider
from cymbal.controller.telemetry_provider import InProcessTelemetryProvider as _InProcessTelemetryPy
from cymbal.inputs.sbus_reader cimport SBUSReader
from cymbal.inputs.sbus_reader import SBUSReader
from cymbal.inputs.channel_mapper cimport ChannelMapper
from cymbal.inputs.channel_mapper import ChannelMapper, MODE_MANUAL, MODE_STABILIZE, MODE_TRACK
from libc.math cimport atan2, sqrt, cos, M_PI, isnan

_DEG_TO_RAD     = M_PI / 180.0
_METERS_PER_DEG = 111111.0


cdef class CymbalController:
    """
    Orchestrator for a configurable set of gimbal objects.

    Args:
        gimbals: List of GimbalBase instances to manage.  The list may
                 contain any mix of Storm32GimbalAdapter, ServoGimbalAdapter,
                 SimpleBGCGimbalAdapter, or custom implementations.
        config:  SystemConfig instance with GPS, OSD, SBUS, and channel map
                 settings.  The ``gimbals`` list takes precedence over the
                 legacy ``config.camera_gimbal`` / ``config.spotlight_gimbal``
                 fields for hardware initialisation.
        logger:  Optional logger.  Defaults to logging.getLogger(__name__).
    """

    def __init__(self, list gimbals, object config, object logger=None,
                 object telemetry_provider=None):
        self.gimbals = gimbals
        self.config  = config
        self.logger  = logger if logger is not None else logging.getLogger(__name__)

        self.telemetry_provider = telemetry_provider   # injected or built in initialize()
        self.sbus           = None
        self.channel_mapper = None

        self.running          = False
        self.poi_locked       = False
        self.poi_lat          = 0.0
        self.poi_lon          = 0.0
        self.current_address  = "No fix"
        self.current_mode     = MODE_MANUAL
        self._last_camera_yaw = float('nan')

        # Loop-timing stats
        self._loop_count       = 0
        self._loop_elapsed_sum = 0.0
        self._loop_elapsed_min = 1e9
        self._loop_elapsed_max = 0.0
        self._stats_window     = 100   # log every 100 iterations (~2 s at 50 Hz)
        self._last_mean_loop_ms = 0.0
        self._last_min_loop_ms  = 0.0
        self._last_max_loop_ms  = 0.0

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    cpdef bint initialize(self):
        """
        Initialize all subsystems and injected gimbals.

        Returns:
            True if at least one gimbal and all non-optional subsystems
            initialized successfully.
        """
        self.logger.info("CymbalController: initializing…")

        try:
            self._init_gimbals()
            self._init_telemetry_provider()
            self._init_sbus()
            self._init_channel_mapper()

            active = [g for g in self.gimbals if g is not None]
            if not active:
                self.logger.error("No gimbals initialized; aborting")
                return False

            self.logger.info(
                f"CymbalController initialized ({len(active)} gimbal(s))"
            )
            return True

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False

    cdef void _init_gimbals(self):
        initialized = []
        for gimbal in self.gimbals:
            try:
                if gimbal.initialize():
                    self.logger.info(
                        f"Gimbal '{gimbal.gimbal_id}' initialized "
                        f"(roles={gimbal.roles})"
                    )
                    initialized.append(gimbal)
                else:
                    self.logger.warning(
                        f"Gimbal '{gimbal.gimbal_id}' initialize() returned False"
                    )
            except Exception as e:
                self.logger.warning(
                    f"Gimbal '{gimbal.gimbal_id}' init error: {e}"
                )
        self.gimbals = initialized

    cdef void _init_telemetry_provider(self):
        """
        If no TelemetryProvider was injected, create an InProcessTelemetryProvider
        from the current config.  If one was injected, call its initialize().

        Blocking latency during initialize():
          - Serial port open:   < 1 ms (O_RDWR on /dev/ttyUSBx)
          - SQLite DB open:     < 5 ms (WAL mode, read-only)
          - SRTM file scan:     50-500 ms first call on cold cache (optional,
                                skipped when use_terrain_db=False)
        """
        if self.telemetry_provider is None:
            self.telemetry_provider = _InProcessTelemetryPy(
                gps_config=self.config.gps,
                geo_config=self.config.geo,
                gps_update_rate_hz=float(self.config.gps.update_rate_hz),
            )
        if not self.telemetry_provider.initialize():
            self.logger.warning(
                "TelemetryProvider.initialize() failed; telemetry features disabled"
            )

    cdef void _init_sbus(self):
        cfg = self.config.sbus
        if not cfg.enabled:
            self.logger.info("S-BUS disabled by config")
            return
        try:
            self.sbus = SBUSReader()
            if not self.sbus.connect(cfg.socket_path):
                self.logger.warning("S-BUS reader unavailable")
                self.sbus = None
        except Exception as e:
            self.logger.warning(f"S-BUS init error: {e}")
            self.sbus = None

    cdef void _init_channel_mapper(self):
        try:
            self.channel_mapper = ChannelMapper()
            if self.config.gimbals:
                # New modular path
                self.channel_mapper.initialize_from_gimbals(
                    self.config.gimbals,
                    mode_channel=self.config.channel_map.mode_select,
                    poi_lock_channel=self.config.channel_map.poi_lock,
                )
            else:
                # Legacy fallback
                self.channel_mapper.initialize(self.config.channel_map)
        except Exception as e:
            self.logger.warning(f"ChannelMapper init error: {e}")
            self.channel_mapper = None

    # ------------------------------------------------------------------
    # Main runtime loop
    # ------------------------------------------------------------------

    cpdef void run(self):
        """
        Run the main 50 Hz control loop.

        Blocking-latency budget per 20 ms loop iteration:
          SBUS update      : non-blocking Unix datagram drain, < 0.1 ms typical.
          Telemetry update : delegated to TelemetryProvider.update().
                             SocketTelemetryProvider (Phase 3): ~0.05 ms
                             (non-blocking socket drain, same pattern as SBUS).
                             InProcessTelemetryProvider (fallback): GPS serial
                             read ~1-5 ms at 5 Hz gate; SQLite ~1-5 ms at 1 Hz.
          Gimbal dispatch  : serial write to Storm32 ~1-2 ms; PWM pigpio ~0.1 ms.

        OSD/video rendering is no longer in the control loop.  It runs in the
        cymbal-video sidecar process (Phase 4), which consumes TelemetrySnapshot
        datagrams independently.

        Loop-timing instrumentation:
          Each iteration records elapsed wall time.  Every _stats_window (100)
          iterations, min/mean/max are logged at DEBUG level and stored in
          _last_min/mean/max_loop_ms for inspection via get_status().
        """
        cdef double loop_interval   = 1.0 / 50.0
        cdef double t, elapsed
        cdef double mean_ms

        self.logger.info("CymbalController: starting main loop (50 Hz)")
        self.running = True

        while self.running:
            t = time.monotonic()

            # ---- S-BUS (non-blocking socket drain, < 0.1 ms) ----
            if self.sbus is not None:
                self.sbus.update()
                if self.sbus.failsafe_active:
                    self._apply_failsafe()
                    self._sleep_to_interval(t, loop_interval)
                    continue

            # ---- Telemetry (rate-limited inside the provider) ----
            # InProcessTelemetryProvider: may block on GPS serial read (~1-5 ms)
            #   and/or SQLite address query (~1-5 ms) at their respective rates.
            # SocketTelemetryProvider (Phase 3): non-blocking socket read, < 0.1 ms.
            if self.telemetry_provider is not None:
                self.telemetry_provider.update()
                # Mirror address into controller field for get_status() callers.
                self.current_address = self.telemetry_provider.address

            # ---- POI lock check ----
            if (self.channel_mapper is not None and self.sbus is not None
                    and self.telemetry_provider is not None
                    and self.telemetry_provider.has_fix):
                if self.channel_mapper.get_poi_lock_triggered(self.sbus):
                    self._lock_poi(
                        self.telemetry_provider.latitude,
                        self.telemetry_provider.longitude,
                    )

            # ---- Gimbal commands (serial write ~1-2 ms, PWM ~0.1 ms) ----
            self._apply_control_mode()

            # ---- Sleep to maintain 50 Hz rate ----
            self._sleep_to_interval(t, loop_interval)

            # ---- Loop-timing instrumentation ----
            elapsed = time.monotonic() - t   # includes the sleep time
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
                self.logger.debug(
                    f"Loop timing (last {self._loop_count} iters): "
                    f"mean={mean_ms:.2f}ms "
                    f"min={self._last_min_loop_ms:.2f}ms "
                    f"max={self._last_max_loop_ms:.2f}ms"
                )
                # Reset for the next window
                self._loop_count       = 0
                self._loop_elapsed_sum = 0.0
                self._loop_elapsed_min = 1e9
                self._loop_elapsed_max = 0.0

        self.logger.info("CymbalController: main loop exited")

    cpdef void run_stabilization_loop(self, double update_rate=0.1):
        """Backward-compatible wrapper — delegates to run()."""
        self.run()

    # ------------------------------------------------------------------
    # Control mode dispatch
    # ------------------------------------------------------------------

    cdef void _apply_control_mode(self):
        cdef int mode = MODE_MANUAL
        cdef double poi_pitch, poi_yaw

        if self.channel_mapper is not None and self.sbus is not None:
            mode = self.channel_mapper.get_mode_index(self.sbus)
        self.current_mode = mode

        if mode == MODE_MANUAL:
            self._apply_manual_mode()

        elif mode == MODE_TRACK:
            if (self.poi_locked
                    and self.telemetry_provider is not None
                    and self.telemetry_provider.has_fix
                    and not isnan(self.telemetry_provider.altitude_agl)):
                poi_pitch, poi_yaw = self._compute_poi_angles(
                    self.telemetry_provider.latitude,
                    self.telemetry_provider.longitude,
                    self.telemetry_provider.altitude_agl,
                    self.poi_lat, self.poi_lon,
                )
                self._point_all_gimbals(poi_pitch, poi_yaw)
                if not isnan(self.telemetry_provider.track_degrees):
                    self._last_camera_yaw = poi_yaw - self.telemetry_provider.track_degrees
                else:
                    self._last_camera_yaw = poi_yaw

        elif mode == MODE_STABILIZE:
            for gimbal in self.gimbals:
                if hasattr(gimbal, 'stabilize'):
                    try:
                        gimbal.stabilize()
                    except Exception:
                        pass

    cdef void _apply_manual_mode(self):
        """Dispatch per-gimbal axis commands from S-BUS channels."""
        if self.channel_mapper is None or self.sbus is None:
            return

        # Modular path: get_commands returns {gimbal_id: {axis: degrees}}
        cmds = self.channel_mapper.get_commands(self.sbus)
        if cmds:
            for gimbal in self.gimbals:
                axes = cmds.get(gimbal.gimbal_id)
                if axes:
                    gimbal.set_axes(axes)
            # Update camera yaw for OSD compass (take from first camera gimbal)
            for gimbal in self.gimbals:
                if 'camera' in gimbal.roles and gimbal.gimbal_id in cmds:
                    yaw = cmds[gimbal.gimbal_id].get('yaw', float('nan'))
                    if not math.isnan(yaw):
                        self._last_camera_yaw = yaw
                    break
        else:
            # Fallback: legacy 4-key dict from get_gimbal_commands
            legacy = self.channel_mapper.get_gimbal_commands(self.sbus)
            self._apply_legacy_commands(legacy)

    cdef void _apply_legacy_commands(self, dict cmds):
        """Apply the legacy camera_pitch / spotlight_yaw style commands."""
        cam_pitch  = cmds.get('camera_pitch',    0.0)
        cam_yaw    = cmds.get('camera_yaw',       0.0)
        spot_pitch = cmds.get('spotlight_pitch',  0.0)
        spot_yaw   = cmds.get('spotlight_yaw',    0.0)

        for gimbal in self.gimbals:
            if 'camera' in gimbal.roles:
                gimbal.set_axes({'pitch': cam_pitch, 'roll': 0.0, 'yaw': cam_yaw})
            elif 'spotlight' in gimbal.roles:
                gimbal.set_axes({'pitch': spot_pitch, 'yaw': spot_yaw})

        self._last_camera_yaw = cam_yaw

    cdef void _apply_failsafe(self):
        self.logger.warning("S-BUS failsafe active — centering all gimbals")
        self.center_all()
        self._last_camera_yaw = 0.0

    # ------------------------------------------------------------------
    # POI tracking math
    # ------------------------------------------------------------------

    cdef tuple _compute_poi_angles(self, double ac_lat, double ac_lon,
                                   double ac_alt_agl,
                                   double poi_lat, double poi_lon):
        cdef double d_north, d_east, d_horiz, pitch_deg, yaw_deg
        cdef double cos_lat = cos(ac_lat * _DEG_TO_RAD)

        d_north = (poi_lat - ac_lat) * _METERS_PER_DEG
        d_east  = (poi_lon - ac_lon) * _METERS_PER_DEG * cos_lat
        d_horiz = sqrt(d_north * d_north + d_east * d_east)

        yaw_deg = atan2(d_east, d_north) * 180.0 / M_PI

        if d_horiz < 0.1:
            pitch_deg = -90.0
        else:
            pitch_deg = -atan2(ac_alt_agl, d_horiz) * 180.0 / M_PI

        return (pitch_deg, yaw_deg)

    cdef void _point_all_gimbals(self, double pitch, double yaw):
        """Point all gimbals to pitch / yaw (used in TRACK mode)."""
        for gimbal in self.gimbals:
            axes = {'pitch': pitch, 'yaw': yaw}
            if 'camera' in gimbal.roles:
                axes['roll'] = 0.0
            gimbal.set_axes(axes)

    # ------------------------------------------------------------------
    # POI lock
    # ------------------------------------------------------------------

    cpdef void lock_poi(self, double lat, double lon):
        self._lock_poi(lat, lon)

    cdef void _lock_poi(self, double lat, double lon):
        self.poi_lat    = lat
        self.poi_lon    = lon
        self.poi_locked = True
        self.logger.info(f"POI locked at ({lat:.5f}, {lon:.5f})")

    cpdef void unlock_poi(self):
        self.poi_locked = False
        self.logger.info("POI unlocked")

    # ------------------------------------------------------------------
    # Status and telemetry
    # ------------------------------------------------------------------

    cpdef tuple get_position(self):
        cdef double nan = float('nan')
        if self.telemetry_provider is None or not self.telemetry_provider.has_fix:
            return (nan, nan, nan, nan)
        return (
            self.telemetry_provider.latitude,
            self.telemetry_provider.longitude,
            self.telemetry_provider.altitude_msl,
            self.telemetry_provider.altitude_agl,
        )

    cpdef double get_groundspeed(self):
        if self.telemetry_provider is None:
            return float('nan')
        return self.telemetry_provider.groundspeed_ms

    cpdef dict get_status(self):
        cdef dict status = {
            'gimbals':    {},
            'gps':        None,
            'sbus':       None,
            'timing':     None,
            'mode':       self.current_mode,
            'poi_locked': self.poi_locked,
            'address':    self.current_address,
        }

        for gimbal in self.gimbals:
            try:
                status['gimbals'][gimbal.gimbal_id] = gimbal.get_status()
            except Exception:
                status['gimbals'][gimbal.gimbal_id] = {'error': 'get_status failed'}

        tp = self.telemetry_provider
        if tp is not None:
            status['gps'] = {
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

        if self.sbus:
            status['sbus'] = {
                'connected':  self.sbus.connected,
                'failsafe':   self.sbus.failsafe_active,
                'frame_lost': self.sbus.frame_lost,
            }

        # Loop-timing — populated after the first stats window completes.
        if self._last_mean_loop_ms > 0.0 or self._loop_count > 0:
            status['timing'] = {
                'mean_loop_ms':  self._last_mean_loop_ms,
                'min_loop_ms':   self._last_min_loop_ms,
                'max_loop_ms':   self._last_max_loop_ms,
                'stats_window':  self._stats_window,
            }

        return status

    # ------------------------------------------------------------------
    # Gimbal control API
    # ------------------------------------------------------------------

    cpdef void center_all(self):
        """Center every managed gimbal."""
        for gimbal in self.gimbals:
            try:
                gimbal.center()
            except Exception as e:
                self.logger.debug(f"center_all: gimbal '{gimbal.gimbal_id}' error: {e}")

    cpdef bint set_gimbal_axes(self, str gimbal_id, dict values):
        """Set axis angles on the gimbal identified by gimbal_id."""
        for gimbal in self.gimbals:
            if gimbal.gimbal_id == gimbal_id:
                try:
                    return gimbal.set_axes(values)
                except Exception as e:
                    self.logger.error(
                        f"set_gimbal_axes({gimbal_id}): {e}")
                    return False
        self.logger.warning(f"set_gimbal_axes: gimbal '{gimbal_id}' not found")
        return False

    # --- Backward-compat convenience methods ---

    def set_camera_position(self, double pitch, double roll, double yaw):
        """Set the first camera-role gimbal to pitch/roll/yaw."""
        for gimbal in self.gimbals:
            if 'camera' in gimbal.roles:
                return gimbal.set_axes({'pitch': pitch, 'roll': roll, 'yaw': yaw})
        return False

    def set_spotlight_position(self, double pitch, double yaw):
        """Set the first spotlight-role gimbal to pitch/yaw."""
        for gimbal in self.gimbals:
            if 'spotlight' in gimbal.roles:
                return gimbal.set_axes({'pitch': pitch, 'yaw': yaw})
        return False

    def sync_gimbals(self, double pitch, double yaw):
        """Point every gimbal to the same pitch/yaw."""
        for gimbal in self.gimbals:
            axes = {'pitch': pitch, 'yaw': yaw}
            if 'camera' in gimbal.roles:
                axes['roll'] = 0.0
            gimbal.set_axes(axes)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    cpdef void shutdown(self):
        """Gracefully stop the loop and close all subsystems."""
        self.logger.info("CymbalController: shutting down…")
        self.running = False

        for gimbal in self.gimbals:
            try:
                gimbal.shutdown()
            except Exception as e:
                self.logger.debug(f"shutdown: gimbal '{gimbal.gimbal_id}' error: {e}")

        if self.telemetry_provider is not None:
            try:
                self.telemetry_provider.close()
            except Exception as e:
                self.logger.debug(f"shutdown: telemetry_provider close error: {e}")

        if self.sbus:
            self.sbus.close()

        self.logger.info("CymbalController: shutdown complete")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    cdef void _sleep_to_interval(self, double t_start, double interval):
        cdef double elapsed  = time.monotonic() - t_start
        cdef double remaining = interval - elapsed
        if remaining > 0.0:
            time.sleep(remaining)


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

GimbalController = CymbalController
