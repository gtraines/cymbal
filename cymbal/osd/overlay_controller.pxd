"""
Cython header file for OSDOverlay.
"""

cdef class OSDOverlay:
    cdef public bint enabled
    cdef public double font_scale
    cdef public int font_thickness
    cdef object _text_color
    cdef object _bg_color
    cdef public double background_alpha
    cdef public bint show_sbus_channels
    cdef public bint show_compass
    cdef public int compass_radius
    cdef public bint show_heading_tape
    cdef public double heading_tape_height_pct
    cdef public double heading_tape_width_pct
    cdef public double heading_tape_fov_deg

    # Video sink (optional)
    cdef object _video_sink

    # Timestamp injection (callable → datetime)
    cdef object _time_fn

    # Timezone for local timestamp display
    cdef public str local_timezone   # IANA timezone name, e.g. "America/Phoenix"
    cdef object _local_tz            # zoneinfo.ZoneInfo instance, or None

    # Cached aircraft telemetry values
    cdef public double lat
    cdef public double lon
    cdef public double alt_agl          # altitude AGL, metres
    cdef public double alt_msl          # altitude MSL, metres
    cdef public double groundspeed_ms   # ground speed, m/s
    cdef public str address
    cdef public int fix_quality
    cdef public int satellites
    cdef public object sbus_channels    # list/tuple of int
    cdef public double track_degrees    # GPS ground track, degrees from N clockwise
    cdef public double camera_yaw_deg   # camera yaw relative to aircraft nose, degrees

    # Cached target/POI values
    cdef public bint poi_locked
    cdef public double poi_lat
    cdef public double poi_lon
    cdef public double poi_alt_msl      # target terrain elevation, metres MSL
    cdef public double slant_range_ft   # 3D aircraft→target distance, feet
    cdef public str poi_address

    cpdef bint initialize(self, object video_sink=*)
    cpdef void update_telemetry(self, double lat, double lon, double alt_agl,
                                double groundspeed, str address,
                                int fix_quality, int satellites,
                                object sbus_channels,
                                double track_degrees,
                                double camera_yaw_deg,
                                double alt_msl=*)
    cpdef void update_target(self, bint poi_locked, double poi_lat, double poi_lon,
                             double poi_alt_msl, double slant_range_m,
                             str poi_address)
    cpdef void render_frame(self, object frame)
    cpdef void close(self)
    cdef void _draw_text_box(self, object frame, list lines, int x, int y,
                             object text_color=*)
    cdef void _draw_compass_widget(self, object frame, int cx, int cy,
                                   int radius, double track_deg,
                                   double camera_yaw_deg)
    cdef void _draw_heading_tape(self, object frame, double camera_heading_deg)
    cdef void _draw_crosshair(self, object frame)
    cdef void _draw_target_panel(self, object frame)
    cdef void _draw_datetime_panel(self, object frame)
    cdef void _put_text_shadowed(self, object frame, str text, int x, int y,
                                  double scale, object color, int thickness)
