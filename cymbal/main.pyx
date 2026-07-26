"""
Main control application for dual gimbal system.

Coordinates control of both camera and spotlight gimbals from a Raspberry Pi 3B+,
integrating GPS positioning, terrain elevation, offline reverse geocoding,
S-BUS RC input, and on-screen display.
"""

import math
import time
import logging
import signal
import sys
from typing import Optional

from cymbal.camera_gimbal.storm32_controller cimport Storm32Controller
from cymbal.camera_gimbal.storm32_controller import Storm32Controller
from cymbal.spotlight_gimbal.servo_controller cimport SpotlightController
from cymbal.spotlight_gimbal.servo_controller import SpotlightController
from cymbal.sensors.gps_sensor cimport GPSSensor
from cymbal.sensors.gps_sensor import GPSSensor
from cymbal.geo.terrain_elevation cimport TerrainElevationDB
from cymbal.geo.terrain_elevation import TerrainElevationDB
from cymbal.geo.address_lookup cimport AddressLookup
from cymbal.geo.address_lookup import AddressLookup
from cymbal.inputs.sbus_reader cimport SBUSReader
from cymbal.inputs.sbus_reader import SBUSReader
from cymbal.inputs.channel_mapper cimport ChannelMapper
from cymbal.inputs.channel_mapper import ChannelMapper, MODE_MANUAL, MODE_STABILIZE, MODE_TRACK
from cymbal.osd.overlay_controller cimport OSDOverlay
from cymbal.osd.overlay_controller import OSDOverlay
from cymbal.utils.config import SystemConfig
from libc.math cimport atan2, sqrt, cos, M_PI, isnan


# ---------------------------------------------------------------------------
# POI tracking math constants
# ---------------------------------------------------------------------------
_DEG_TO_RAD     = M_PI / 180.0
_METERS_PER_DEG = 111111.0   # approximate metres per degree latitude


