"""
Unit tests for SBUSDecoder.

All tests use synthetic 25-byte frames so no hardware or pigpio is required.
"""

import math
import struct
import time
import unittest

# ---------------------------------------------------------------------------
# Helpers to build synthetic S-BUS frames
# ---------------------------------------------------------------------------

SBUS_HEADER = 0x0F
SBUS_FOOTER = 0x00
SBUS_FRAME_LENGTH = 25

# Futaba endpoints
CH_MIN = 172
CH_MID = 992
CH_MAX = 1811


def _pack_channels(channels, flags=0):
    """
    Build a valid 25-byte S-BUS frame from a list of 16 channel values.

    channels: list of 16 ints (0-2047 each)
    flags:    byte 23 flags value (default 0)
    """
    assert len(channels) == 16, "Need exactly 16 channel values"

    # Pack 16 × 11-bit values into 176 bits (22 bytes), LSB-first
    bit_stream = 0
    for i, val in enumerate(channels):
        bit_stream |= (int(val) & 0x7FF) << (i * 11)

    data_bytes = bytearray(22)
    for i in range(22):
        data_bytes[i] = (bit_stream >> (i * 8)) & 0xFF

    frame = bytearray(25)
    frame[0] = SBUS_HEADER
    frame[1:23] = data_bytes
    frame[23] = flags
    frame[24] = SBUS_FOOTER
    return bytes(frame)


def _center_frame(flags=0):
    return _pack_channels([CH_MID] * 16, flags=flags)


def _min_frame():
    return _pack_channels([CH_MIN] * 16)


def _max_frame():
    return _pack_channels([CH_MAX] * 16)


# ---------------------------------------------------------------------------
# Tests: is_valid_frame
# ---------------------------------------------------------------------------

class TestSBUSDecoderValidation(unittest.TestCase):

    def _make_decoder(self):
        from cymbal.inputs.sbus_decoder import SBUSDecoder
        return SBUSDecoder()

    def test_valid_center_frame(self):
        d = self._make_decoder()
        self.assertTrue(d.is_valid_frame(_center_frame()))

    def test_rejects_wrong_length_short(self):
        d = self._make_decoder()
        self.assertFalse(d.is_valid_frame(_center_frame()[:24]))

    def test_rejects_wrong_length_long(self):
        d = self._make_decoder()
        self.assertFalse(d.is_valid_frame(_center_frame() + b'\x00'))

    def test_rejects_bad_header(self):
        d = self._make_decoder()
        frame = bytearray(_center_frame())
        frame[0] = 0xAA
        self.assertFalse(d.is_valid_frame(bytes(frame)))

    def test_rejects_bad_footer(self):
        d = self._make_decoder()
        frame = bytearray(_center_frame())
        frame[24] = 0xFF
        self.assertFalse(d.is_valid_frame(bytes(frame)))

    def test_rejects_empty(self):
        d = self._make_decoder()
        self.assertFalse(d.is_valid_frame(b''))


# ---------------------------------------------------------------------------
# Tests: decode_frame — channel unpacking
# ---------------------------------------------------------------------------

class TestSBUSDecoderChannels(unittest.TestCase):

    def _make_decoder(self):
        from cymbal.inputs.sbus_decoder import SBUSDecoder
        return SBUSDecoder()

    def test_center_channels_decode_correctly(self):
        d = self._make_decoder()
        self.assertTrue(d.decode_frame(_center_frame()))
        for ch in range(1, 17):
            self.assertEqual(d.get_channel(ch), CH_MID,
                             msg=f"Channel {ch} expected {CH_MID}, got {d.get_channel(ch)}")

    def test_min_channels_decode_correctly(self):
        d = self._make_decoder()
        self.assertTrue(d.decode_frame(_min_frame()))
        for ch in range(1, 17):
            self.assertEqual(d.get_channel(ch), CH_MIN,
                             msg=f"Channel {ch} expected {CH_MIN}")

    def test_max_channels_decode_correctly(self):
        d = self._make_decoder()
        self.assertTrue(d.decode_frame(_max_frame()))
        for ch in range(1, 17):
            self.assertEqual(d.get_channel(ch), CH_MAX,
                             msg=f"Channel {ch} expected {CH_MAX}")

    def test_individual_channels_independently(self):
        """Each channel should decode its own unique value without bleeding."""
        d = self._make_decoder()
        # Assign channel N a unique value: CH_MIN + N*50 (all < 2047)
        values = [CH_MIN + i * 50 for i in range(16)]
        frame = _pack_channels(values)
        d.decode_frame(frame)
        for i, expected in enumerate(values):
            ch = i + 1
            self.assertEqual(
                d.get_channel(ch), expected,
                msg=f"Channel {ch}: expected {expected}, got {d.get_channel(ch)}"
            )

    def test_channel_1_boundary_bits_do_not_bleed_to_channel_2(self):
        """Verify bit-boundary isolation between channels 1 and 2."""
        d = self._make_decoder()
        vals = [0] * 16
        vals[0] = 0x7FF  # channel 1 = max (all 11 bits set)
        vals[1] = 0x000  # channel 2 = 0
        frame = _pack_channels(vals)
        d.decode_frame(frame)
        self.assertEqual(d.get_channel(1), 0x7FF)
        self.assertEqual(d.get_channel(2), 0x000)

    def test_out_of_range_channel_returns_safe(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame())
        # Channel 0 (invalid)
        self.assertEqual(d.get_channel(0), CH_MID)
        # Channel 19 (invalid)
        self.assertEqual(d.get_channel(19), CH_MID)

    def test_decode_frame_increments_frame_count(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame())
        d.decode_frame(_center_frame())
        self.assertEqual(d.frame_count, 2)

    def test_invalid_frame_increments_error_count(self):
        d = self._make_decoder()
        d.decode_frame(b'\xFF' * 25)
        self.assertEqual(d.error_count, 1)

    def test_invalid_frame_returns_false(self):
        d = self._make_decoder()
        self.assertFalse(d.decode_frame(b'\xFF' * 25))

    def test_invalid_frame_sets_safe_channels(self):
        d = self._make_decoder()
        # First set to max
        d.decode_frame(_max_frame())
        self.assertEqual(d.get_channel(1), CH_MAX)
        # Now send a bad frame — channels should revert to center
        d.decode_frame(b'\xFF' * 25)
        self.assertEqual(d.get_channel(1), CH_MID)


