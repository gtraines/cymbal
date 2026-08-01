"""
Cython header file for TelemetryProvider and InProcessTelemetryProvider.

Import with:
    from cymbal.controller.telemetry_provider cimport TelemetryProvider
    from cymbal.controller.telemetry_provider cimport InProcessTelemetryProvider
"""

from cymbal.sensors.gps_sensor cimport GPSSensor
from cymbal.geo.terrain_elevation cimport TerrainElevationDB
from cymbal.geo.address_lookup cimport AddressLookup


cdef class TelemetryProvider:
    # Published fields — all readable at C level by cimport consumers.
    cdef public bint   has_fix
    cdef public bint   is_available
    cdef public double latitude
    cdef public double longitude
    cdef public double altitude_msl
    cdef public double altitude_agl
    cdef public double groundspeed_ms
    cdef public double track_degrees
    cdef public int    fix_quality
    cdef public int    satellites
    cdef public str    address
    # Staleness indicator: milliseconds since last successful data update.
    # 0.0 for in-process providers; >0 for socket-based providers.
    cdef public double data_age_ms

    cpdef bint initialize(self)
    cpdef bint update(self)
    cpdef void close(self)


cdef class InProcessTelemetryProvider(TelemetryProvider):
    # Config objects (Python dataclass instances, held as object)
    cdef object _gps_config
    cdef object _geo_config

    # Rate-limiting intervals (seconds)
    cdef double _gps_interval
    cdef double _addr_interval
    cdef double _last_gps_t
    cdef double _last_addr_t

    # Wrapped subsystems (typed)
    cdef GPSSensor        _gps
    cdef TerrainElevationDB _terrain_db
    cdef AddressLookup    _address_lookup

    cpdef bint initialize(self)
    cpdef bint update(self)
    cpdef void close(self)
    cdef  void _sync_from_gps(self)