cdef class GimbalController:
    """
    Main controller for the Cymbal dual-gimbal system.

    Manages camera and spotlight gimbals, GPS, terrain elevation,
    reverse geocoding, S-BUS RC input, channel mapping, and OSD.
    """

    cdef object config
    cdef object logger

    # Hardware controllers (existing)
    cdef Storm32Controller camera_gimbal
    cdef SpotlightController spotlight_gimbal

    # Phase 2 — geo / GPS
    cdef GPSSensor gps
    cdef TerrainElevationDB terrain_db
    cdef AddressLookup address_lookup

    # Phase 3 — S-BUS
    cdef SBUSReader sbus

    # Phase 4 — channel mapping, OSD
    cdef ChannelMapper channel_mapper
    cdef OSDOverlay osd

    # Loop state
    cdef public bint running

    # POI tracking
    cdef public bint poi_locked
    cdef public double poi_lat
    cdef public double poi_lon

    # Cached telemetry (read by OSD / status)
    cdef public str current_address
    cdef public int current_mode
    cdef public double _last_camera_yaw   # degrees from nose; NaN until first command

    def __init__(self, config: SystemConfig):
        self.config = config
        self.logger = self._setup_logging()

        self.camera_gimbal   = None
        self.spotlight_gimbal = None
        self.gps             = None
        self.terrain_db      = None
        self.address_lookup  = None
        self.sbus            = None
        self.channel_mapper  = None
        self.osd             = None

        self.running         = False
        self.poi_locked      = False
        self.poi_lat         = 0.0
        self.poi_lon         = 0.0
        self.current_address = "No fix"
        self.current_mode    = MODE_MANUAL
        self._last_camera_yaw = float('nan')

        signal.signal(signal.SIGINT,  self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logging(self):
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('/var/log/cymbal.log'),
            ],
        )
        return logging.getLogger(__name__)

    def _signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    cpdef bint initialize(self):
        """
        Initialize all subsystems in dependency order.

        Returns:
            True if at least one gimbal and all non-optional subsystems
            initialized successfully.
        """
        self.logger.info("Initializing Cymbal gimbal control system...")

        try:
            self._init_gimbals()
            self._init_terrain_db()
            self._init_gps()
            self._init_address_lookup()
            self._init_sbus()
            self._init_channel_mapper()
            self._init_osd()

            if self.camera_gimbal is None and self.spotlight_gimbal is None:
                self.logger.error("No gimbals initialized; aborting")
                return False

            self.logger.info("Cymbal system initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False

    cdef void _init_gimbals(self):
        cam = self.config.camera_gimbal
        try:
            self.camera_gimbal = Storm32Controller(
                port=cam.serial_port, baudrate=cam.baudrate, timeout=cam.timeout)
            if not self.camera_gimbal.connect():
                self.logger.warning("Camera gimbal unavailable")
                self.camera_gimbal = None
            else:
                self.logger.info("Camera gimbal connected")
        except Exception as e:
            self.logger.warning(f"Camera gimbal init error: {e}")
            self.camera_gimbal = None

        spot = self.config.spotlight_gimbal
        try:
            self.spotlight_gimbal = SpotlightController(
                pitch_pin=spot.pitch_pin, yaw_pin=spot.yaw_pin,
                i2c_address=spot.i2c_address, i2c_bus=spot.i2c_bus,
                use_stabilization=spot.use_stabilization)
            if not self.spotlight_gimbal.initialize():
                self.logger.warning("Spotlight gimbal unavailable")
                self.spotlight_gimbal = None
            else:
                self.logger.info("Spotlight gimbal initialized")
        except Exception as e:
            self.logger.warning(f"Spotlight gimbal init error: {e}")
            self.spotlight_gimbal = None

    cdef void _init_terrain_db(self):
        cfg = self.config.gps
        if not cfg.use_terrain_db:
            self.logger.info("Terrain DB disabled by config")
            return
        try:
            self.terrain_db = TerrainElevationDB()
            if not self.terrain_db.initialize(cfg.terrain_db_path):
                self.logger.warning("Terrain DB initialization failed; AGL will be NaN")
                self.terrain_db = None
        except Exception as e:
            self.logger.warning(f"Terrain DB init error: {e}")
            self.terrain_db = None

    cdef void _init_gps(self):
        cfg = self.config.gps
        try:
            self.gps = GPSSensor(terrain_db=self.terrain_db)
            if not self.gps.initialize(cfg.port, cfg.baudrate):
                self.logger.warning("GPS unavailable; position features disabled")
                self.gps = None
        except Exception as e:
            self.logger.warning(f"GPS init error: {e}")
            self.gps = None

    cdef void _init_address_lookup(self):
        cfg = self.config.geo
        if not cfg.enabled:
            self.logger.info("Address lookup disabled by config")
            return
        try:
            self.address_lookup = AddressLookup()
            if not self.address_lookup.initialize(cfg.address_db_path):
                self.logger.warning("Address lookup unavailable")
                self.address_lookup = None
        except Exception as e:
            self.logger.warning(f"Address lookup init error: {e}")
            self.address_lookup = None

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
            self.channel_mapper.initialize(self.config.channel_map)
        except Exception as e:
            self.logger.warning(f"ChannelMapper init error: {e}")
            self.channel_mapper = None

    cdef void _init_osd(self):
        try:
            self.osd = OSDOverlay(self.config.osd)
            if not self.osd.initialize():
                self.logger.warning("OSD unavailable (OpenCV missing?)")
                self.osd = None
        except Exception as e:
            self.logger.warning(f"OSD init error: {e}")
            self.osd = None

    # ------------------------------------------------------------------
    # Main runtime loop
    # ------------------------------------------------------------------

    cpdef void run(self):
        """
        Run the main 50 Hz control loop.

        Polls S-BUS at 50 Hz, GPS at the configured rate, and updates
        the OSD at 10 Hz.  Applies manual/stabilize/track mode logic.
        """
        cdef double loop_interval   = 1.0 / 50.0          # 20 ms
        cdef double gps_interval    = 1.0 / max(self.config.gps.update_rate_hz, 1)
        cdef double osd_interval    = 0.1                  # 10 Hz
        cdef double address_interval = 1.0                 # 1 Hz
        cdef double last_gps_t      = 0.0
        cdef double last_osd_t      = 0.0
        cdef double last_addr_t     = 0.0
        cdef double t, elapsed

        self.logger.info("Starting main control loop (50 Hz)")
        self.running = True

        while self.running:
            t = time.monotonic()

            # -- S-BUS input (every iteration) --
            if self.sbus is not None:
                self.sbus.update()
                if self.sbus.failsafe_active:
                    self._apply_failsafe()
                    self._sleep_to_interval(t, loop_interval)
                    continue

            # -- GPS --
            if self.gps is not None and (t - last_gps_t) >= gps_interval:
                self.gps.update()
                last_gps_t = t

            # -- POI lock check --
            if (self.channel_mapper is not None and self.sbus is not None
                    and self.gps is not None and self.gps.has_fix):
                if self.channel_mapper.get_poi_lock_triggered(self.sbus):
                    self._lock_poi(self.gps.latitude, self.gps.longitude)

            # -- Address lookup (1 Hz) --
            if (self.address_lookup is not None and self.gps is not None
                    and self.gps.has_fix and (t - last_addr_t) >= address_interval):
                self.current_address = self.address_lookup.reverse_geocode(
                    self.gps.latitude, self.gps.longitude)
                last_addr_t = t

            # -- Gimbal command application --
            self._apply_control_mode()

            # -- OSD (10 Hz) --
            if self.osd is not None and (t - last_osd_t) >= osd_interval:
                self._update_osd()
                last_osd_t = t

            self._sleep_to_interval(t, loop_interval)

        self.logger.info("Main control loop exited")

    # Keep the old entry point for backward compatibility
    cpdef void run_stabilization_loop(self, double update_rate=0.1):
        """
        Backward-compatible wrapper — runs the full control loop.

        The update_rate parameter is ignored; the loop always runs at 50 Hz.
        """
        self.run()

    # ------------------------------------------------------------------
    # Control mode dispatch
    # ------------------------------------------------------------------

    cdef void _apply_control_mode(self):
        """Dispatch gimbal commands based on the current operating mode."""
        cdef int mode = MODE_MANUAL
        cdef dict cmds
        cdef double poi_pitch, poi_yaw

        if self.channel_mapper is not None and self.sbus is not None:
            mode = self.channel_mapper.get_mode_index(self.sbus)
        self.current_mode = mode

        if mode == MODE_MANUAL:
            if self.channel_mapper is not None and self.sbus is not None:
                cmds = self.channel_mapper.get_gimbal_commands(self.sbus)
                self.set_camera_position(
                    cmds['camera_pitch'], 0.0, cmds['camera_yaw'])
                self.set_spotlight_position(
                    cmds['spotlight_pitch'], cmds['spotlight_yaw'])
                self._last_camera_yaw = cmds['camera_yaw']

        elif mode == MODE_TRACK:
            if (self.poi_locked and self.gps is not None and self.gps.has_fix
                    and not isnan(self.gps.altitude_agl)):
                poi_pitch, poi_yaw = self._compute_poi_angles(
                    self.gps.latitude, self.gps.longitude, self.gps.altitude_agl,
                    self.poi_lat, self.poi_lon)
                self.sync_gimbals(poi_pitch, poi_yaw)
                # In TRACK mode the camera yaw is the absolute bearing offset
                # from the aircraft nose = poi_yaw - gps.track_degrees
                if not isnan(self.gps.track_degrees):
                    self._last_camera_yaw = poi_yaw - self.gps.track_degrees
                else:
                    self._last_camera_yaw = poi_yaw

        elif mode == MODE_STABILIZE:
            if self.spotlight_gimbal is not None:
                try:
                    self.spotlight_gimbal.stabilize()
                except Exception:
                    pass
            # In stabilize mode, camera yaw stays at last known value

    cdef void _apply_failsafe(self):
        """Center all gimbals immediately on S-BUS failsafe."""
        self.logger.warning("S-BUS failsafe active — centering gimbals")
        self.center_all()
        self._last_camera_yaw = 0.0

    # ------------------------------------------------------------------
    # POI tracking math
    # ------------------------------------------------------------------

    cdef tuple _compute_poi_angles(self, double ac_lat, double ac_lon,
                                   double ac_alt_agl,
                                   double poi_lat, double poi_lon):
        """
        Compute the gimbal pitch and yaw angles to point at a ground POI.

        Args:
            ac_lat, ac_lon:  Aircraft position (decimal degrees).
            ac_alt_agl:      Aircraft altitude above ground (metres).
            poi_lat, poi_lon: POI coordinates (decimal degrees).

        Returns:
            (pitch_deg, yaw_deg) — pitch is ≤ 0 (looking down).
        """
        cdef double d_north, d_east, d_horiz, pitch_deg, yaw_deg
        cdef double cos_lat = cos(ac_lat * _DEG_TO_RAD)

        d_north = (poi_lat - ac_lat) * _METERS_PER_DEG
        d_east  = (poi_lon - ac_lon) * _METERS_PER_DEG * cos_lat
        d_horiz = sqrt(d_north * d_north + d_east * d_east)

        # Yaw: bearing from aircraft to POI (degrees from true north)
        yaw_deg = atan2(d_east, d_north) * 180.0 / M_PI

        # Pitch: angle below horizontal to ground POI (negative = down)
        if d_horiz < 0.1:
            pitch_deg = -90.0   # directly below
        else:
            pitch_deg = -atan2(ac_alt_agl, d_horiz) * 180.0 / M_PI

        return (pitch_deg, yaw_deg)

    cpdef void lock_poi(self, double lat, double lon):
        """Lock the given coordinates as the current POI target."""
        self._lock_poi(lat, lon)

    cdef void _lock_poi(self, double lat, double lon):
        self.poi_lat    = lat
        self.poi_lon    = lon
        self.poi_locked = True
        self.logger.info(f"POI locked at ({lat:.5f}, {lon:.5f})")

    cpdef void unlock_poi(self):
        """Release the current POI lock."""
        self.poi_locked = False
        self.logger.info("POI unlocked")

    # ------------------------------------------------------------------
    # OSD update
    # ------------------------------------------------------------------

    cdef void _update_osd(self):
        cdef double lat, lon, alt_agl, gs, track_deg, cam_yaw
        cdef int fix_q, sats, i

        lat      = 0.0
        lon      = 0.0
        alt_agl  = float('nan')
        gs       = float('nan')
        track_deg = float('nan')
        cam_yaw  = self._last_camera_yaw
        fix_q    = 0
        sats     = 0

        if self.gps is not None:
            lat       = self.gps.latitude
            lon       = self.gps.longitude
            alt_agl   = self.gps.altitude_agl
            gs        = self.gps.groundspeed_ms
            fix_q     = self.gps.fix_quality
            sats      = self.gps.satellites
            track_deg = self.gps.track_degrees

        # Convert C int[18] array to Python list for OSD display
        sbus_ch = []
        if self.sbus is not None:
            for i in range(18):
                sbus_ch.append(self.sbus.channels[i])

        self.osd.update_telemetry(
            lat, lon, alt_agl, gs,
            self.current_address, fix_q, sats, sbus_ch,
            track_deg, cam_yaw,
        )

    # ------------------------------------------------------------------
    # Status and telemetry accessors
    # ------------------------------------------------------------------

    cpdef tuple get_position(self):
        """
        Return current GPS position.

        Returns:
            (latitude, longitude, altitude_msl, altitude_agl) as floats,
            or all NaN if GPS is unavailable or has no fix.
        """
        cdef double nan
        nan = float('nan')
        if self.gps is None or not self.gps.has_fix:
            return (nan, nan, nan, nan)
        return (self.gps.latitude, self.gps.longitude,
                self.gps.altitude_msl, self.gps.altitude_agl)

    cpdef double get_groundspeed(self):
        """
        Return current ground speed in m/s, or NaN if unavailable.
        """
        if self.gps is None:
            return float('nan')
        return self.gps.groundspeed_ms

    cpdef dict get_status(self):
        """Return a status snapshot of all subsystems."""
        cdef dict status = {
            'camera_gimbal':   None,
            'spotlight_gimbal': None,
            'gps':             None,
            'sbus':            None,
            'mode':            self.current_mode,
            'poi_locked':      self.poi_locked,
            'address':         self.current_address,
        }

        if self.camera_gimbal:
            status['camera_gimbal'] = self.camera_gimbal.get_status()

        if self.spotlight_gimbal:
            status['spotlight_gimbal'] = {
                'orientation': self.spotlight_gimbal.get_orientation(),
                'target_pitch': self.spotlight_gimbal.target_pitch,
                'target_yaw':   self.spotlight_gimbal.target_yaw,
            }

        if self.gps:
            status['gps'] = {
                'has_fix':      self.gps.has_fix,
                'fix_quality':  self.gps.fix_quality,
                'satellites':   self.gps.satellites,
                'lat':          self.gps.latitude,
                'lon':          self.gps.longitude,
                'alt_msl':      self.gps.altitude_msl,
                'alt_agl':      self.gps.altitude_agl,
                'groundspeed':  self.gps.groundspeed_ms,
            }

        if self.sbus:
            status['sbus'] = {
                'connected':   self.sbus.connected,
                'failsafe':    self.sbus.failsafe_active,
                'frame_lost':  self.sbus.frame_lost,
            }

        return status

    # ------------------------------------------------------------------
    # Existing gimbal control API (preserved)
    # ------------------------------------------------------------------

    cpdef void center_all(self):
        """Center both gimbals."""
        if self.camera_gimbal:
            self.camera_gimbal.center()
        if self.spotlight_gimbal:
            self.spotlight_gimbal.center()

    cpdef bint set_camera_position(self, double pitch, double roll, double yaw):
        """Set camera gimbal angles (degrees)."""
        if not self.camera_gimbal:
            return False
        return self.camera_gimbal.set_angle(pitch, roll, yaw)

    cpdef bint set_spotlight_position(self, double pitch, double yaw):
        """Set spotlight gimbal position (degrees)."""
        if not self.spotlight_gimbal:
            return False
        return self.spotlight_gimbal.set_position(pitch, yaw)

    cpdef void sync_gimbals(self, double pitch, double yaw):
        """Point both gimbals to the same pitch/yaw."""
        if self.camera_gimbal:
            self.camera_gimbal.set_angle(pitch, 0, yaw)
        if self.spotlight_gimbal:
            self.spotlight_gimbal.set_position(pitch, yaw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    cdef void _sleep_to_interval(self, double t_start, double interval):
        """Sleep for whatever remains of the loop interval."""
        cdef double elapsed = time.monotonic() - t_start
        cdef double remaining = interval - elapsed
        if remaining > 0.0:
            time.sleep(remaining)

    cpdef void shutdown(self):
        """Gracefully shut down all subsystems."""
        self.logger.info("Shutting down Cymbal system...")
        self.running = False

        if self.camera_gimbal:
            self.camera_gimbal.disconnect()
        if self.spotlight_gimbal:
            self.spotlight_gimbal.close()
        if self.gps:
            self.gps.close()
        if self.address_lookup:
            self.address_lookup.close()
        if self.terrain_db:
            self.terrain_db.close()
        if self.sbus:
            self.sbus.close()
        if self.osd:
            self.osd.close()

        self.logger.info("Cymbal system shutdown complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for cymbal.main module."""
    config = SystemConfig.load('/etc/cymbal/config.json')
    controller = GimbalController(config)

    if not controller.initialize():
        print("Failed to initialize Cymbal system", file=sys.stderr)
        return 1

    controller.center_all()
    print("Cymbal system ready — press Ctrl+C to exit")

    try:
        controller.run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