# ---------------------------------------------------------------------------
# Tests: flags byte
# ---------------------------------------------------------------------------

class TestSBUSDecoderFlags(unittest.TestCase):

    def _make_decoder(self):
        from cymbal.inputs.sbus_decoder import SBUSDecoder
        return SBUSDecoder()

    def test_no_flags_set(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x00))
        self.assertFalse(d.frame_lost)
        self.assertFalse(d.failsafe_active)
        self.assertEqual(d.channels[16], 0)  # digital ch17
        self.assertEqual(d.channels[17], 0)  # digital ch18

    def test_digital_channel_17_set(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x01))
        self.assertEqual(d.channels[16], 1)
        self.assertEqual(d.channels[17], 0)

    def test_digital_channel_18_set(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x02))
        self.assertEqual(d.channels[16], 0)
        self.assertEqual(d.channels[17], 1)

    def test_frame_lost_flag(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x04))
        self.assertTrue(d.frame_lost)
        self.assertFalse(d.failsafe_active)

    def test_failsafe_flag(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x08))
        self.assertFalse(d.frame_lost)
        self.assertTrue(d.failsafe_active)

    def test_both_flags_set(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame(flags=0x0C))
        self.assertTrue(d.frame_lost)
        self.assertTrue(d.failsafe_active)

    def test_frame_lost_resets_proportional_channels_to_safe(self):
        """When frame_lost, proportional channels must go to center."""
        d = self._make_decoder()
        d.decode_frame(_max_frame())
        d.decode_frame(_center_frame(flags=0x04))  # frame lost
        for ch in range(1, 17):
            self.assertEqual(d.get_channel(ch), CH_MID)

    def test_failsafe_resets_proportional_channels_to_safe(self):
        d = self._make_decoder()
        d.decode_frame(_min_frame())
        d.decode_frame(_center_frame(flags=0x08))  # failsafe
        for ch in range(1, 17):
            self.assertEqual(d.get_channel(ch), CH_MID)


# ---------------------------------------------------------------------------
# Tests: normalization helpers
# ---------------------------------------------------------------------------

class TestSBUSDecoderNormalization(unittest.TestCase):

    def _make_decoder(self):
        from cymbal.inputs.sbus_decoder import SBUSDecoder
        return SBUSDecoder()

    def test_center_normalized_is_zero(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame())
        self.assertAlmostEqual(d.get_channel_normalized(1), 0.0, places=3)

    def test_min_normalized_is_minus_one(self):
        d = self._make_decoder()
        d.decode_frame(_min_frame())
        self.assertAlmostEqual(d.get_channel_normalized(1), -1.0, places=3)

    def test_max_normalized_is_plus_one(self):
        d = self._make_decoder()
        d.decode_frame(_max_frame())
        self.assertAlmostEqual(d.get_channel_normalized(1), 1.0, places=3)

    def test_center_percent_is_fifty(self):
        d = self._make_decoder()
        d.decode_frame(_center_frame())
        pct = d.get_channel_percent(1)
        # 992 in range [172, 1811]: (992-172)/(1811-172)*100 ≈ 50.03
        self.assertAlmostEqual(pct, 50.0, delta=1.0)

    def test_min_percent_is_zero(self):
        d = self._make_decoder()
        d.decode_frame(_min_frame())
        self.assertAlmostEqual(d.get_channel_percent(1), 0.0, places=3)

    def test_max_percent_is_hundred(self):
        d = self._make_decoder()
        d.decode_frame(_max_frame())
        self.assertAlmostEqual(d.get_channel_percent(1), 100.0, places=3)


if __name__ == '__main__':
    unittest.main()
