"""
Cython header file for GimbalBase.

Provides the cimport interface for all gimbal adapter implementations.
"""

cdef class GimbalBase:
    cdef public str gimbal_id
    cdef public list roles
    cdef public dict axes

    cpdef bint initialize(self)
    cpdef bint center(self)
    cpdef bint set_axes(self, dict values)
    cpdef dict get_status(self)
    cpdef void shutdown(self)
