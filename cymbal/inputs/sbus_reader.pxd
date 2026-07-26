"""
Cython header file for SBUSReader.
"""

cdef class SBUSReader:
    cdef object _sock
    cdef public str socket_path
    cdef public bint connected
    cdef public bint failsafe_active
    cdef public bint frame_lost
    cdef public double last_update_time
    cdef public int[18] channels

    cpdef bint connect(self, str socket_path)
    cpdef bint update(self)
    cpdef int get_channel(self, int channel_number)
    cpdef double get_channel_normalized(self, int channel_number)
    cpdef void close(self)
    cdef void _apply_payload(self, bytes data)
