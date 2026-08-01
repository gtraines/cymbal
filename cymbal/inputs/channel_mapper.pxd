"""
Cython header file for ChannelMapper.
"""

cdef class ChannelMapper:
    # --- Legacy fields (backward compat) ---
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

    # --- Modular per-gimbal/axis mapping ---
    # dict: (gimbal_id, axis_name) -> (sbus_channel, min_deg, max_deg)
    cdef dict _axis_map

    cpdef bint initialize(self, object config)
    cpdef bint initialize_from_gimbals(self, list gimbal_defs,
                                       int mode_channel=*, int poi_lock_channel=*)
    cpdef dict get_gimbal_commands(self, object sbus)
    cpdef dict get_commands(self, object sbus)
    cpdef int get_mode_index(self, object sbus)
    cpdef bint get_poi_lock_triggered(self, object sbus)
    cpdef double map_channel_to_angle(self, int raw_value,
                                      double min_angle, double max_angle)
