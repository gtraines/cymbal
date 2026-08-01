"""
cymbal-telemetry service — Telemetry publisher process.

Reads GPS position, terrain elevation, and reverse-geocoded address using
InProcessTelemetryProvider, and publishes TelemetrySnapshot datagrams over a
Unix domain datagram socket so the main cymbal control process (and any other
consumers) can read them without blocking on serial I/O or SQLite.

Run as:
    python3 -m cymbal.telemetry.telemetry_service

Or via the cymbal-telemetry.service systemd unit.

IPC socket:
    Publisher binds to:  /run/cymbal/telemetry.sock
    Reader binds to:     /run/cymbal/telemetry.sock.reader
    Publisher sends to:  /run/cymbal/telemetry.sock.reader

Configuration (from /etc/cymbal/config.json):
    gps.update_rate_hz      — how often GPS is polled (default 5 Hz)
    telemetry.socket_path   — socket path (default /run/cymbal/telemetry.sock)
    telemetry.frame_timeout_ms — (informational; used by readers, not here)
"""

import json
import logging
import os
import signal
import socket
import sys
import time

# ---------------------------------------------------------------------------
# Bootstrap logging before any heavy imports
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/var/log/cymbal.log', delay=True),
    ],
)
logger = logging.getLogger('cymbal.telemetry_service')

# ---------------------------------------------------------------------------
# Imports (guarded so the module can be imported on non-Linux machines)
# ---------------------------------------------------------------------------
try:
    from cymbal.controller.telemetry_provider import InProcessTelemetryProvider
except ImportError as exc:
    logger.critical(f"Could not import InProcessTelemetryProvider: {exc}")
    sys.exit(1)

try:
    from cymbal.controller.ipc_schemas import TelemetrySnapshotSchema, SOCKET_TELEMETRY_PATH
except ImportError as exc:
    logger.critical(f"Could not import IPC schemas: {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
_CONFIG_PATH = '/etc/cymbal/config.json'


def _load_config():
    defaults = {
        'gps': {
            'port': '/dev/ttyUSB0',
            'baudrate': 9600,
            'update_rate_hz': 5,
            'terrain_db_path': '/opt/cymbal/srtm',
            'use_terrain_db': True,
            'min_fix_quality': 1,
        },
        'geo': {
            'address_db_path': '/opt/cymbal/addresses.db',
            'search_radius_deg': 0.01,
            'enabled': True,
        },
        'telemetry': {
            'socket_path': SOCKET_TELEMETRY_PATH,
            'frame_timeout_ms': 500,
        },
    }
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        # Deep-merge: section defaults overridden by actual config
        for section in ('gps', 'geo', 'telemetry'):
            defaults[section].update(cfg.get(section, {}))
    except FileNotFoundError:
        logger.warning(f"Config file {_CONFIG_PATH} not found; using defaults")
    except Exception as e:
        logger.warning(f"Config load error: {e}; using defaults")
    return defaults


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TelemetryService:
    """
    Reads GPS/terrain/address data and publishes TelemetrySnapshot datagrams.

    Runs a tight loop at the configured GPS rate; on each cycle:
      1. Calls provider.update() (may block on serial read or SQLite)
      2. Packs a TelemetrySnapshot struct
      3. Sends it to the reader socket path (non-blocking datagram)
    """

    def __init__(self, gps_cfg: dict, geo_cfg: dict, socket_path: str):
        self._socket_path = socket_path
        self._running     = False
        self._sock        = None

        # Build lightweight config objects from dicts
        self._gps_cfg = _DictConfig(gps_cfg)
        self._geo_cfg = _DictConfig(geo_cfg)
        self._update_interval = 1.0 / max(gps_cfg.get('update_rate_hz', 5), 1)

        self._provider = InProcessTelemetryProvider(
            gps_config=self._gps_cfg,
            geo_config=self._geo_cfg,
            gps_update_rate_hz=float(gps_cfg.get('update_rate_hz', 5)),
        )

    def start(self):
        logger.info(f"cymbal-telemetry: starting (socket={self._socket_path})")

        if not self._provider.initialize():
            logger.warning("cymbal-telemetry: TelemetryProvider.initialize() returned False; "
                           "continuing (GPS may be unavailable)")

        # Create socket directory and bind
        socket_dir = os.path.dirname(self._socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o660)
        logger.info(f"cymbal-telemetry: socket bound at {self._socket_path}")

        self._running = True
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._run_loop()

    def _run_loop(self):
        reader_path = self._socket_path + ".reader"
        logger.info("cymbal-telemetry: publish loop running")
        while self._running:
            t_start = time.monotonic()
            try:
                self._provider.update()
                self._broadcast(reader_path)
            except Exception as e:
                logger.warning(f"cymbal-telemetry: loop error: {e}")
            # Rate-limit: sleep remaining time in the update interval
            elapsed   = time.monotonic() - t_start
            remaining = self._update_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _broadcast(self, reader_path: str):
        """Pack the latest provider state and send to the reader socket."""
        p = self._provider
        import math
        payload = TelemetrySnapshotSchema.pack(
            lat            = p.latitude         if p.has_fix and not math.isnan(p.latitude)       else float('nan'),
            lon            = p.longitude        if p.has_fix and not math.isnan(p.longitude)      else float('nan'),
            alt_msl        = p.altitude_msl,
            alt_agl        = p.altitude_agl,
            groundspeed_ms = p.groundspeed_ms,
            track_degrees  = p.track_degrees,
            fix_quality    = p.fix_quality,
            satellites     = p.satellites,
            address        = p.address or "No fix",
            timestamp      = time.monotonic(),
        )
        try:
            self._sock.sendto(payload, reader_path)
        except FileNotFoundError:
            pass  # Reader not yet connected — normal at startup
        except Exception as e:
            logger.debug(f"cymbal-telemetry: send error: {e}")

    def _handle_signal(self, signum, frame):
        logger.info(f"cymbal-telemetry: received signal {signum}, shutting down")
        self._running = False
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        try:
            self._provider.close()
        except Exception:
            pass
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            if os.path.exists(self._socket_path):
                try:
                    os.unlink(self._socket_path)
                except Exception:
                    pass
        logger.info("cymbal-telemetry: stopped")


# ---------------------------------------------------------------------------
# Lightweight dict-to-attribute config shim
# ---------------------------------------------------------------------------

class _DictConfig:
    """
    Exposes a plain dict as attribute access so InProcessTelemetryProvider
    can read gps_config.port, geo_config.enabled, etc. without needing
    a full SystemConfig instance.
    """

    def __init__(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        raise AttributeError(f"_DictConfig has no attribute '{name}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    cfg = _load_config()
    service = TelemetryService(
        gps_cfg     = cfg['gps'],
        geo_cfg     = cfg['geo'],
        socket_path = cfg['telemetry']['socket_path'],
    )
    service.start()


if __name__ == '__main__':
    main()
