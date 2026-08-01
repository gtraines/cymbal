"""
cymbal-video service — OSD and video output process.

Consumes TelemetrySnapshot datagrams from the cymbal-telemetry sidecar (or
falls back to an InProcessTelemetryProvider), annotates video frames with
flight telemetry via OSDOverlay, and routes annotated frames to the
configured VideoSink (headless, display, or composite/file).

Run as:
    python3 -m cymbal.video.video_service

Or via the cymbal-video.service systemd unit.

Architecture notes:
  - This process owns all OpenCV work, so cv2 blocking (frame copy,
    drawing primitives) never touches the control loop.
  - Telemetry is consumed as latest-snapshot datagrams; stale data renders
    as "No fix" but the video loop keeps running.
  - Camera capture is optional: when camera_source == -1 or when cv2
    VideoCapture fails, a synthetic black frame is used so the OSD still
    renders telemetry overlays for testing or display-only deployments.

Decision on native pipeline (ADR-001):
    See docs/ADR-001-native-video-pipeline.md for the evaluation of
    GStreamer/FFmpeg vs Python/OpenCV for this sidecar.
"""

import json
import logging
import math
import os
import signal
import sys
import time

# ---------------------------------------------------------------------------
# Bootstrap logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/var/log/cymbal.log', delay=True),
    ],
)
logger = logging.getLogger('cymbal.video_service')

# ---------------------------------------------------------------------------
# Guarded imports
# ---------------------------------------------------------------------------
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np  = None
    logger.warning("OpenCV (cv2) not available; video capture disabled")

try:
    from cymbal.osd.overlay_controller import OSDOverlay
except ImportError as exc:
    logger.critical(f"Could not import OSDOverlay: {exc}")
    sys.exit(1)

try:
    from cymbal.controller.socket_telemetry_provider import SocketTelemetryProvider
    from cymbal.controller.telemetry_provider import InProcessTelemetryProvider
    from cymbal.controller.ipc_schemas import SOCKET_TELEMETRY_PATH
