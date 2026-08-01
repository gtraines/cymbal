"""
Cymbal entry-point module.

This module is the thin process-level shell for the Cymbal gimbal system.
It owns all process-global concerns:
  - Signal handler installation (SIGINT / SIGTERM)
  - logging.basicConfig() / log-file setup
  - Building concrete GimbalBase objects from SystemConfig.gimbals
  - Selecting and constructing the TelemetryProvider from config
  - Constructing and running CymbalController

Library users should import CymbalController directly from cymbal.controller
and inject their own gimbal objects — do NOT call this module programmatically.

Backward-compatibility:
    The name ``GimbalController`` is re-exported here so existing code that
    does ``from cymbal.main import GimbalController`` continues to work.
"""

import logging
import signal
import sys

# cimport declarations give Cython compile-time type information so that
# direct method calls on ctrl (initialize, run, shutdown, center_all) are
# dispatched at the C level rather than through the Python object protocol.
from cymbal.controller.cymbal_controller cimport CymbalController
from cymbal.gimbals.storm32_adapter cimport Storm32GimbalAdapter
from cymbal.gimbals.servo_adapter cimport ServoGimbalAdapter

# Runtime Python imports — required for construction and re-export.
# SimpleBGCGimbalAdapter remains a dynamic (try/except) import because the
# simplebgc_stub extension is optional and may not be compiled on all targets.
from cymbal.controller.cymbal_controller import CymbalController, GimbalController  # noqa: F401
from cymbal.controller.telemetry_provider import InProcessTelemetryProvider as _InProcessPy
from cymbal.config.config import SystemConfig
from cymbal.gimbals.storm32_adapter import Storm32GimbalAdapter as _Storm32Py
from cymbal.gimbals.servo_adapter import ServoGimbalAdapter as _ServoPy


def _build_gimbals_from_config(config: SystemConfig) -> list:
    """
    Instantiate GimbalBase objects from ``config.gimbals``.

    Falls back to the legacy camera_gimbal / spotlight_gimbal fields when
    the gimbals list is empty (old JSON files).
    """
    gimbals = []

    if config.gimbals:
        for gd in config.gimbals:
            if not gd.enabled:
                continue
            hw = gd.hardware
            axes = gd.get_axes_dict()

            if gd.backend_type == "storm32":
                gimbals.append(_Storm32Py(
                    gimbal_id=gd.id,
                    port=hw.get("serial_port", "/dev/ttyAMA0"),
                    baudrate=int(hw.get("baudrate", 115200)),
                    timeout=float(hw.get("timeout", 1.0)),
                    roles=list(gd.roles),
                    axes=axes,
                ))

            elif gd.backend_type == "servo_gpio":
                gimbals.append(_ServoPy(
                    gimbal_id=gd.id,
                    pitch_pin=int(hw.get("pitch_pin", 17)),
                    yaw_pin=int(hw.get("yaw_pin", 27)),
                    i2c_address=int(hw.get("i2c_address", 0x68)),
                    i2c_bus=int(hw.get("i2c_bus", 1)),
                    use_stabilization=bool(hw.get("use_stabilization", True)),
                    roles=list(gd.roles),
                    axes=axes,
                ))

            elif gd.backend_type == "simplebgc":
                try:
                    from cymbal.gimbals.simplebgc_stub import SimpleBGCGimbalAdapter
                    gimbals.append(SimpleBGCGimbalAdapter(
                        gimbal_id=gd.id,
                        port=hw.get("port", "/dev/ttyUSB0"),
                        baudrate=int(hw.get("baudrate", 115200)),
                        roles=list(gd.roles),
                        axes=axes,
                    ))
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"SimpleBGC gimbal '{gd.id}' not available: {e}"
                    )

            else:
                logging.getLogger(__name__).warning(
                    f"Unknown backend_type '{gd.backend_type}' for gimbal '{gd.id}'; skipping"
                )
    else:
        # Legacy fallback: use old camera_gimbal / spotlight_gimbal config sections
        cam  = config.camera_gimbal
        spot = config.spotlight_gimbal
        gimbals = [
            _Storm32Py(
                gimbal_id="camera_1",
                port=cam.serial_port,
                baudrate=cam.baudrate,
                timeout=cam.timeout,
            ),
            _ServoPy(
                gimbal_id="spotlight_1",
                pitch_pin=spot.pitch_pin,
                yaw_pin=spot.yaw_pin,
                i2c_address=spot.i2c_address,
                i2c_bus=spot.i2c_bus,
                use_stabilization=spot.use_stabilization,
            ),
        ]

    return gimbals


def _build_telemetry_provider(config, logger):
    """
    Construct the correct TelemetryProvider from config.

    telemetry.mode == "sidecar":
        Try to open a SocketTelemetryProvider.  If the socket cannot be bound
        (e.g. the sidecar is not yet running), fall back to InProcess and log
        a warning so the operator knows the control loop will block on GPS.

    telemetry.mode == "in_process" (default):
        Always use InProcessTelemetryProvider.

    The provider is NOT initialized here; CymbalController.initialize() calls
    provider.initialize() as part of its normal startup sequence.
    """
    mode = getattr(config.telemetry, 'mode', 'in_process')
    if mode == 'sidecar':
        try:
            from cymbal.controller.socket_telemetry_provider import (
                SocketTelemetryProvider as _SockPy,
            )
            provider = _SockPy(
                socket_path      = config.telemetry.socket_path,
                frame_timeout_ms = float(config.telemetry.frame_timeout_ms),
            )
            logger.info(
                f"TelemetryProvider: sidecar mode — socket={config.telemetry.socket_path}"
            )
            return provider
        except Exception as e:
            logger.warning(
                f"TelemetryProvider: sidecar requested but SocketTelemetryProvider "
                f"unavailable ({e}); falling back to in-process (GPS blocks control loop)"
            )

    # Default / fallback: in-process provider
    logger.info("TelemetryProvider: in-process mode (GPS serial in control loop)")
    return _InProcessPy(
        gps_config          = config.gps,
        geo_config          = config.geo,
        gps_update_rate_hz  = float(config.gps.update_rate_hz),
    )


def main():
    """
    Main entry point for the Cymbal control application.

    Process-level concerns handled here:
      - logging.basicConfig() with optional file handler
      - Signal handler registration (Ctrl+C / SIGTERM)
      - Config loading → provider selection → gimbal construction → controller startup
    """
    cdef CymbalController ctrl

    config = SystemConfig.load("/etc/cymbal/config.json")

    # --- Logging ---
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("/var/log/cymbal.log"),
        ],
    )
    logger = logging.getLogger(__name__)

    # --- Telemetry provider (selected from config) ---
    telemetry_provider = _build_telemetry_provider(config, logger)

    # --- Gimbals ---
    gimbals = _build_gimbals_from_config(config)

    # --- Controller (typed so lifecycle calls dispatch at the C level) ---
    ctrl = CymbalController(
        gimbals,
        config,
        logger=logger,
        telemetry_provider=telemetry_provider,
    )

    # --- Signal handlers (process-level only) ---
    def _on_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down…")
        ctrl.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    if not ctrl.initialize():
        logger.error("Failed to initialize Cymbal system")
        sys.exit(1)

    ctrl.center_all()
    logger.info("Cymbal system ready — press Ctrl+C to exit")

    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
