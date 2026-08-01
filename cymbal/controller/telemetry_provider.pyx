"""
TelemetryProvider — abstract interface and in-process implementation.

Decouples CymbalController from directly owning GPSSensor, TerrainElevationDB,
and AddressLookup.  The controller reads telemetry through a TelemetryProvider
reference; the concrete implementation is injected at construction time.

Two implementations exist at this phase:

  InProcessTelemetryProvider
      Wraps GPSSensor + TerrainElevationDB + AddressLookup in the same process.
      This is a behavioural no-op relative to the old design: it produces
      identical results but through the provider interface.

  (Future, Phase 3) SocketTelemetryProvider
      Reads TelemetrySnapshot structs from a Unix datagram socket published by
      the cymbal-telemetry sidecar process, and populates the same public fields.
      The controller requires no further changes because it talks only to the
      TelemetryProvider interface.

Blocking-latency notes for InProcessTelemetryProvider.update():
  - GPSSensor.update()        : serial readline, timeout=1.0 s worst-case,
                                 typically 1-5 ms per NMEA sentence.
  - AddressLookup.reverse_geocode(): SQLite R*-tree query, ~1-5 ms typical.
  Both are rate-limited internally so they only run when their interval has
  elapsed, not on every call to update().
"""

from cymbal.sensors.gps_sensor cimport GPSSensor
from cymbal.sensors.gps_sensor import GPSSensor as _GPSSensorPy
from cymbal.geo.terrain_elevation cimport TerrainElevationDB
from cymbal.geo.terrain_elevation import TerrainElevationDB as _TerrainDBPy
from cymbal.geo.address_lookup cimport AddressLookup
from cymbal.geo.address_lookup import AddressLookup as _AddressLookupPy

import logging
import time as _time

logger = logging.getLogger(__name__)

_NAN = float('nan')


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

cdef class TelemetryProvider:
    """
    Abstract interface for position and telemetry data.

    All public fields are populated by update(); consumers read them directly
    at the C level without Python boxing overhead.

    Implementations must override initialize(), update(), and close().
    """

    def __init__(self):
        # Initialise all published fields to safe sentinel values so callers
        # never see uninitialised memory even before the first update().
        self.has_fix          = False
        self.is_available     = False
        self.latitude         = _NAN
        self.longitude        = _NAN
        self.altitude_msl     = _NAN
        self.altitude_agl     = _NAN
        self.groundspeed_ms   = _NAN
        self.track_degrees    = _NAN
        self.fix_quality      = 0
        self.satellites       = 0
        self.address          = "No fix"
        self.data_age_ms      = _NAN

    cpdef bint initialize(self):
        """
        Open hardware/socket connections.

        Returns True on success.  Must be called before the first update().
        Subclasses should set self.is_available = True on success.
        """
        raise NotImplementedError("TelemetryProvider.initialize() not implemented")

    cpdef bint update(self):
        """
        Refresh all published fields from the underlying data source.

        Returns True if at least one field changed since the last call.
        This method should be cheap to call on every loop iteration;
        implementations are responsible for their own rate limiting.
        """
        raise NotImplementedError("TelemetryProvider.update() not implemented")

    cpdef void close(self):
        """Release all resources."""
        self.is_available = False


# ---------------------------------------------------------------------------
# In-process implementation
# ---------------------------------------------------------------------------

