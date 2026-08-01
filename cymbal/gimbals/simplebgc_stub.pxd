"""
Cython header file for SimpleBGCGimbalAdapter.
"""

from cymbal.gimbals.base cimport GimbalBase

cdef class SimpleBGCGimbalAdapter(GimbalBase):
    cdef public str port
    cdef public int baudrate

    cpdef bint initialize(self)
    cpdef bint center(self)
    cpdef bint set_axes(self, dict values)
    cpdef dict get_status(self)
    cpdef void shutdown(self)
