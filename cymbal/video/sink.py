"""
VideoSink — base protocol for all video output backends.

A VideoSink receives annotated frames from the OSD pipeline and
decides what to do with them: display on-screen, write to a file,
discard (headless), etc.

Usage::

    from cymbal.video.sink import VideoSink

    class MyCustomSink(VideoSink):
        def initialize(self, width: int, height: int) -> bool:
            ...
        def write_frame(self, frame) -> None:
            ...
        def close(self) -> None:
            ...
"""


class VideoSink:
    """
    Abstract base class for video output sinks.

    Subclasses must implement initialize(), write_frame(), and close().
    The base implementations are safe no-ops so partial overrides are
    possible during development.
    """

    def initialize(self, width: int = 640, height: int = 480) -> bool:
        """
        Prepare the sink for receiving frames.

        Args:
            width:  Frame width in pixels.
            height: Frame height in pixels.

        Returns:
            True if the sink is ready to receive frames.
        """
        return True

    def write_frame(self, frame) -> None:
        """
        Deliver one video frame to the sink.

        Args:
            frame: A numpy ndarray (H × W × 3, uint8, BGR), or None to skip.
        """

    def close(self) -> None:
        """Release any resources held by this sink."""

    # Context manager support
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