cdef class InProcessTelemetryProvider(TelemetryProvider):
    """
    TelemetryProvider that wraps GPSSensor, TerrainElevationDB, and
    AddressLookup in the same process.

    GPS and address-lookup updates are rate-limited internally:
      - GPS: updated at gps_update_rate_hz (default 5 Hz)
      - Address: updated at address_update_rate_hz (default 1 Hz)

    This is a drop-in replacement for the old in-controller subsystems; the
    controller loop calls update() once per iteration and reads fields directly.
    """

    def __init__(
        self,
        object gps_config,
        object geo_config,
        double gps_update_rate_hz = 5.0,
        double address_update_rate_hz = 1.0,
    ):
        """
        Args:
            gps_config:   GPSConfig dataclass instance.
            geo_config:   GeoConfig dataclass instance.
            gps_update_rate_hz:     Rate at which GPSSensor.update() is called.
            address_update_rate_hz: Rate at which reverse geocoding is called.
        """
        super().__init__()

        self._gps_config     = gps_config
        self._geo_config     = geo_config
        self._gps_interval   = 1.0 / max(gps_update_rate_hz, 0.1)
        self._addr_interval  = 1.0 / max(address_update_rate_hz, 0.01)

        self._gps            = None
        self._terrain_db     = None
        self._address_lookup = None

        self._last_gps_t     = 0.0
        self._last_addr_t    = 0.0

    cpdef bint initialize(self):
        """
        Open GPS serial port, terrain DB, and address lookup database.

        Returns True if at least GPS is available (terrain and address are
        optional; failures there are logged but do not prevent initialization).
        """
        cdef bint gps_ok = False

        # ---- Terrain elevation DB (optional) ----
        if self._gps_config.use_terrain_db:
            try:
                self._terrain_db = _TerrainDBPy()
                if not self._terrain_db.initialize(self._gps_config.terrain_db_path):
                    logger.warning("InProcessTelemetryProvider: terrain DB unavailable; AGL will be NaN")
                    self._terrain_db = None
            except Exception as e:
                logger.warning(f"InProcessTelemetryProvider: terrain DB init error: {e}")
                self._terrain_db = None
        else:
            logger.info("InProcessTelemetryProvider: terrain DB disabled by config")

        # ---- GPS sensor ----
        try:
            self._gps = _GPSSensorPy(terrain_db=self._terrain_db)
            if self._gps.initialize(self._gps_config.port, self._gps_config.baudrate):
                gps_ok = True
                logger.info(
                    f"InProcessTelemetryProvider: GPS opened on "
                    f"{self._gps_config.port} @ {self._gps_config.baudrate} baud"
                )
            else:
                logger.warning("InProcessTelemetryProvider: GPS unavailable; position features disabled")
                self._gps = None
        except Exception as e:
            logger.warning(f"InProcessTelemetryProvider: GPS init error: {e}")
            self._gps = None

        # ---- Address lookup (optional) ----
        if self._geo_config.enabled:
            try:
                self._address_lookup = _AddressLookupPy()
                if not self._address_lookup.initialize(self._geo_config.address_db_path):
                    logger.warning("InProcessTelemetryProvider: address lookup unavailable")
                    self._address_lookup = None
            except Exception as e:
                logger.warning(f"InProcessTelemetryProvider: address lookup init error: {e}")
                self._address_lookup = None
        else:
            logger.info("InProcessTelemetryProvider: address lookup disabled by config")

        self.is_available = True   # provider is structurally online even if GPS is absent
        return True                # always succeeds; GPS failure is a warning, not fatal

    cpdef bint update(self):
        """
        Rate-limited update of GPS + address fields.

        - GPS is updated at the configured rate (default 5 Hz).
        - Address lookup is updated at 1 Hz, only when GPS has a fix.
        - All TelemetryProvider public fields are refreshed after each GPS read.

        Blocking latency (worst-case):
          GPS serial read:    up to 1.0 s (serial timeout) if no data available.
                              Typically < 5 ms when data arrives at 5 Hz.
          Address SQLite:     ~1-5 ms per query at the R*-tree index; only runs 1 Hz.

        Returns True if any field changed.
        """
        cdef double t       = _time.monotonic()
        cdef bint   changed = False

        # ---- GPS update (rate-limited) ----
        if self._gps is not None and (t - self._last_gps_t) >= self._gps_interval:
            changed = self._gps.update() or changed  # [BLOCKING ~1-5 ms serial read]
            self._last_gps_t = t
            self._sync_from_gps()

        # ---- Address lookup (rate-limited, only when fix available) ----
        if (self._address_lookup is not None
                and self.has_fix
                and (t - self._last_addr_t) >= self._addr_interval):
            new_addr = self._address_lookup.reverse_geocode(  # [BLOCKING ~1-5 ms SQLite]
                self.latitude, self.longitude
            )
            if new_addr != self.address:
                self.address = new_addr
                changed = True
            self._last_addr_t = t

        self.data_age_ms = 0.0   # in-process data is always current
        return changed

    cdef void _sync_from_gps(self):
        """Copy all GPS sensor fields into the provider's public attributes."""
        if self._gps is None:
            self.has_fix        = False
            self.latitude       = _NAN
            self.longitude      = _NAN
            self.altitude_msl   = _NAN
            self.altitude_agl   = _NAN
            self.groundspeed_ms = _NAN
            self.track_degrees  = _NAN
            self.fix_quality    = 0
            self.satellites     = 0
            if not self.has_fix:
                self.address    = "No fix"
            return

        self.has_fix        = self._gps.has_fix
        self.fix_quality    = self._gps.fix_quality
        self.satellites     = self._gps.satellites

        if self._gps.has_fix:
            self.latitude       = self._gps.latitude
            self.longitude      = self._gps.longitude
            self.altitude_msl   = self._gps.altitude_msl
            self.altitude_agl   = self._gps.altitude_agl
            self.groundspeed_ms = self._gps.groundspeed_ms
            self.track_degrees  = self._gps.track_degrees
        else:
            self.latitude       = _NAN
            self.longitude      = _NAN
            self.altitude_msl   = _NAN
            self.altitude_agl   = _NAN
            self.groundspeed_ms = _NAN
            self.track_degrees  = _NAN
            self.address        = "No fix"

    cpdef void close(self):
        """Close all subsystems."""
        if self._gps is not None:
            try:
                self._gps.close()
            except Exception:
                pass
            self._gps = None

        if self._address_lookup is not None:
            try:
                self._address_lookup.close()
            except Exception:
                pass
            self._address_lookup = None

        if self._terrain_db is not None:
            try:
                self._terrain_db.close()
            except Exception:
                pass
            self._terrain_db = None

        super().close()
        logger.info("InProcessTelemetryProvider closed")
