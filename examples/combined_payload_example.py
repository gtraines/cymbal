#!/usr/bin/env python3
"""
Example: Combined payload gimbal — one gimbal, two roles.

A single gimbal mount can carry both a camera and a spotlight on the same
pan/tilt head.  By assigning roles=["camera", "spotlight"] the
CymbalController will route both camera and spotlight commands to the
same physical gimbal.

Hardware scenario:
  - One 2-axis servo gimbal (pitch + yaw) mounted under the drone.
  - A camera module and an LED spotlight rigidly co-mounted on the head.
  - MPU6050 IMU for stabilization.

Use cases:
  - Lightweight fixed-wing where weight budget allows only one pan/tilt head.
  - Search-and-rescue where the light and camera must point at the same target.
"""

import logging
import sys
import time

from cymbal.gimbals import ServoGimbalAdapter
from cymbal.controller import CymbalController
from cymbal.config.config import (
    SystemConfig, GimbalDef, AxisConfig, VideoOutputConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


def build_config() -> SystemConfig:
    """Build a SystemConfig describing one combined camera+spotlight gimbal."""
    return SystemConfig.from_dict({
        "gimbals": [
            {
                "id":           "combo_1",
                "backend_type": "servo_gpio",
                "roles":        ["camera", "spotlight"],   # ← dual role
                "axes": [
                    {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0,
                     "sbus_channel": 6},
                    {"name": "yaw",   "min_deg": -180.0, "max_deg": 180.0,
                     "sbus_channel": 7},
                ],
                "hardware": {
                    "pitch_pin":        17,
                    "yaw_pin":          27,
                    "i2c_address":      0x68,
                    "i2c_bus":          1,
                    "use_stabilization": True,
                },
            }
        ],
        "video":  {"mode": "headless"},
        "sbus":   {"enabled": False},
        "gps":    {"use_terrain_db": False},
        "geo":    {"enabled": False},
    })


def main() -> int:
    config = build_config()
    gd     = config.gimbals[0]

    # ── 1. Build the adapter from the GimbalDef ──────────────────────────────
    hw = gd.hardware
    combined = ServoGimbalAdapter(
        gimbal_id=gd.id,
        pitch_pin=hw["pitch_pin"],
        yaw_pin=hw["yaw_pin"],
        i2c_address=hw["i2c_address"],
        i2c_bus=hw["i2c_bus"],
        use_stabilization=hw["use_stabilization"],
        roles=gd.roles,                     # ["camera", "spotlight"]
        axes=gd.get_axes_dict(),
    )

    logger.info("Combined gimbal: id=%s  roles=%s", combined.gimbal_id, combined.roles)

    # ── 2. Wire into CymbalController ───────────────────────────────────────
    ctrl = CymbalController(
        gimbals=[combined],
        config=config,
        logger=logger,
    )

    if not ctrl.initialize():
        logger.error("Failed to initialize controller")
        return 1

    try:
        # ── 3. Backward-compat role helpers ──────────────────────────────────
        # set_camera_position() / set_spotlight_position() both route to the
        # same physical gimbal because it carries both roles.
        logger.info("Center all…")
        ctrl.center_all()
        time.sleep(2)

        logger.info("Camera-style command: pitch=-30°, yaw=0°")
        ctrl.set_camera_position(-30.0, 0.0, 0.0)
        time.sleep(3)

        logger.info("Spotlight-style command: pitch=-15°, yaw=45°")
        ctrl.set_spotlight_position(-15.0, 45.0)
        time.sleep(3)

        # ── 4. Direct axis command by id ─────────────────────────────────────
        logger.info("Direct set_gimbal_axes: pitch=-45°, yaw=-90°")
        ctrl.set_gimbal_axes("combo_1", {"pitch": -45.0, "yaw": -90.0})
        time.sleep(3)

        # ── 5. Sync both roles to the same POI bearing ───────────────────────
        logger.info("sync_gimbals: pitch=-20°, yaw=30°")
        ctrl.sync_gimbals(-20.0, 30.0)
        time.sleep(3)

        logger.info("Status: %s", ctrl.get_status())

    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        ctrl.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
