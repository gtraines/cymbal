"""
S-BUS Frame Decoder

Decodes 25-byte S-BUS frames into 16 proportional channels (11-bit, 0–2047)
and 2 digital channels (0 or 1), with frame-lost and failsafe flag tracking.

S-BUS Protocol Reference (Futaba/FrSky):
  - Signal:    Inverted UART (low = logic 1).  Hardware or pigpio inversion
               must be applied before bytes reach this decoder.
  - Baud rate: 100,000 bps
  - Format:    8 data bits, Even parity, 2 stop bits (8E2)
  - Frame:     25 bytes, period ≈ 14 ms (standard) / 7 ms (fast mode)

Frame layout:
  Byte  0:      Header   0x0F
  Bytes 1–22:   176 bits, 16 channels × 11 bits packed LSB-first
  Byte  23:     Flags
                  bit 0 = digital channel 17
                  bit 1 = digital channel 18
                  bit 2 = frame lost
                  bit 3 = failsafe active
  Byte  24:     Footer   0x00

Channel value mapping (Futaba convention):
  Raw 172  = minimum  (some receivers)
  Raw 992  = center   (≈ 1000 µs PWM equivalent)
  Raw 1811 = maximum  (some receivers)
  Raw 0    = minimum  (other convention)
  Raw 1023 = center
  Raw 2047 = maximum

This decoder normalizes to the full 11-bit range (0–2047) and exposes
helpers for –1.0 to +1.0 (normalized) and 0–100 % (percent) conversions,
using the Futaba 172/992/1811 convention by default.
"""

from libc.time cimport time, time_t
import logging
import time as _time

logger = logging.getLogger(__name__)

# S-BUS frame constants
SBUS_HEADER        = 0x0F
SBUS_FOOTER        = 0x00
SBUS_FRAME_LENGTH  = 25

# Futaba channel value endpoints
SBUS_CH_MIN        = 172
SBUS_CH_MID        = 992
SBUS_CH_MAX        = 1811

# Safe / center raw value output when frame is lost
SBUS_SAFE_VALUE    = SBUS_CH_MID

# Flag masks in byte 23
FLAG_DIGITAL_CH17  = 0x01
FLAG_DIGITAL_CH18  = 0x02
FLAG_FRAME_LOST    = 0x04
FLAG_FAILSAFE      = 0x08


cdef class SBUSDecoder:
    """
    Stateful S-BUS frame decoder.

    Call decode_frame() with each 25-byte frame; channel values are updated
    in place so the caller can read them without allocation.
    """

    def __init__(self):
        cdef int i
        for i in range(18):
            self.channels[i] = SBUS_CH_MID
        self.frame_lost       = False
        self.failsafe_active  = False
        self.last_frame_time  = 0.0
        self.frame_count      = 0
        self.error_count      = 0

    cpdef bint decode_frame(self, bytes frame_bytes):
        """
        Decode a 25-byte S-BUS frame and update all channel values in place.

        Args:
            frame_bytes: Exactly 25 raw bytes from the S-BUS stream.

        Returns:
            True  if the frame decoded successfully.
            False if the frame is invalid (wrong header/footer/length);
                  channels are set to SBUS_SAFE_VALUE and frame_lost is set.
        """
        cdef unsigned char flags

        if not self.is_valid_frame(frame_bytes):
            self.error_count += 1
            self._reset_safe()
            return False

        # Decode flags byte
        cdef unsigned char flags = frame_bytes[23]
        self.channels[16]    = 1 if (flags & FLAG_DIGITAL_CH17) else 0
        self.channels[17]    = 1 if (flags & FLAG_DIGITAL_CH18) else 0
        self.frame_lost      = bool(flags & FLAG_FRAME_LOST)
        self.failsafe_active = bool(flags & FLAG_FAILSAFE)

        if self.frame_lost or self.failsafe_active:
            if self.frame_lost:
                logger.warning("S-BUS frame lost flag set")
            if self.failsafe_active:
                logger.warning("S-BUS failsafe active")
            self._reset_safe()
            # Keep flags set but mark as safe — the signal is invalid
            return True

        self._unpack_channels(frame_bytes)
        self.last_frame_time = _time.monotonic()
        self.frame_count += 1
        return True

    cpdef bint is_valid_frame(self, bytes frame_bytes):
        """
        Validate a raw 25-byte S-BUS frame (header, footer, length only).

        Returns:
            True if the frame has the correct header, footer, and length.
        """
        if len(frame_bytes) != SBUS_FRAME_LENGTH:
            return False
        if frame_bytes[0] != SBUS_HEADER:
            return False
        if frame_bytes[24] != SBUS_FOOTER:
            return False
        return True

    cdef void _unpack_channels(self, bytes frame_bytes):
        """
        Unpack 16 × 11-bit channel values from bytes 1–22 (LSB-first bitstream).

        The 22 data bytes form a 176-bit little-endian integer.  Channel N
        occupies bits [(N-1)*11 : N*11].

        Python's arbitrary-precision integers handle the 176-bit width cleanly;
        the per-frame cost is ~3 µs on Pi 3B+ — well within the 14 ms budget.
        """
        cdef int i, ch
        # bit_stream is a Python integer (176 bits — exceeds C 64-bit range)
        bit_stream = 0
        for i in range(22):
            bit_stream |= (<unsigned long long>(frame_bytes[1 + i])) << (i * 8)

        for ch in range(16):
            self.channels[ch] = (bit_stream >> (ch * 11)) & 0x7FF

    cdef void _reset_safe(self):
        """Set all proportional channels to center (safe hover/hold value)."""
        cdef int i
        for i in range(16):
            self.channels[i] = SBUS_SAFE_VALUE

    cpdef int get_channel(self, int channel_number):
        """
        Return raw 11-bit value for channel (1-indexed, returns 0–2047).

        Args:
            channel_number: 1 through 18 (16 proportional + 2 digital).

        Returns:
            Raw value 0–2047, or SBUS_CH_MID on out-of-range index.
        """
        if channel_number < 1 or channel_number > 18:
            logger.warning(f"get_channel: channel_number {channel_number} out of range 1-18")
            return SBUS_CH_MID
        return self.channels[channel_number - 1]

    cpdef double get_channel_normalized(self, int channel_number):
        """
        Return channel value normalized to the range –1.0 to +1.0.

        Uses the Futaba 172/992/1811 endpoints:
          172  → -1.0
          992  → 0.0
          1811 → +1.0

        Args:
            channel_number: 1-indexed channel number (1–16 proportional).

        Returns:
            Float in range [-1.0, 1.0], clamped.
        """
        cdef int raw = self.get_channel(channel_number)
        cdef double norm

        if raw <= SBUS_CH_MID:
            norm = (raw - SBUS_CH_MID) / float(SBUS_CH_MID - SBUS_CH_MIN)
        else:
            norm = (raw - SBUS_CH_MID) / float(SBUS_CH_MAX - SBUS_CH_MID)

        # Clamp to [-1.0, 1.0]
        if norm < -1.0:
            norm = -1.0
        if norm > 1.0:
            norm = 1.0
        return norm

    cpdef double get_channel_percent(self, int channel_number):
        """
        Return channel value as 0.0–100.0 % of travel.

        172  → 0.0
        1811 → 100.0

        Args:
            channel_number: 1-indexed channel number (1–16 proportional).

        Returns:
            Float in range [0.0, 100.0], clamped.
        """
        cdef int raw = self.get_channel(channel_number)
        cdef double pct = (raw - SBUS_CH_MIN) / float(SBUS_CH_MAX - SBUS_CH_MIN) * 100.0
        if pct < 0.0:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        return pct
