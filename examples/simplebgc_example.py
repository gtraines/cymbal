#!/usr/bin/env python3
"""
Example: SimpleBGCGimbalAdapter — AlexMos / BaseCam SimpleBGC controller (stub).

SimpleBGC (also known as BGC 32-bit) is a popular brushless gimbal controller
used in cinema and inspection rigs.  The Cymbal adapter is currently a *stub*
that raises NotImplementedError on every operation.

This example shows:
  1. How to construct a SimpleBGCGimbalAdapter (safe — no hardware access).
  2. The expected API contract so a future implementor knows exactly what to fill in.
  3. How to register it in a SystemConfig ``gimbals`` list.
  4. What happens at runtime until the implementation is written.

When to use this example:
  - You have a SimpleBGC controller and want to add support.
  - You are designing a multi-gimbal system and need to reserve a slot for a BGC.

To implement full support:
  - Replace the stub methods in cymbal/gimbals/simplebgc_stub.pyx with real
    SimpleBGC Serial API v2 calls (see docs/API.md for the framing protocol).
  - The serial library ``sbgc-api`` (pip install sbgc-api) is a good starting
    point, or implement the binary frame encoding manually.
"""

import logging
import sys

# ── New library API ──────────────────────────────────────────────────────────
from cymbal.gimbals import SimpleBGCGimbalAdapter
from cymbal.utils.config import (
    SystemConfig, GimbalDef, AxisConfig, VideoOutputConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


def demo_direct_construction() -> None:
    """Show how to build a SimpleBGCGimbalAdapter directly."""
    logger.info("=== Direct construction ===")

    bgc = SimpleBGCGimbalAdapter(
        gimbal_id="bgc_camera",
        port="/dev/ttyUSB0",
        baudrate=115200,
        roles=["camera"],
        axes={
            "pitch": [-90.0, 45.0],
            "roll":  [-45.0, 45.0],
            "yaw":   [-180.0, 180.0],
        },
    )

    logger.info("Adapter created: %r", bgc)
    logger.info("Roles : %s", bgc.roles)
    logger.info("Axes  : %s", bgc.axes)

    # get_status() is safe — it returns an error dict without connecting
    logger.info("Status (pre-init): %s", bgc.get_status())

    # All other methods raise NotImplementedError until implemented
    logger.info("Attempting initialize()…")
    try:
        bgc.initialize()
    except NotImplementedError as e:
        logger.warning("Expected stub error: %s", e)

    logger.info("Attempting set_axes({'pitch': -30})…")
    try:
        bgc.set_axes({"pitch": -30.0})
    except NotImplementedError as e:
        logger.warning("Expected stub error: %s", e)


def demo_config_based_construction() -> None:
    """Show how to declare a SimpleBGC gimbal in a SystemConfig gimbals list."""
    logger.info("=== Config-based construction ===")

    config_dict = {
        "gimbals": [
            {
                "id":           "bgc_camera",
                "backend_type": "simplebgc",
                "roles":        ["camera"],
                "axes": [
                    {"name": "pitch", "min_deg": -90.0, "max_deg": 45.0,
                     "sbus_channel": 6},
                    {"name": "roll",  "min_deg": -45.0, "max_deg": 45.0},
                    {"name": "yaw",   "min_deg": -180.0, "max_deg": 180.0,
                     "sbus_channel": 7},
                ],
                "hardware": {
                    "port":     "/dev/ttyUSB0",
                    "baudrate": 115200,
                },
                "enabled": True,
            }
        ],
        "video": {"mode": "headless"},
        "sbus":  {"enabled": False},
    }

    cfg = SystemConfig.from_dict(config_dict)
    gd  = cfg.gimbals[0]

    logger.info("GimbalDef id          : %s", gd.id)
    logger.info("GimbalDef backend_type: %s", gd.backend_type)
    logger.info("GimbalDef roles       : %s", gd.roles)
    logger.info("GimbalDef axes        : %s", gd.get_axes_dict())
    logger.info("GimbalDef hardware    : %s", gd.hardware)

    # cymbal/main.py's _build_gimbals_from_config() will pick up this entry
    # and construct a SimpleBGCGimbalAdapter from it when the backend is wired.
    logger.info(
        "\nTo activate: implement SimpleBGCGimbalAdapter in "
        "cymbal/gimbals/simplebgc_stub.pyx and rebuild.\n"
        "See cymbal/gimbals/simplebgc_stub.pyx for the expected interface."
    )


def main() -> int:
    demo_direct_construction()
    print()
    demo_config_based_construction()
    return 0


if __name__ == "__main__":
    sys.exit(main())
