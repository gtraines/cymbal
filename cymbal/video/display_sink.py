"""
DisplaySink — optional VideoSink that shows frames via cv2.imshow().

This sink requires an X11/Wayland or equivalent desktop environment.
It is not suitable for headless Raspberry Pi OS Lite deployments.
The cv2 import is guarded so the class can still be imported on
machines where OpenCV is not installed — initialize() will return False
with a clear error message in that case.

Usage::

    from cymbal.video.display_sink import DisplaySink

    sink = DisplaySink(window_title="Cymbal OSD")
    if sink.initialize(640, 480):
        while running:
            sink.write_frame(annotated_frame)
    sink.close()
"""

import logging

from cymbal.video.sink import VideoSink

logger = logging.getLogger(__name__)

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None


class DisplaySink(VideoSink):
    """
    VideoSink that renders frames in an on-screen window via cv2.imshow().

    Args:
        window_title: Title shown in the OS window chrome.
        quit_key:     ASCII character that closes the window when pressed
                      (default ``'q'``).  Set to None to disable.
    """

    def __init__(self, window_title: str = "Cymbal OSD", quit_key: str = 'q'):
        self.window_title = window_title
        self.quit_key     = quit_key
        self._active      = False

    def initialize(self, width: int = 640, height: int = 480) -> bool:
        """
        Open the display window.

        Returns:
            True if cv2 is available and a window was created successfully.
        """
        if _cv2 is None:
            logger.error(
                "DisplaySink: OpenCV not available. "
                "Install opencv-python or switch to HeadlessSink."
            )
            return False

        try:
            _cv2.namedWindow(self.window_title, _cv2.WINDOW_NORMAL)
            _cv2.resizeWindow(self.window_title, width, height)
            self._active = True
            logger.info(f"DisplaySink: window '{self.window_title}' opened")
            return True
        except Exception as e:
            logger.error(f"DisplaySink: failed to open window: {e}")
            return False

    def write_frame(self, frame) -> None:
        """Display one frame.  Checks for quit key press each call."""
        if not self._active or _cv2 is None or frame is None:
            return
        try:
            _cv2.imshow(self.window_title, frame)
            key = _cv2.waitKey(1) & 0xFF
            if self.quit_key is not None and key == ord(self.quit_key):
                self._active = False
                logger.info("DisplaySink: quit key pressed")
        except Exception as e:
            logger.error(f"DisplaySink: write_frame error: {e}")

    def close(self) -> None:
        """Destroy the display window."""
        if _cv2 is not None:
            try:
                _cv2.destroyWindow(self.window_title)
            except Exception:
                pass
        self._active = False
        logger.debug(f"DisplaySink: window '{self.window_title}' closed")

    @property
    def is_active(self) -> bool:
        """True while the window is open and no quit key has been pressed."""
        return self._active
