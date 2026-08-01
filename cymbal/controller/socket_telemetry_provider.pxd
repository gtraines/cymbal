"""
Cython header file for SocketTelemetryProvider.
"""

from cymbal.controller.telemetry_provider cimport TelemetryProvider


cdef class SocketTelemetryProvider(TelemetryProvider):
    cdef public str    socket_path
    cdef public double frame_timeout_ms
    cdef public bint   connected
    cdef public double last_snapshot_time
    # Staleness high-water mark: the worst (largest) data_age_ms seen
    # since the provider was initialised.  Never reset to allow post-flight
    # inspection of peak IPC latency.
    cdef public double max_data_age_ms
    cdef object _sock
    # Tracks previous has_fix for logging stale/recover transitions.
    cdef bint   _prev_has_fix

    cpdef bint initialize(self)
    cpdef bint connect(self, str socket_path)
    cpdef bint update(self)
    cpdef void close(self)
    cdef  bint _apply_snapshot(self, bytes data, double now)
    cdef  void _check_staleness(self, double now)
    cdef  void _mark_stale(self, double now)