except ImportError as exc:
    logger.critical(f"Could not import telemetry providers: {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
_CONFIG_PATH = '/etc/cymbal/config.json'


def _load_config() -> dict:
    defaults = {
        'video': {
            'mode':          'headless',
            'camera_source': 0,
            'width':         640,
            'height':        480,
            'fps':           30.0,
            'window_title':  'Cymbal OSD',
            'output_path':   '',
        },
        'osd': {
            'enabled':          True,
            'font_scale':       0.6,
            'font_thickness':   1,
            'text_color':       [255, 255, 255],
            'background_color': [0, 0, 0],
            'background_alpha': 0.5,
            'show_sbus_channels': False,
            'show_compass':     True,
            'compass_radius':   45,
        },
        'telemetry': {
            'mode':             'sidecar',
            'socket_path':      SOCKET_TELEMETRY_PATH,
            'frame_timeout_ms': 500,
        },
        'gps': {
            'port': '/dev/ttyUSB0', 'baudrate': 9600, 'update_rate_hz': 5,
            'terrain_db_path': '/opt/cymbal/srtm', 'use_terrain_db': True,
            'min_fix_quality': 1,
        },
        'geo': {
            'address_db_path': '/opt/cymbal/addresses.db',
            'search_radius_deg': 0.01, 'enabled': True,
        },
    }
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        for section in ('video', 'osd', 'telemetry', 'gps', 'geo'):
            defaults[section].update(cfg.get(section, {}))
    except FileNotFoundError:
        logger.warning(f"Config file {_CONFIG_PATH} not found; using defaults")
    except Exception as e:
        logger.warning(f"Config load error: {e}; using defaults")
    return defaults


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VideoService:
    """
    Standalone video/OSD process.

    Consumes telemetry via SocketTelemetryProvider (or InProcessTelemetryProvider
    as fallback), captures camera frames, renders OSD, and routes output to the
    configured sink.
    """

    def __init__(self, cfg: dict):
        self._cfg       = cfg
        self._running   = False
        self._cap       = None   # cv2.VideoCapture or None
        self._osd       = None
        self._provider  = None
        self._sink      = None

        vcfg = cfg['video']
        self._width          = int(vcfg.get('width',  640))
        self._height         = int(vcfg.get('height', 480))
        self._fps            = float(vcfg.get('fps', 30.0))
        self._frame_interval = 1.0 / max(self._fps, 1.0)
        self._camera_source  = vcfg.get('camera_source', 0)
        self._video_mode     = vcfg.get('mode', 'headless')

    def start(self):
        logger.info("cymbal-video: starting")
        self._init_telemetry()
        self._init_osd()
        self._init_camera()
        self._running = True
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        self._run_loop()

    def _init_telemetry(self):
        """Connect to the telemetry sidecar, or fall back to in-process."""
        tcfg   = self._cfg['telemetry']
        mode   = tcfg.get('mode', 'sidecar')
        spath  = tcfg.get('socket_path', SOCKET_TELEMETRY_PATH)
        timeout = float(tcfg.get('frame_timeout_ms', 500))

        if mode == 'sidecar':
            try:
                p = SocketTelemetryProvider(socket_path=spath, frame_timeout_ms=timeout)
                if p.initialize():
                    self._provider = p
                    logger.info(f"cymbal-video: using SocketTelemetryProvider ({spath})")
                    return
            except Exception as e:
                logger.warning(f"cymbal-video: SocketTelemetryProvider failed ({e}); "
                               "falling back to InProcess")

        # Fallback: in-process GPS/terrain/address
        class _DictCfg:
            def __init__(self, d): [setattr(self, k, v) for k, v in d.items()]
        p = InProcessTelemetryProvider(
            gps_config=_DictCfg(self._cfg['gps']),
            geo_config=_DictCfg(self._cfg['geo']),
            gps_update_rate_hz=float(self._cfg['gps'].get('update_rate_hz', 5)),
        )
        p.initialize()
        self._provider = p
        logger.info("cymbal-video: using InProcessTelemetryProvider")

    def _init_osd(self):
        """Create OSDOverlay with the appropriate video sink."""
        try:
            from cymbal.utils.config import OSDConfig

            class _OSDCfg:
                def __init__(self, d):
                    for k, v in d.items(): setattr(self, k, v)
                    # ensure list fields are lists
                    if isinstance(getattr(self, 'text_color', None), list):
                        pass
                    if isinstance(getattr(self, 'background_color', None), list):
                        pass

            osd_cfg = _OSDCfg(self._cfg['osd'])
            self._osd = OSDOverlay(config=osd_cfg)

            sink = self._build_sink()
            ok   = self._osd.initialize(video_sink=sink)
            if not ok:
                logger.warning("cymbal-video: OSDOverlay.initialize() returned False "
                               "(OpenCV missing?)")
        except Exception as e:
            logger.error(f"cymbal-video: OSD init failed: {e}")
            self._osd = None

    def _build_sink(self):
        """Return a VideoSink appropriate for the configured output mode."""
        mode = self._video_mode
        try:
            if mode == 'display':
                from cymbal.video.display_sink import DisplaySink
                sink = DisplaySink(window_title=self._cfg['video'].get('window_title', 'Cymbal OSD'))
                sink.initialize(self._width, self._height)
                return sink
            elif mode == 'composite':
                output_path = self._cfg['video'].get('output_path', '')
                if output_path and cv2 is not None and np is not None:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    writer = cv2.VideoWriter(
                        output_path, fourcc, self._fps,
                        (self._width, self._height)
                    )
                    return _VideoWriterSink(writer)
        except Exception as e:
            logger.warning(f"cymbal-video: could not create {mode} sink: {e}; using headless")

        # Default: headless
        from cymbal.video.headless_sink import HeadlessSink
        sink = HeadlessSink()
        sink.initialize(self._width, self._height)
        return sink

    def _init_camera(self):
        """Open the camera capture device.  Failure is non-fatal."""
        if cv2 is None:
            logger.info("cymbal-video: cv2 not available; using blank frames")
            return
        src = self._camera_source
        if src == -1:
            logger.info("cymbal-video: camera_source=-1; using blank frames")
            return
        try:
            cap = cv2.VideoCapture(src)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
                self._cap = cap
                logger.info(f"cymbal-video: camera opened (source={src})")
            else:
                logger.warning(f"cymbal-video: could not open camera source={src}; "
                               "using blank frames")
        except Exception as e:
            logger.warning(f"cymbal-video: camera init error: {e}; using blank frames")

    def _run_loop(self):
        logger.info("cymbal-video: render loop running")
        while self._running:
            t_start = time.monotonic()

            # 1. Refresh telemetry
            if self._provider is not None:
                self._provider.update()

            # 2. Acquire frame
            frame = self._capture_frame()

            # 3. Push telemetry into OSD and render
            if self._osd is not None and frame is not None:
                tp = self._provider
                self._osd.update_telemetry(
                    lat            = tp.latitude        if tp is not None and not math.isnan(tp.latitude) else float('nan'),
                    lon            = tp.longitude       if tp is not None and not math.isnan(tp.longitude) else float('nan'),
                    alt_agl        = tp.altitude_agl    if tp is not None else float('nan'),
                    groundspeed    = tp.groundspeed_ms  if tp is not None else float('nan'),
                    address        = tp.address         if tp is not None else "No fix",
                    fix_quality    = tp.fix_quality     if tp is not None else 0,
                    satellites     = tp.satellites      if tp is not None else 0,
                    sbus_channels  = [],        # SBUS not available in video sidecar
                    track_degrees  = tp.track_degrees   if tp is not None else float('nan'),
                    camera_yaw_deg = float('nan'),  # camera yaw not yet published via IPC
                )
                self._osd.render_frame(frame)

            # 4. Rate-limit
            elapsed   = time.monotonic() - t_start
            remaining = self._frame_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _capture_frame(self):
        """Return a BGR numpy frame, or a blank frame if the camera is unavailable."""
        if self._cap is not None and cv2 is not None:
            ret, frame = self._cap.read()
            if ret:
                return frame
        if np is not None:
            return np.zeros((self._height, self._width, 3), dtype=np.uint8)
        return None

    def _handle_signal(self, signum, frame):
        logger.info(f"cymbal-video: received signal {signum}, shutting down")
        self._running = False
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        if self._cap is not None:
            try: self._cap.release()
            except Exception: pass
        if self._osd is not None:
            try: self._osd.close()
            except Exception: pass
        if self._provider is not None:
            try: self._provider.close()
            except Exception: pass
        logger.info("cymbal-video: stopped")


# ---------------------------------------------------------------------------
# VideoWriter sink adapter
# ---------------------------------------------------------------------------

class _VideoWriterSink:
    """Thin adapter wrapping cv2.VideoWriter as a VideoSink."""

    def __init__(self, writer):
        self._writer = writer

    def initialize(self, width=640, height=480):
        return self._writer.isOpened()

    def write_frame(self, frame):
        if frame is not None and self._writer.isOpened():
            self._writer.write(frame)

    def close(self):
        try: self._writer.release()
        except Exception: pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    cfg = _load_config()
    service = VideoService(cfg)
    service.start()


if __name__ == '__main__':
    main()
