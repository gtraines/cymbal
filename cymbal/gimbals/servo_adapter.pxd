"""
Cython header file for ServoGimbalAdapter.
"""

from cymbal.gimbals.base cimport GimbalBase
from cymbal.spotlight_gimbal.servo_controller cimport SpotlightController

cdef class ServoGimbalAdapter(GimbalBase):
    cdef SpotlightController _controller
    cdef public int pitch_pin
    cdef public int yaw_pin
    cdef public int i2c_address
    cdef public int i2c_bus
    cdef public bint use_stabilization

    cpdef bint initialize(self)
    cpdef bint center(self)
    cpdef bint set_axes(self, dict values)
    cpdef dict get_status(self)
    cpdef void shutdown(self)
    cpdef bint stabilize(self)
