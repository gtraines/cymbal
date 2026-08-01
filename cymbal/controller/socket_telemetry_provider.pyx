"""
SocketTelemetryProvider — non-blocking TelemetrySnapshot socket consumer.

Connects to the cymbal-telemetry sidecar over a Unix domain datagram socket
and provides the same TelemetryProvider interface as InProcessTelemetryProvider.

The control loop calls update() on every iteration.  update() is non-blocking:
it drains the receive buffer and applies the most recent snapshot, so the
control loop never waits on serial I/O or SQLite.

Staleness handling:
  If no snapshot has been received within frame_timeout_ms, the provider sets
  has_fix = False and address = "No fix" to signal that the data is stale.
  The last known lat/lon/altitude are preserved so callers that track heading
  can still display the last fix.

Socket convention (matches sbus_reader.pyx):
  Sidecar binds to:    socket_path          (e.g. /run/cymbal/telemetry.sock)
  Reader binds to:     socket_path + ".reader"
  Sidecar sends to:    socket_path + ".reader"
"""

from cymbal.controller.telemetry_provider cimport TelemetryProvider
from cymbal.controller.ipc_schemas import TelemetrySnapshotSchema

import logging
import os
import socket
import struct
import time as _time

logger = logging.getLogger(__name__)

_NAN      = float('nan')
_SNAP_SIZE = TelemetrySnapshotSchema.SIZE


cdef class SocketTelemetryProvider(TelemetryProvider):
    """
    Non-blocking TelemetryProvider that reads TelemetrySnapshot datagrams
    from the cymbal-telemetry sidecar process.

    Args:
        socket_path:      Path to the Unix socket where the sidecar publishes
                          e.g. /run/cymbal/telemetry.sock
        frame_timeout_ms: Milliseconds after which stale data is flagged.
                          Recommended: 2× sidecar publish interval.
    """

    def __init__(self, str socket_path, double frame_timeout_ms = 500.0):
        super().__init__()
        self.socket_path       = socket_path
        self.frame_timeout_ms  = frame_timeout_ms
        self._sock             = None
        self.connected         = False
        self.last_snapshot_time = 0.0
        self.max_data_age_ms   = 0.0
        self._prev_has_fix     = False

    cpdef bint initialize(self):
        """
        Open the non-blocking receive socket.

        Returns True if the socket was opened and bound successfully.
        Does NOT verify that the sidecar is running; the first call to
        update() will return False until the sidecar starts publishing.
        """
        return self.connect(self.socket_path)

    cpdef bint connect(self, str socket_path):
        """
        Open and bind the receive socket.

        Args:
            socket_path: Path to the sidecar's bound socket.

        Returns:
            True if the socket was opened successfully.
        """
        self.socket_path = socket_path
        bind_path = socket_path + ".reader"
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.setblocking(False)
            if os.path.exists(bind_path):
                os.unlink(bind_path)
            sock.bind(bind_path)
            self._sock = sock
            self.connected = True
            self.is_available = True
            logger.info(f"SocketTelemetryProvider connected to {socket_path}")
            return True
        except Exception as e:
            logger.error(f"SocketTelemetryProvider: failed to open socket: {e}")
            self.connected = False
            return False

    cpdef bint update(self):
        """
        Drain the receive buffer and apply the most recent snapshot.

        Non-blocking: returns False immediately if no new data is available.

        Staleness check: if now - last_snapshot_time > frame_timeout_ms,
        clears has_fix and address to signal stale data.

        Returns:
            True  if at least one new snapshot was received and decoded.
            False if no data was available, the socket is not connected,
                  or only a decoding error occurred.
        """
        cdef bint got_data = False
        cdef bytes latest  = None
        cdef double now    = _time.monotonic()

        if not self.connected or self._sock is None:
            self._mark_stale(now)
            return False

        # Drain the socket buffer, keeping only the most recent datagram.
        try:
            while True:
                data = self._sock.recv(_SNAP_SIZE)
                if len(data) == _SNAP_SIZE:
                    latest = data
        except BlockingIOError:
            pass  # Buffer empty — expected in non-blocking mode
        except Exception as e:
            logger.warning(f"SocketTelemetryProvider socket error: {e}")
            self.connected = False
            self._mark_stale(now)
            return False

        if latest is not None:
            if self._apply_snapshot(latest, now):
                got_data = True
        else:
            # No new data — check staleness
            self._check_staleness(now)

        return got_data

    cdef bint _apply_snapshot(self, bytes data, double now):
        """Unpack a raw TelemetrySnapshot datagram and update all fields."""
        snap = TelemetrySnapshotSchema.unpack(data)
        if not snap.get('valid', False):
            logger.warning("SocketTelemetryProvider: received invalid snapshot (bad magic)")
            return False

        cdef bint was_stale = not self._prev_has_fix and snap['fix_quality'] > 0

        self.has_fix          = snap['fix_quality'] > 0
        self.fix_quality      = snap['fix_quality']
        self.satellites       = snap['satellites']
        self.latitude         = snap['lat']
        self.longitude        = snap['lon']
        self.altitude_msl     = snap['alt_msl']
        self.altitude_agl     = snap['alt_agl']
        self.groundspeed_ms   = snap['groundspeed_ms']
        self.track_degrees    = snap['track_degrees']
        self.address          = snap['address']

        self.last_snapshot_time = snap['timestamp']
        cdef double age_ms = (now - snap['timestamp']) * 1000.0
        self.data_age_ms = age_ms

        # Update high-water mark
        if age_ms > self.max_data_age_ms:
            self.max_data_age_ms = age_ms

        # Log recovery from stale state
        if was_stale:
            logger.info(
                f"SocketTelemetryProvider: telemetry recovered "
                f"(data_age_ms={age_ms:.1f})"
            )

        self._prev_has_fix = self.has_fix
        return True

    cdef void _check_staleness(self, double now):
        """Mark stale if the last snapshot is too old."""
        if self.last_snapshot_time <= 0.0:
            # Never received a snapshot yet
            self.data_age_ms = _NAN
            return
        cdef double age_ms = (now - self.last_snapshot_time) * 1000.0
        self.data_age_ms = age_ms
        if age_ms > self.frame_timeout_ms:
            self._mark_stale(now)

    cdef void _mark_stale(self, double now):
        """Clear fields that should not be used when data is stale; log the event."""
        cdef bint was_fresh = self._prev_has_fix

        self.has_fix     = False
        self.address     = "No fix"
        # Preserve lat/lon/altitude so the last known position is still
        # readable; callers must check has_fix before relying on them.
        if self.last_snapshot_time > 0.0:
            cdef double age_ms = (now - self.last_snapshot_time) * 1000.0
            self.data_age_ms = age_ms
            if age_ms > self.max_data_age_ms:
                self.max_data_age_ms = age_ms
        else:
            self.data_age_ms = _NAN

        # Log fresh→stale transition once (not on every subsequent update)
        if was_fresh:
            logger.warning(
                f"SocketTelemetryProvider: telemetry went stale "
                f"(age={self.data_age_ms:.1f}ms > timeout={self.frame_timeout_ms:.0f}ms)"
            )
            self._prev_has_fix = False

    cpdef void close(self):
        """Close the receive socket and clean up the bind path."""
        bind_path = self.socket_path + ".reader"
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            try:
                if os.path.exists(bind_path):
                    os.unlink(bind_path)
            except Exception:
                pass
            self._sock = None
        self.connected = False
        super().close()
        logger.debug("SocketTelemetryProvider closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
