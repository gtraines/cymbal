"""
OSD render pipeline integration tests.

Tests that validate end-to-end OSD rendering:
  - render_frame() modifies a frame (non-zero pixels after render)
  - HeadlessSink.write_frame() is called with the annotated frame
  - frame_count increments correctly
  - render_frame() is a no-op when OSD is disabled
  - telemetry flows through the full pipeline to the frame
  - numpy array frames get a pixel written (when numpy available)

These tests use the pure-Python OSDOverlay from osd_test_helpers and a
capturing HeadlessSink to avoid any hardware or display dependency.
"""

import math
import unittest

from tests.video.osd_test_helpers import (
    OSDOverlay, make_osd, make_frame, fill_telemetry, fixed_time,
    _FakeHeadlessSink,
)


class TestOSDRenderPipeline(unittest.TestCase):

    # ------------------------------------------------------------------
    # Frame annotation
    # ------------------------------------------------------------------

    def test_render_frame_annotates_dict_frame(self):
        osd, sink = make_osd(time_fn=fixed_time("10:30:00 UTC"))
        fill_telemetry(osd)
        frame = {}
        osd.render_frame(frame)
        self.assertTrue(frame.get('annotated'))

    def test_render_frame_passes_lines_into_dict_frame(self):
        osd, sink = make_osd(time_fn=fixed_time("10:30:00 UTC"))
        fill_telemetry(osd, address="Test Address")
        frame = {}
        osd.render_frame(frame)
        self.assertIn('lines', frame)
        lines = frame['lines']
        self.assertTrue(any("Test Address" in l for l in lines))

    def test_render_frame_skips_none_frame(self):
        osd, sink = make_osd(time_fn=fixed_time())
        osd.render_frame(None)   # must not raise
        self.assertEqual(sink.frame_count, 0)

    # ------------------------------------------------------------------
    # Video sink integration
    # ------------------------------------------------------------------

    def test_sink_write_frame_called_after_render(self):
        sink = _FakeHeadlessSink(capture=True)
        sink.initialize()
        osd = OSDOverlay(time_fn=fixed_time())
        osd.initialize(video_sink=sink)
        fill_telemetry(osd)
        frame = {}
        osd.render_frame(frame)
        self.assertEqual(sink.frame_count, 1)
        self.assertIs(sink.last_frame, frame)

    def test_sink_write_frame_called_multiple_times(self):
        sink = _FakeHeadlessSink(capture=True)
        sink.initialize()
        osd = OSDOverlay(time_fn=fixed_time())
        osd.initialize(video_sink=sink)
        fill_telemetry(osd)
        for _ in range(5):
            osd.render_frame({})
        self.assertEqual(sink.frame_count, 5)

    def test_no_sink_does_not_raise(self):
        osd = OSDOverlay(time_fn=fixed_time())
        osd._video_sink = None
        fill_telemetry(osd)
        osd.render_frame({})   # must not raise

    # ------------------------------------------------------------------
    # Disabled OSD
    # ------------------------------------------------------------------

    def test_disabled_osd_skips_render(self):
        osd, sink = make_osd(time_fn=fixed_time())
        osd.enabled = False
        fill_telemetry(osd)
        frame = {}
        osd.render_frame(frame)
        self.assertFalse(frame.get('annotated'))
        self.assertEqual(sink.frame_count, 0)

    # ------------------------------------------------------------------
    # Telemetry → frame content
    # ------------------------------------------------------------------

    def test_telemetry_address_appears_in_rendered_lines(self):
        osd, sink = make_osd(time_fn=fixed_time())
        fill_telemetry(osd, address="321 W Broadway, Tempe, AZ 85282")
        frame = {}
        osd.render_frame(frame)
        self.assertTrue(
            any("321 W Broadway" in l for l in frame.get('lines', [])),
            f"lines={frame.get('lines')}"
        )

    def test_telemetry_gps_appears_in_rendered_lines(self):
        osd, sink = make_osd(time_fn=fixed_time())
        fill_telemetry(osd, lat=33.41520, lon=-111.83150)
        frame = {}
        osd.render_frame(frame)
        lines = frame.get('lines', [])
        self.assertTrue(
            any("33.41520" in l for l in lines),
            f"Expected lat in lines: {lines}"
        )

    def test_telemetry_no_fix_appears_in_rendered_lines(self):
        osd, sink = make_osd(time_fn=fixed_time())
        fill_telemetry(osd, lat=float('nan'), lon=float('nan'))
        frame = {}
        osd.render_frame(frame)
        lines = frame.get('lines', [])
        self.assertTrue(
            any("No fix" in l for l in lines),
            f"Expected 'No fix' in lines: {lines}"
        )

    def test_injected_timestamp_in_rendered_frame(self):
        osd, sink = make_osd(time_fn=fixed_time("09:15:30 UTC"))
        fill_telemetry(osd)
        frame = {}
        osd.render_frame(frame)
        lines = frame.get('lines', [])
        self.assertEqual(lines[0], "09:15:30 UTC")

    # ------------------------------------------------------------------
    # numpy frame path (when numpy is available)
    # ------------------------------------------------------------------

    def test_numpy_frame_modified_by_render(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available")

        osd, sink = make_osd(time_fn=fixed_time())
        fill_telemetry(osd)
        frame = np.zeros((480, 640, 3), dtype='uint8')
        osd.render_frame(frame)
        # The test stub writes a white dot at [5,5]
        self.assertFalse(
            (frame == 0).all(),
            "Frame should be non-zero after render_frame()"
        )

    def test_sink_receives_numpy_frame(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available")

        sink = _FakeHeadlessSink(capture=True)
        sink.initialize()
        osd = OSDOverlay(time_fn=fixed_time())
        osd.initialize(video_sink=sink)
        fill_telemetry(osd)
        frame = np.zeros((480, 640, 3), dtype='uint8')
        osd.render_frame(frame)
        self.assertEqual(sink.frame_count, 1)
        self.assertIsNotNone(sink.last_frame)

    # ------------------------------------------------------------------
    # close() lifecycle
    # ------------------------------------------------------------------

    def test_close_resets_video_sink(self):
        osd, sink = make_osd(time_fn=fixed_time())
        osd.close()
        self.assertIsNone(osd._video_sink)

    def test_render_after_close_does_not_raise(self):
        osd, sink = make_osd(time_fn=fixed_time())
        osd.close()
        fill_telemetry(osd)
        osd.render_frame({})   # _video_sink is None → must not raise

    # ------------------------------------------------------------------
    # Default HeadlessSink attached on initialize()
    # ------------------------------------------------------------------

    def test_default_sink_attached_on_initialize(self):
        osd = OSDOverlay(time_fn=fixed_time())
        osd.initialize()   # no explicit sink
        self.assertIsNotNone(osd._video_sink)

    def test_explicit_sink_overrides_default(self):
        custom_sink = _FakeHeadlessSink(capture=True)
        custom_sink.initialize()
        osd = OSDOverlay(time_fn=fixed_time())
        osd.initialize(video_sink=custom_sink)
        self.assertIs(osd._video_sink, custom_sink)


if __name__ == '__main__':
    unittest.main()
