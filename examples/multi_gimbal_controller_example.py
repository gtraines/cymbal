#!/usr/bin/env python3
"""
Example: CymbalController with multiple injected gimbals.

Shows the primary library usage pattern — building gimbal objects, passing
them into CymbalController, and using the full orchestration API.

This example covers four common hardware configurations:
  A. Classic dual-gimbal (Storm32 camera + servo spotlight) — original setup
  B. Dual camera (two Storm32 gimbals, e.g. fore and aft cameras)
  C. Single combined payload (servo gimbal, both roles)
  D. Building gimbals automatically from a JSON config file

Run the section you need by editing the SCENARIO constant below.
"""

import logging
import sys
import time

from cymbal.gimbals import Storm32GimbalAdapter, ServoGimbalAdapter
from cymbal.controller import CymbalController
from cymbal.utils.config import SystemConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Choose one scenario ──────────────────────────────────────────────────────
SCENARIO = "A"   # "A", "B", "C", or "D"


# ---------------------------------------------------------------------------
# Scenario A — Classic dual-gimbal (Storm32 camera + servo spotlight)
# ---------------------------------------------------------------------------

def scenario_a() -> list:
    """Build the original camera+spotlight combination."""
    return [
        Storm32GimbalAdapter(
            gimbal_id="camera_1",
            port="/dev/ttyAMA0",
            baudrate=115200,
            roles=["camera"],
            axes={
                "pitch": [-90.0, 30.0],
                "roll":  [-30.0, 30.0],
                "yaw":   [-90.0, 90.0],
            },
        ),
        ServoGimbalAdapter(
            gimbal_id="spotlight_1",
            pitch_pin=17,
            yaw_pin=27,
            use_stabilization=True,
            roles=["spotlight"],
            axes={
                "pitch": [-90.0, 30.0],
                "yaw":   [-180.0, 180.0],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario B — Dual camera (two Storm32 gimbals)
# ---------------------------------------------------------------------------

def scenario_b() -> list:
    """Two camera gimbals on separate UART ports for fore/aft coverage."""
    return [
        Storm32GimbalAdapter(
            gimbal_id="camera_fore",
            port="/dev/ttyAMA0",
            baudrate=115200,
            roles=["camera"],
            axes={"pitch": [-90.0, 30.0], "roll": [-30.0, 30.0], "yaw": [-90.0, 90.0]},
        ),
        Storm32GimbalAdapter(
            gimbal_id="camera_aft",
            port="/dev/ttyUSB0",          # second UART on a USB-serial adaptor
            baudrate=115200,
            roles=["camera"],
            axes={"pitch": [-90.0, 30.0], "roll": [-30.0, 30.0], "yaw": [-90.0, 90.0]},
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario C — Single combined payload (one servo gimbal, dual roles)
# ---------------------------------------------------------------------------

def scenario_c() -> list:
    """One servo gimbal carrying both camera and spotlight."""
    return [
        ServoGimbalAdapter(
            gimbal_id="combo_1",
            pitch_pin=17,
            yaw_pin=27,
            use_stabilization=True,
            roles=["camera", "spotlight"],
            axes={
                "pitch": [-90.0, 30.0],
                "yaw":   [-180.0, 180.0],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario D — Build gimbals from a JSON-based SystemConfig
# ---------------------------------------------------------------------------

def scenario_d_config() -> SystemConfig:
    """Return a SystemConfig that describes a dual-gimbal system in JSON form."""
    return SystemConfig.from_dict({
        "gimbals": [
            {
                "id":           "camera_1",
                "backend_type": "storm32",
                "roles":        ["camera"],
                "axes": [
                    {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0,
                     "sbus_channel": 6},
                    {"name": "roll",  "min_deg": -30.0, "max_deg": 30.0},
                    {"name": "yaw",   "min_deg": -90.0, "max_deg": 90.0,
                     "sbus_channel": 7},
                ],
                "hardware": {
                    "serial_port": "/dev/ttyAMA0",
                    "baudrate":    115200,
                    "timeout":     1.0,
                },
            },
            {
                "id":           "spotlight_1",
                "backend_type": "servo_gpio",
                "roles":        ["spotlight"],
                "axes": [
                    {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0,
                     "sbus_channel": 8},
                    {"name": "yaw",   "min_deg": -180.0, "max_deg": 180.0,
                     "sbus_channel": 9},
                ],
                "hardware": {
                    "pitch_pin":         17,
                    "yaw_pin":           27,
                    "i2c_address":       0x68,
                    "i2c_bus":           1,
                    "use_stabilization": True,
                },
            },
        ],
        "video":  {"mode": "headless"},
        "sbus":   {"enabled": False},
        "gps":    {"use_terrain_db": False},
        "geo":    {"enabled": False},
    })


def build_gimbals_from_config(config: SystemConfig) -> list:
    """Instantiate adapters from a config.gimbals list (mirrors main.pyx logic)."""
    gimbals = []
    for gd in config.gimbals:
        if not gd.enabled:
            continue
        hw = gd.hardware
        if gd.backend_type == "storm32":
            gimbals.append(Storm32GimbalAdapter(
                gimbal_id=gd.id,
                port=hw.get("serial_port", "/dev/ttyAMA0"),
                baudrate=int(hw.get("baudrate", 115200)),
                timeout=float(hw.get("timeout", 1.0)),
                roles=list(gd.roles),
                axes=gd.get_axes_dict(),
            ))
        elif gd.backend_type == "servo_gpio":
            gimbals.append(ServoGimbalAdapter(
                gimbal_id=gd.id,
                pitch_pin=int(hw.get("pitch_pin", 17)),
                yaw_pin=int(hw.get("yaw_pin", 27)),
                i2c_address=int(hw.get("i2c_address", 0x68)),
                i2c_bus=int(hw.get("i2c_bus", 1)),
                use_stabilization=bool(hw.get("use_stabilization", True)),
                roles=list(gd.roles),
                axes=gd.get_axes_dict(),
            ))
    return gimbals


# ---------------------------------------------------------------------------
# Run the selected scenario
# ---------------------------------------------------------------------------

def run_controller(gimbals: list, config: SystemConfig) -> int:
    logger.info("Gimbals:")
    for g in gimbals:
        logger.info("  %-20s  roles=%-30s  axes=%s",
                    g.gimbal_id, g.roles, list(g.axes.keys()))

    ctrl = CymbalController(gimbals=gimbals, config=config, logger=logger)

    if not ctrl.initialize():
        logger.error("Initialization failed — check hardware connections")
        return 1

    logger.info("Initialized successfully")

    try:
        # ── Center all ───────────────────────────────────────────────────────
        logger.info("Centering all gimbals…")
        ctrl.center_all()
        time.sleep(2)

        # ── Coordinated sweep ─────────────────────────────────────────────────
        logger.info("Synchronized sweep…")
        for yaw in (-60, -30, 0, 30, 60, 0):
            ctrl.sync_gimbals(pitch=-20.0, yaw=float(yaw))
            time.sleep(2)

        # ── Role-based commands ───────────────────────────────────────────────
        ctrl.set_camera_position(pitch=-30.0, roll=0.0, yaw=45.0)
        time.sleep(2)
        ctrl.set_spotlight_position(pitch=-30.0, yaw=45.0)
        time.sleep(2)

        # ── Direct id-based command ───────────────────────────────────────────
        for gimbal in gimbals:
            ctrl.set_gimbal_axes(gimbal.gimbal_id, {"pitch": 0.0, "yaw": 0.0})

        # ── Status snapshot ──────────────────────────────────────────────────
        status = ctrl.get_status()
        logger.info("Status → mode=%s  poi_locked=%s  address=%r",
                    status["mode"], status["poi_locked"], status["address"])
        for gid, gs in status["gimbals"].items():
            logger.info("  %-20s  %s", gid, gs)

    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        ctrl.shutdown()

    return 0


def main() -> int:
    if SCENARIO == "A":
        logger.info("Scenario A: dual-gimbal (Storm32 camera + servo spotlight)")
        config  = SystemConfig()
        gimbals = scenario_a()

    elif SCENARIO == "B":
        logger.info("Scenario B: dual camera (two Storm32 gimbals)")
        config  = SystemConfig()
        gimbals = scenario_b()

    elif SCENARIO == "C":
        logger.info("Scenario C: single combined payload (servo, dual roles)")
        config  = SystemConfig()
        gimbals = scenario_c()

    elif SCENARIO == "D":
        logger.info("Scenario D: gimbals built from JSON config")
        config  = scenario_d_config()
        gimbals = build_gimbals_from_config(config)

    else:
        logger.error("Unknown SCENARIO %r — set to 'A', 'B', 'C', or 'D'", SCENARIO)
        return 1

    return run_controller(gimbals, config)


if __name__ == "__main__":
    sys.exit(main())
