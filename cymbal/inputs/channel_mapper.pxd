"""
Cython header file for ChannelMapper.
"""

cdef class ChannelMapper:
    cdef public int ch_camera_pitch
    cdef public int ch_camera_yaw
    cdef public int ch_spotlight_pitch
    cdef public int ch_spotlight_yaw
    cdef public int ch_mode_select
    cdef public int ch_poi_lock

    cdef double _cam_pitch_min, _cam_pitch_max
    cdef double _cam_yaw_min, _cam_yaw_max
    cdef double _spot_pitch_min, _spot_pitch_max
    cdef double _spot_yaw_min, _spot_yaw_max

    # POI lock is edge-triggered: track previous switch state
    cdef int _prev_poi_raw

    cpdef bint initialize(self, object config)
    cpdef dict get_gimbal_commands(self, object sbus)
    cpdef int get_mode_index(self, object sbus)
    cpdef bint get_poi_lock_triggered(self, object sbus)
    cpdef double map_channel_to_angle(self, int raw_value,
                                      double min_angle, double max_angle)
