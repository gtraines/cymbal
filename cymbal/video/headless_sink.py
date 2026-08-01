"""
HeadlessSink — no-op VideoSink for headless deployments and testing.

Frames delivered to this sink are discarded immediately.  It is the
default sink used by OSDOverlay when no explicit sink is configured,
making it safe to run on hardware without a display (e.g. Raspberry Pi
OS Lite, CI environments).

Optional frame capture for testing::

    sink = HeadlessSink(capture=True)
    sink.initialize(640, 480)
    sink.write_frame(frame)
    assert sink.last_frame is not None
    assert sink.frame_count == 1
"""

import logging

from cymbal.video.sink import VideoSink

logger = logging.getLogger(__name__)


class HeadlessSink(VideoSink):
    """
    No-op VideoSink that silently discards all frames.

    When ``capture=True`` the most recent frame is stored in
    ``self.last_frame`` and a running count is kept in
    ``self.frame_count``.  This is only intended for test use
    (storing frames in memory is not suitable for production).

    Args:
        capture: If True, retain the last frame and increment frame_count.
    """

    def __init__(self, capture: bool = False):
        self.capture     = capture
        self.last_frame  = None
        self.frame_count = 0
        self._width      = 0
        self._height     = 0
        self._initialized = False

    def initialize(self, width: int = 640, height: int = 480) -> bool:
        self._width  = width
        self._height = height
        self._initialized = True
        logger.debug(f"HeadlessSink initialized ({width}×{height})")
        return True

    def write_frame(self, frame) -> None:
        if frame is None:
            return
        if self.capture:
            self.last_frame = frame
            self.frame_count += 1

    def close(self) -> None:
        self._initialized = False
        logger.debug("HeadlessSink closed")
