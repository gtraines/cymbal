#!/usr/bin/env python3
"""
Example: ServoGimbalAdapter — spotlight gimbal via GPIO PWM servos.

Demonstrates the new library API for a 2-axis servo gimbal using pigpio PWM
and an optional MPU6050 IMU for IMU-assisted stabilization.

Hardware:
  - 2× 360° continuous-rotation servos
      Pitch  → BCM GPIO 17  (PWM signal, 5 V logic via level shifter)
      Yaw    → BCM GPIO 27
  - MPU6050 IMU (I²C bus 1, address 0x68)  — optional, disables stabilization
    when absent
  - pigpiod must be running:  sudo systemctl start pigpiod

New vs old API:
  Old: from cymbal.spotlight_gimbal import SpotlightController
  New: from cymbal.gimbals import ServoGimbalAdapter

The adapter exposes the same set_axes() interface as every other GimbalBase
implementation and adds a stabilize() pass-through for IMU-based correction.
"""

import logging
import sys
import time

# ── New library API ──────────────────────────────────────────────────────────
from cymbal.gimbals import ServoGimbalAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    # ── 1. Construct the adapter ─────────────────────────────────────────────
    spotlight = ServoGimbalAdapter(
        gimbal_id="spotlight_1",
        pitch_pin=17,
        yaw_pin=27,
        i2c_address=0x68,
        i2c_bus=1,
        use_stabilization=True,      # set False to skip MPU6050 init
        roles=["spotlight"],
        axes={
            "pitch": [-90.0, 30.0],
            "yaw":   [-180.0, 180.0],
        },
    )

    logger.info("Adapter created: %r", spotlight)

    # ── 2. Initialize GPIO and IMU ───────────────────────────────────────────
    if not spotlight.initialize():
        logger.error(
            "Servo gimbal init failed.  "
            "Is pigpiod running?  sudo systemctl start pigpiod"
        )
        return 1

    logger.info("Servo gimbal initialized")

    try:
        # ── 3. Center ────────────────────────────────────────────────────────
        logger.info("Centering…")
        spotlight.center()
        time.sleep(2)

        # ── 4. Positioning via set_axes() ────────────────────────────────────
        positions = [
            ({"pitch": -30.0, "yaw":   0.0}, "Aim down 30°"),
            ({"pitch":   0.0, "yaw":  90.0}, "Aim right 90°"),
            ({"pitch": -20.0, "yaw": -90.0}, "Down-left"),
            ({"pitch":   0.0, "yaw":   0.0}, "Return to centre"),
        ]

        for axes, description in positions:
            logger.info("%-30s  axes=%s", description, axes)
            spotlight.set_axes(axes)
            time.sleep(3)

        # ── 5. IMU-based stabilization loop ──────────────────────────────────
        #
        # stabilize() reads the MPU6050 and applies a proportional correction
        # to counteract drone tilt, keeping the payload on-target.
        logger.info("Running stabilization loop for 5 s (try tilting the drone)…")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            spotlight.stabilize()
            time.sleep(0.05)          # 20 Hz

        # ── 6. Status ────────────────────────────────────────────────────────
        status = spotlight.get_status()
        logger.info("Status: %s", status)

    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        # ── 7. Shutdown ──────────────────────────────────────────────────────
        spotlight.shutdown()
        logger.info("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
