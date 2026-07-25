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

    # Cached telemetry values
    cdef public double lat
    cdef public double lon
    cdef public double alt_agl
    cdef public double groundspeed_ms
    cdef public str address
    cdef public int fix_quality
    cdef public int satellites
    cdef public object sbus_channels   # list/tuple of int

    cpdef bint initialize(self)
    cpdef void update_telemetry(self, double lat, double lon, double alt_agl,
                                double groundspeed, str address,
                                int fix_quality, int satellites,
                                object sbus_channels)
    cpdef void render_frame(self, object frame)
    cpdef void close(self)
    cdef void _draw_text_box(self, object frame, list lines, int x, int y)
