"""
Cython header file for Storm32Controller
"""

cdef class Storm32Controller:
    cdef public str port
    cdef public int baudrate
    cdef public double timeout
    cdef object serial_conn
    cdef bint _is_connected
    
    cpdef bint connect(self)
    cpdef void disconnect(self)
    cpdef bint is_connected(self)
    cpdef bint set_angle(self, double pitch, double roll, double yaw)
    cpdef bint set_speed(self, double pitch_speed, double roll_speed, double yaw_speed)
    cpdef object get_status(self)
    cpdef bint center(self)
    cdef bytes _build_angle_command(self, double pitch, double roll, double yaw)
    cdef bytes _build_speed_command(self, double pitch_speed, double roll_speed, double yaw_speed)
    cdef bytes _build_status_request(self)
    cdef dict _parse_status_response(self, bytes response)
