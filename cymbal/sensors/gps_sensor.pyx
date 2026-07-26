"""
USB GPS Sensor Interface

Reads NMEA-0183 sentences from a USB GPS receiver (e.g. u-blox, GlobalTop)
and provides position, altitude, groundspeed, and computed AGL altitude.

NMEA library choice: pynmea2 (https://github.com/Knio/pynmea2)
  - Purpose-built for NMEA 0183; exposes typed fields and decimal degree helpers.
  - Lightweight: pure Python, <5ms per sentence parse in benchmarks.
  - Supports GGA (position/altitude/fix quality), VTG (speed/track), and RMC
    (combined position/speed) out of the box.
  - gpsd was rejected: introduces a background daemon dependency and additional
    inter-process latency; the direct serial approach is simpler and sufficient
    for the 5 Hz update rate requirement.

AGL computation:
  altitude_agl = gps_altitude_msl - terrain_elevation(lat, lon)

When use_terrain_db=False or the terrain lookup misses, altitude_agl is set to
NaN. Callers must check math.isnan(sensor.altitude_agl) before relying on it.

Hardware assumptions:
  - GPS module on /dev/ttyUSB0 at 9600 baud (NMEA default).
  - The module outputs GGA sentences at ≥1 Hz; update() should be called at
    the configured update rate (default 5 Hz).
"""

from libc.math cimport isnan
import io
import logging
import math
import serial

try:
    import pynmea2
except ImportError:
    pynmea2 = None

logger = logging.getLogger(__name__)

_NAN = float('nan')


cdef class GPSSensor:
    """
    Interface for a USB NMEA GPS receiver.

    Parses GGA, VTG, and RMC sentences to track position, altitude,
    groundspeed, and fix quality. Optionally computes AGL altitude from
    a TerrainElevationDB instance injected at construction time.
    """

    def __init__(self, terrain_db=None):
        """
        Args:
            terrain_db: Optional TerrainElevationDB instance for AGL computation.
                        If None, altitude_agl remains NaN.
        """
        self._serial = None
        self._terrain_db = terrain_db
        self.port = ""
        self.baudrate = 9600

        self.latitude = _NAN
        self.longitude = _NAN
        self.altitude_msl = _NAN
        self.altitude_agl = _NAN
        self.groundspeed_ms = _NAN
        self.track_degrees = _NAN
        self.fix_quality = 0
        self.satellites = 0
        self.hdop = _NAN
        self.vdop = _NAN
        self.has_fix = False
        self.use_terrain_db = terrain_db is not None
        self._nan = _NAN

    cpdef bint initialize(self, str port, int baudrate):
        """
        Open the serial port to the GPS module.

        Args:
            port:     Serial device path, e.g. /dev/ttyUSB0
            baudrate: Baud rate (default 9600 for most NMEA GPS modules)

        Returns:
            True if the port opened successfully.
        """
        if pynmea2 is None:
            logger.error("pynmea2 not installed; run: pip install pynmea2")
            return False

        self.port = port
        self.baudrate = baudrate
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1.0,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            logger.info(f"GPSSensor opened {port} @ {baudrate} baud")
            return True
        except Exception as e:
            logger.error(f"Failed to open GPS port {port}: {e}")
            return False

    cpdef bint update(self):
        """
        Read and parse one complete NMEA cycle from the serial port.

        Reads lines until a valid GGA sentence is processed or the read
        times out. Updates all public fields in place.

        Returns:
            True if at least one sentence was parsed and produced a valid fix.
        """
        if self._serial is None:
            logger.warning("GPSSensor.update() called before initialize()")
            return False

        cdef bint updated = False
        cdef int max_lines = 20

        try:
            for _ in range(max_lines):
                raw_line = self._serial.readline()
                if not raw_line:
                    break
                try:
                    line = raw_line.decode('ascii', errors='replace').strip()
                    msg = pynmea2.parse(line)
                except pynmea2.ParseError:
                    continue
                except Exception:
                    continue

                sentence_type = msg.sentence_type
                if sentence_type == 'GGA':
                    updated = self._parse_gga(msg) or updated
                elif sentence_type == 'VTG':
                    updated = self._parse_vtg(msg) or updated
                elif sentence_type == 'RMC':
                    updated = self._parse_rmc(msg) or updated

                if updated:
                    break

        except Exception as e:
            logger.warning(f"GPS read error: {e}")

        return updated

    cpdef bint _parse_gga(self, object msg):
        """Parse a GGA sentence for position, altitude, and fix quality."""
        cdef int q
        try:
            q = int(msg.gps_qual) if msg.gps_qual else 0
            self.fix_quality = q
            self.has_fix = q > 0

            if self.has_fix:
                self.latitude = float(msg.latitude)
                self.longitude = float(msg.longitude)
                self.altitude_msl = float(msg.altitude)
                self.satellites = int(msg.num_sats) if msg.num_sats else 0
                self.hdop = float(msg.horizontal_dil) if msg.horizontal_dil else _NAN

                if self.use_terrain_db and self._terrain_db is not None:
                    terrain_elev = self.get_terrain_elevation(self.latitude, self.longitude)
                    if not math.isnan(terrain_elev):
                        self.altitude_agl = self.altitude_msl - terrain_elev
                    else:
                        self.altitude_agl = _NAN
                else:
                    self.altitude_agl = _NAN

                return True
        except Exception as e:
            logger.debug(f"GGA parse error: {e}")
        return False

    cpdef bint _parse_vtg(self, object msg):
        """Parse a VTG sentence for groundspeed and track."""
        try:
            if msg.spd_over_grnd_kmph is not None and msg.spd_over_grnd_kmph != '':
                self.groundspeed_ms = float(msg.spd_over_grnd_kmph) / 3.6
            if msg.true_track is not None and msg.true_track != '':
                self.track_degrees = float(msg.true_track)
            return True
        except Exception as e:
            logger.debug(f"VTG parse error: {e}")
        return False

    cpdef bint _parse_rmc(self, object msg):
        """Parse an RMC sentence for position, speed, and track (fallback)."""
        try:
            if hasattr(msg, 'status') and msg.status != 'A':
                return False
            if self.latitude != self.latitude:  # NaN check
                self.latitude = float(msg.latitude)
                self.longitude = float(msg.longitude)
            if msg.spd_over_grnd is not None and msg.spd_over_grnd != '':
                # RMC speed is in knots; convert to m/s
                self.groundspeed_ms = float(msg.spd_over_grnd) * 0.514444
            if msg.true_course is not None and msg.true_course != '':
                self.track_degrees = float(msg.true_course)
            return True
        except Exception as e:
            logger.debug(f"RMC parse error: {e}")
        return False

    cpdef double get_terrain_elevation(self, double lat, double lon):
        """
        Return terrain elevation (m MSL) from the injected TerrainElevationDB.

        Returns NaN if no terrain DB was provided or the lookup fails.
        """
        if self._terrain_db is None:
            return self._nan
        return self._terrain_db.get_elevation(lat, lon)

    cpdef void close(self):
        """Close the serial port."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self.has_fix = False
        logger.info("GPSSensor closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
