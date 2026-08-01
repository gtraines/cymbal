#!/usr/bin/env python3
"""
Example: Storm32GimbalAdapter — camera gimbal via Storm32bgc serial controller.

Demonstrates the new library API for a 3-axis brushless camera gimbal backed
by a Storm32bgc controller connected over UART.

Hardware:
  - Storm32bgc controller wired to RPi GPIO 14/15 (/dev/ttyAMA0)
  - Connection: 115200 baud, 8N1

New vs old API:
  Old: from cymbal.camera_gimbal import Storm32Controller
  New: from cymbal.gimbals import Storm32GimbalAdapter

The adapter wraps Storm32Controller behind the standard GimbalBase interface
so it can be used standalone or injected into CymbalController.
"""

import logging
import sys
import time

# ── New library API ──────────────────────────────────────────────────────────
from cymbal.gimbals import Storm32GimbalAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    # ── 1. Construct the gimbal adapter ─────────────────────────────────────
    #
    # Custom axis limits can be supplied — here we restrict the yaw range to
    # ±90° to match a physical mounting constraint.
    camera = Storm32GimbalAdapter(
        gimbal_id="camera_1",
        port="/dev/ttyAMA0",
        baudrate=115200,
        timeout=1.0,
        roles=["camera"],
        axes={
            "pitch": [-90.0, 30.0],   # looking down 90° to slightly up
            "roll":  [-30.0, 30.0],
            "yaw":   [-90.0, 90.0],
        },
    )

    logger.info("Adapter created: %r", camera)
    logger.info("Roles : %s", camera.roles)
    logger.info("Axes  : %s", camera.axes)

    # ── 2. Initialize (connect over serial) ──────────────────────────────────
    if not camera.initialize():
        logger.error("Failed to connect to Storm32bgc.  Check wiring and baud rate.")
        return 1

    logger.info("Storm32 connected successfully")

    try:
        # ── 3. Center ────────────────────────────────────────────────────────
        logger.info("Centering gimbal…")
        camera.center()
        time.sleep(2)

        # ── 4. Axis commands via set_axes() ──────────────────────────────────
        #
        # set_axes() accepts any subset of axis names.
        # Unknown axis names are silently ignored (with a debug log).
        # Missing axes default to 0.0.
        movements = [
            ({"pitch": -30.0, "roll":  0.0, "yaw":   0.0}, "Looking down 30°"),
            ({"pitch":   0.0, "roll":  0.0, "yaw":  45.0}, "Panning right 45°"),
            ({"pitch": -20.0, "roll":  5.0, "yaw": -45.0}, "Down-left with roll"),
            ({"pitch":   0.0, "roll":  0.0, "yaw":   0.0}, "Return to centre"),
        ]

        for axes, description in movements:
            logger.info("%-40s  axes=%s", description, axes)
            camera.set_axes(axes)
            time.sleep(3)

        # ── 5. Status ────────────────────────────────────────────────────────
        status = camera.get_status()
        logger.info("Status: %s", status)

    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        # ── 6. Shutdown ──────────────────────────────────────────────────────
        camera.shutdown()
        logger.info("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
