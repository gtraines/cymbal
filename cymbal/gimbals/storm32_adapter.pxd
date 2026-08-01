"""
Cython header file for Storm32GimbalAdapter.
"""

from cymbal.gimbals.base cimport GimbalBase
from cymbal.camera_gimbal.storm32_controller cimport Storm32Controller

cdef class Storm32GimbalAdapter(GimbalBase):
    cdef Storm32Controller _controller
    cdef public str port
    cdef public int baudrate
    cdef public double timeout

    cpdef bint initialize(self)
    cpdef bint center(self)
    cpdef bint set_axes(self, dict values)
    cpdef dict get_status(self)
    cpdef void shutdown(self)
