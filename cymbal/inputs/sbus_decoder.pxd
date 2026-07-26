"""
Cython header file for SBUSDecoder.
"""

cdef class SBUSDecoder:
    cdef public int[18] channels
    cdef public bint frame_lost
    cdef public bint failsafe_active
    cdef public double last_frame_time
    cdef public unsigned long long frame_count
    cdef public unsigned long long error_count

    cpdef bint decode_frame(self, bytes frame_bytes)
    cpdef bint is_valid_frame(self, bytes frame_bytes)
    cpdef int get_channel(self, int channel_number)
    cpdef double get_channel_normalized(self, int channel_number)
    cpdef double get_channel_percent(self, int channel_number)
    cdef void _unpack_channels(self, bytes frame_bytes)
    cdef void _reset_safe(self)
