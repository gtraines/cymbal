"""
Cython header file for CymbalController.

Subsystem handles use typed cimport declarations so callers that cimport
CymbalController can resolve field types at the C level without Python
object-protocol overhead.
"""

from cymbal.controller.telemetry_provider cimport TelemetryProvider
from cymbal.inputs.sbus_reader cimport SBUSReader
from cymbal.inputs.channel_mapper cimport ChannelMapper


cdef class CymbalController:
    cdef public object config
    cdef public object logger

    # Injected gimbal list
    cdef public list gimbals

    # Telemetry provider — typed so cimport callers read fields without boxing.
    # Default: InProcessTelemetryProvider; replaceable with SocketTelemetryProvider.
    cdef TelemetryProvider telemetry_provider

    # Remaining in-process subsystem handles.
    # OSD/video is now the responsibility of the cymbal-video sidecar (Phase 4).
    cdef SBUSReader    sbus
    cdef ChannelMapper channel_mapper

    # Loop state
    cdef public bint running

    # POI tracking
    cdef public bint poi_locked
    cdef public double poi_lat
    cdef public double poi_lon

    # Cached telemetry
    cdef public str current_address
    cdef public int current_mode
    cdef public double _last_camera_yaw

    # Loop-timing instrumentation (Phase 6).
    # Stats are accumulated over _stats_window iterations then reset.
    # Last-window values are exposed via get_status() under the 'timing' key.
    cdef int    _loop_count
    cdef double _loop_elapsed_sum
    cdef double _loop_elapsed_min
    cdef double _loop_elapsed_max
    cdef int    _stats_window
    # Last completed window — safe to read from get_status() while running.
    cdef public double _last_mean_loop_ms
    cdef public double _last_min_loop_ms
    cdef public double _last_max_loop_ms

    cpdef bint initialize(self)
    cpdef void run(self)
    cpdef void run_stabilization_loop(self, double update_rate=*)
    cpdef void shutdown(self)
    cpdef void center_all(self)
    cpdef bint set_gimbal_axes(self, str gimbal_id, dict values)
    cpdef dict get_status(self)
    cpdef tuple get_position(self)
    cpdef double get_groundspeed(self)
    cpdef void lock_poi(self, double lat, double lon)
    cpdef void unlock_poi(self)
