"""
Cython header file for GPSSensor.
"""

cdef class GPSSensor:
    cdef object _serial
    cdef object _terrain_db
    cdef public str port
    cdef public int baudrate
    cdef public double latitude
    cdef public double longitude
    cdef public double altitude_msl
    cdef public double altitude_agl
    cdef public double groundspeed_ms
    cdef public double track_degrees
    cdef public int fix_quality
    cdef public int satellites
    cdef public double hdop
    cdef public double vdop
    cdef public bint has_fix
    cdef public bint use_terrain_db
    cdef double _nan

    cpdef bint initialize(self, str port, int baudrate)
    cpdef bint update(self)
    cpdef double get_terrain_elevation(self, double lat, double lon)
    cpdef void close(self)
    cpdef bint _parse_gga(self, object msg)
    cpdef bint _parse_vtg(self, object msg)
    cpdef bint _parse_rmc(self, object msg)
