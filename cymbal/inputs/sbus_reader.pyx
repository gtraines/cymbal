"""
S-BUS Reader — Unix Domain Socket Consumer

Connects to the sbus-decoder service over /run/cymbal/sbus.sock and provides
a non-blocking interface to the latest decoded channel values.

Socket transport format (binary, big-endian, 48 bytes per datagram):
  Offset  Size  Type    Field
  0       4     4s      Magic bytes b'SBUS'
  4       32    16H     Channel values 1-16 (uint16, 0-2047 each)
  36      1     B       Digital channel 17 (0 or 1)
  37      1     B       Digital channel 18 (0 or 1)
  38      1     B       frame_lost flag (0 or 1)
  39      1     B       failsafe_active flag (0 or 1)
  40      8     d       Monotonic timestamp (float, seconds)

The socket is SOCK_DGRAM (connectionless); the reader receives the latest
datagram and discards older ones in the OS buffer so it always returns the
most recently decoded frame.
"""

import logging
import socket
import struct
import time as _time

# --- Futaba endpoints (mirror sbus_decoder constants for normalization) ---
_SBUS_CH_MIN = 172
_SBUS_CH_MID = 992
_SBUS_CH_MAX = 1811
_SBUS_SAFE   = _SBUS_CH_MID

logger = logging.getLogger(__name__)

# Shared payload struct — import this in sbus_service.py too
SBUS_MAGIC          = b'SBUS'
SBUS_PAYLOAD_STRUCT = struct.Struct('!4s16HBBBBd')
SBUS_PAYLOAD_SIZE   = SBUS_PAYLOAD_STRUCT.size   # 48 bytes


cdef class SBUSReader:
    """
    Non-blocking consumer of decoded S-BUS channel data over a Unix socket.

    Intended to be polled from the main GimbalController loop at ≥50 Hz.
    update() is non-blocking: it drains the receive buffer and keeps the
    most recent datagram.  If the service has not sent a new frame, the
    previous values are preserved.
    """

    def __init__(self):
        self._sock = None
        self.socket_path = ""
        self.connected = False
        self.failsafe_active = False
        self.frame_lost = False
        self.last_update_time = 0.0
        cdef int i
        for i in range(18):
            self.channels[i] = _SBUS_SAFE

    cpdef bint connect(self, str socket_path):
        """
        Open a non-blocking DGRAM socket pointed at the S-BUS service.

        Args:
            socket_path: Path to the Unix socket, e.g. /run/cymbal/sbus.sock.

        Returns:
            True if the socket was opened successfully.
        """
        self.socket_path = socket_path
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.setblocking(False)
            # Bind to an abstract address so we can receive datagrams
            # (DGRAM sockets need a bound address to receive on Linux).
            import tempfile, os
            bind_path = socket_path + ".reader"
            if os.path.exists(bind_path):
                os.unlink(bind_path)
            sock.bind(bind_path)
            self._sock = sock
            self.connected = True
            logger.info(f"SBUSReader connected to {socket_path}")
            return True
        except Exception as e:
            logger.error(f"SBUSReader: failed to connect to {socket_path}: {e}")
            self.connected = False
            return False

    cpdef bint update(self):
        """
        Drain the socket receive buffer and apply the most recent frame.

        Non-blocking: returns False immediately if no new data is available.

        Returns:
            True  if at least one new datagram was received and decoded.
            False if no data was available or a socket error occurred.
        """
        cdef bint got_data = False
        cdef bytes latest = None

        if not self.connected or self._sock is None:
            return False

        # Drain the socket buffer, keeping only the most recent datagram.
        try:
            while True:
                data = self._sock.recv(SBUS_PAYLOAD_SIZE)
                if len(data) == SBUS_PAYLOAD_SIZE:
                    latest = data
        except BlockingIOError:
            pass  # Buffer empty — expected in non-blocking mode
        except Exception as e:
            logger.warning(f"SBUSReader socket error: {e}")
            self.connected = False
            return False

        if latest is not None:
            self._apply_payload(latest)
            got_data = True

        return got_data

    cdef void _apply_payload(self, bytes data):
        """Unpack a raw 48-byte datagram and update channel state."""
        cdef int i
        try:
            fields = SBUS_PAYLOAD_STRUCT.unpack(data)
        except struct.error as e:
            logger.warning(f"SBUSReader: malformed datagram: {e}")
            return

        magic = fields[0]
        if magic != SBUS_MAGIC:
            logger.warning(f"SBUSReader: bad magic {magic!r}, expected {SBUS_MAGIC!r}")
            return

        # fields[1:17] = 16 channel values
        for i in range(16):
            self.channels[i] = fields[1 + i]
        self.channels[16]    = fields[17]   # digital ch17
        self.channels[17]    = fields[18]   # digital ch18
        self.frame_lost      = bool(fields[19])
        self.failsafe_active = bool(fields[20])
        self.last_update_time = fields[21]

    cpdef int get_channel(self, int channel_number):
        """
        Return raw 11-bit channel value (1-indexed, 0–2047).

        Args:
            channel_number: 1 through 18.

        Returns:
            Raw value 0–2047, or _SBUS_SAFE on out-of-range.
        """
        if channel_number < 1 or channel_number > 18:
            return _SBUS_SAFE
        return self.channels[channel_number - 1]

    cpdef double get_channel_normalized(self, int channel_number):
        """
        Return channel value normalized to –1.0 to +1.0 (Futaba 172/992/1811).

        Args:
            channel_number: 1-indexed channel number (1–16).

        Returns:
            Float in [-1.0, 1.0], clamped.
        """
        cdef int raw = self.get_channel(channel_number)
        cdef double norm

        if raw <= _SBUS_CH_MID:
            norm = (raw - _SBUS_CH_MID) / float(_SBUS_CH_MID - _SBUS_CH_MIN)
        else:
            norm = (raw - _SBUS_CH_MID) / float(_SBUS_CH_MAX - _SBUS_CH_MID)

        if norm < -1.0:
            norm = -1.0
        if norm > 1.0:
            norm = 1.0
        return norm

    cpdef void close(self):
        """Close the socket."""
        import os
        if self._sock is not None:
            bind_path = self.socket_path + ".reader"
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
        logger.debug("SBUSReader closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
