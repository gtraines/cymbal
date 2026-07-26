"""
Cython header file for TerrainElevationDB.
"""

cdef class TerrainElevationDB:
    cdef public object _elevation_data
    cdef public str data_path
    cdef public bint is_initialized
    cdef public double nan_sentinel

    cpdef bint initialize(self, str data_path)
    cpdef double get_elevation(self, double lat, double lon)
    cpdef void close(self)
