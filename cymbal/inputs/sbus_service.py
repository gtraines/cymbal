"""
sbus_service.py — S-BUS Decoder Systemd Service Entry Point

Reads S-BUS frames from a GPIO pin using pigpio bit-bang serial, decodes them
with SBUSDecoder, and broadcasts the result over a Unix domain socket datagram
so the main cymbal process can consume it via SBUSReader.

Run as:
    python3 -m cymbal.inputs.sbus_service

Or via the sbus-decoder.service systemd unit.

Hardware wiring:
  GPIO 4  (Pin 7) <-- S-BUS signal (inverted UART from RC receiver)

Signal notes:
  - S-BUS is inverted UART: logic 0 = high voltage, logic 1 = low voltage.
  - pigpio bb_serial handles inversion via bb_serial_invert(gpio, 1).
  - No hardware inverter component is required when using this service.
  - Baud rate: 100,000 bps (non-standard, requires bit-bang serial).
  - Frame period: ~14 ms (Futaba) or ~7 ms (fast mode).
"""

import json
import logging
import os
import signal
import socket
import struct
import sys
import time

# ---------------------------------------------------------------------------
# Bootstrap logging before any imports that might log
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/var/log/cymbal.log', delay=True),
    ],
)
logger = logging.getLogger('cymbal.sbus_service')

# ---------------------------------------------------------------------------
# Attempt imports
# ---------------------------------------------------------------------------
try:
    import pigpio
except ImportError:
    pigpio = None
    logger.critical("pigpio not installed; cannot run S-BUS service without it")
    sys.exit(1)

try:
    from cymbal.inputs.sbus_decoder import SBUSDecoder
except ImportError as exc:
    logger.critical(f"Could not import SBUSDecoder: {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Shared payload format — must match sbus_reader.pyx
# ---------------------------------------------------------------------------
SBUS_MAGIC          = b'SBUS'
SBUS_PAYLOAD_STRUCT = struct.Struct('!4s16HBBBBd')

# ---------------------------------------------------------------------------
# S-BUS frame constants
# ---------------------------------------------------------------------------
SBUS_FRAME_LENGTH = 25
SBUS_HEADER       = 0x0F
SBUS_FOOTER       = 0x00
SBUS_BAUD         = 100000

# ---------------------------------------------------------------------------
# Read config (simple fall-through to defaults)
# ---------------------------------------------------------------------------
_CONFIG_PATH = '/etc/cymbal/config.json'


def _load_sbus_config():
    defaults = {'gpio_pin': 4, 'socket_path': '/run/cymbal/sbus.sock',
                'failsafe_action': 'center', 'frame_timeout_ms': 100}
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return {**defaults, **cfg.get('sbus', {})}
    except Exception:
        return defaults


# ---------------------------------------------------------------------------
# Frame assembly
# ---------------------------------------------------------------------------

class FrameAssembler:
    """
    Collects raw bytes from pigpio bit-bang reads and emits complete 25-byte
    S-BUS frames when header/footer are detected.
    """

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data: bytes):
        """Feed raw bytes; yields complete validated frames."""
        self._buf.extend(data)
        while True:
            # Find the next 0x0F header
            idx = self._buf.find(SBUS_HEADER)
            if idx < 0:
                self._buf.clear()
                return
            if idx > 0:
                # Discard garbage before header
                del self._buf[:idx]

            # Not enough bytes for a full frame yet
            if len(self._buf) < SBUS_FRAME_LENGTH:
                return

            candidate = bytes(self._buf[:SBUS_FRAME_LENGTH])

            if candidate[24] == SBUS_FOOTER:
                yield candidate
                del self._buf[:SBUS_FRAME_LENGTH]
            else:
                # Bad frame — skip one byte and try again
                del self._buf[0]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SBUSService:

    def __init__(self, gpio_pin: int, socket_path: str):
        self.gpio_pin = gpio_pin
        self.socket_path = socket_path
        self._running = False
        self._pi = None
        self._sock = None
        self._decoder = SBUSDecoder()
        self._assembler = FrameAssembler()

    def start(self):
        logger.info(f"Starting S-BUS service on GPIO {self.gpio_pin}")

        # Connect to pigpiod
        self._pi = pigpio.pi()
        if not self._pi.connected:
            logger.critical("Cannot connect to pigpiod; is it running?")
            sys.exit(1)

        # Configure bit-bang serial on the GPIO pin
        self._pi.set_mode(self.gpio_pin, pigpio.INPUT)
        err = self._pi.bb_serial_read_open(self.gpio_pin, SBUS_BAUD, 8)
        if err != 0:
            logger.critical(
                f"bb_serial_read_open failed on GPIO {self.gpio_pin}: err={err}"
            )
            self._cleanup()
            sys.exit(1)

        # Invert the signal (S-BUS is inverted UART)
        self._pi.bb_serial_invert(self.gpio_pin, 1)
        logger.info(f"Bit-bang serial opened: GPIO {self.gpio_pin} @ {SBUS_BAUD} baud (inverted)")

        # Set up Unix domain socket
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o660)
        logger.info(f"Unix socket bound at {self.socket_path}")

        self._running = True
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._run_loop()

    def _run_loop(self):
        logger.info("S-BUS service running")
        reader_path = self.socket_path + ".reader"
        while self._running:
            try:
                count, data = self._pi.bb_serial_read(self.gpio_pin)
                if count > 0:
                    for frame in self._assembler.feed(bytes(data)):
                        if self._decoder.decode_frame(frame):
                            self._broadcast(reader_path)
                else:
                    time.sleep(0.001)   # 1 ms idle sleep
            except Exception as e:
                logger.warning(f"Read loop error: {e}")
                time.sleep(0.01)

    def _broadcast(self, reader_path: str):
        """Pack the latest decoder state and send to the reader socket."""
        channels = self._decoder.channels
        payload = SBUS_PAYLOAD_STRUCT.pack(
            SBUS_MAGIC,
            channels[0],  channels[1],  channels[2],  channels[3],
            channels[4],  channels[5],  channels[6],  channels[7],
            channels[8],  channels[9],  channels[10], channels[11],
            channels[12], channels[13], channels[14], channels[15],
            channels[16],               # digital ch17
            channels[17],               # digital ch18
            1 if self._decoder.frame_lost      else 0,
            1 if self._decoder.failsafe_active else 0,
            self._decoder.last_frame_time,
        )
        try:
            self._sock.sendto(payload, reader_path)
        except FileNotFoundError:
            pass  # Reader not yet connected
        except Exception as e:
            logger.debug(f"Socket send error: {e}")

    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down S-BUS service")
        self._running = False
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        if self._pi and self._pi.connected:
            try:
                self._pi.bb_serial_read_close(self.gpio_pin)
            except Exception:
                pass
            self._pi.stop()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        logger.info("S-BUS service stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    cfg = _load_sbus_config()
    if not cfg.get('enabled', True):
        logger.info("S-BUS service is disabled in config; exiting")
        sys.exit(0)

    service = SBUSService(
        gpio_pin=cfg['gpio_pin'],
        socket_path=cfg['socket_path'],
    )
    service.start()


if __name__ == '__main__':
    main()
