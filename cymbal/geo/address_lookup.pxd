"""
Cython header file for AddressLookup.
"""

cdef class AddressLookup:
    cdef public object _db_conn
    cdef public str data_path
    cdef public bint is_initialized
    cdef double _search_radius_deg
    cdef int _max_candidates

    cpdef bint initialize(self, str data_path)
    cpdef str reverse_geocode(self, double lat, double lon)
    cpdef dict get_location_info(self, double lat, double lon)
    cpdef void close(self)
    cdef list _query_candidates(self, double lat, double lon)
    cdef dict _best_candidate(self, double lat, double lon, list candidates)
