#!/usr/bin/env python3
"""
Example: Loading and using the new JSON config schema.

Demonstrates the new ``gimbals`` list format in config.json, the
``video`` output section, and how the library auto-translates old-style
``camera_gimbal`` / ``spotlight_gimbal`` keys for backward compatibility.

Run this script to see how each config variant is parsed — no hardware needed.
"""

import json
import logging
import sys
import tempfile
import os

from cymbal.utils.config import SystemConfig

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# A. New-style config — preferred for all new deployments
# ---------------------------------------------------------------------------

NEW_STYLE_CONFIG = {
    "gimbals": [
        {
            "id":           "camera_1",
            "backend_type": "storm32",
            "roles":        ["camera"],
            "axes": [
                {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0,  "sbus_channel": 6},
                {"name": "roll",  "min_deg": -30.0, "max_deg": 30.0},
                {"name": "yaw",   "min_deg": -90.0, "max_deg": 90.0,  "sbus_channel": 7},
            ],
            "hardware": {
                "serial_port": "/dev/ttyAMA0",
                "baudrate":    115200,
                "timeout":     1.0
            }
        },
        {
            "id":           "spotlight_1",
            "backend_type": "servo_gpio",
            "roles":        ["spotlight"],
            "axes": [
                {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0,  "sbus_channel": 8},
                {"name": "yaw",   "min_deg": -180.0, "max_deg": 180.0, "sbus_channel": 9},
            ],
            "hardware": {
                "pitch_pin":         17,
                "yaw_pin":           27,
                "i2c_address":       104,
                "i2c_bus":           1,
                "use_stabilization": True
            },
            "enabled": True
        }
    ],
    "video": {
        "mode":         "headless",   # "headless" | "display" | "composite"
        "width":        640,
        "height":       480,
        "fps":          30.0,
        "output_path":  ""            # used by composite mode (e.g. /tmp/out.avi)
    },
    "gps": {
        "port":              "/dev/ttyUSB0",
        "baudrate":          9600,
        "update_rate_hz":    5,
        "terrain_db_path":   "/opt/cymbal/srtm",
        "use_terrain_db":    True,
        "min_fix_quality":   1
    },
    "geo": {
        "address_db_path":  "/opt/cymbal/addresses.db",
        "search_radius_deg": 0.01,
        "enabled":          True
    },
    "osd": {
        "enabled":           True,
        "font_scale":        0.6,
        "font_thickness":    1,
        "text_color":        [255, 255, 255],
        "background_color":  [0, 0, 0],
        "background_alpha":  0.5,
        "show_sbus_channels": False,
        "show_compass":      True,
        "compass_radius":    45
    },
    "sbus": {
        "gpio_pin":        4,
        "socket_path":     "/run/cymbal/sbus.sock",
        "failsafe_action": "center",
        "frame_timeout_ms": 100,
        "enabled":         True
    },
    "channel_map": {
        "mode_select": 5,
        "poi_lock":    10
    },
    "log_level": "INFO"
}


# ---------------------------------------------------------------------------
# B. Single combined-payload gimbal
# ---------------------------------------------------------------------------

COMBO_CONFIG = {
    "gimbals": [
        {
            "id":           "combo_1",
            "backend_type": "servo_gpio",
            "roles":        ["camera", "spotlight"],
            "axes": [
                {"name": "pitch", "min_deg": -90.0, "max_deg": 30.0, "sbus_channel": 6},
                {"name": "yaw",   "min_deg": -180.0, "max_deg": 180.0, "sbus_channel": 7},
            ],
            "hardware": {
                "pitch_pin": 17, "yaw_pin": 27,
                "i2c_address": 0x68, "i2c_bus": 1,
                "use_stabilization": True
            }
        }
    ],
    "video": {"mode": "display", "window_title": "Cymbal OSD"}
}


# ---------------------------------------------------------------------------
# C. Legacy-style config — auto-translated for backward compat
# ---------------------------------------------------------------------------

LEGACY_CONFIG = {
    "camera_gimbal": {
        "serial_port": "/dev/ttyAMA0",
        "baudrate":    115200,
        "timeout":     1.0
    },
    "spotlight_gimbal": {
        "pitch_pin":         17,
        "yaw_pin":           27,
        "i2c_address":       104,
        "i2c_bus":           1,
        "use_stabilization": True
    },
    "log_level": "INFO"
}


def print_config_summary(label: str, cfg: SystemConfig) -> None:
    logger.info("── %s ──", label)
    logger.info("  video mode       : %s", cfg.video.mode)
    logger.info("  video resolution : %dx%d @ %.0f fps",
                cfg.video.width, cfg.video.height, cfg.video.fps)
    logger.info("  gimbals (%d):", len(cfg.gimbals))
    for gd in cfg.gimbals:
        axes_names = [a.name for a in gd.axes]
        ch_map = {a.name: a.sbus_channel for a in gd.axes if a.sbus_channel}
        logger.info(
            "    %-20s  backend=%-12s  roles=%-30s  axes=%s  sbus=%s",
            gd.id, gd.backend_type, gd.roles, axes_names, ch_map,
        )
    print()


def demo_load_from_file() -> None:
    """Write a config to a temp file and load it with SystemConfig.load()."""
    logger.info("=== Loading from file ===")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(NEW_STYLE_CONFIG, f, indent=2)
        path = f.name

    try:
        cfg = SystemConfig.load(path)
        print_config_summary("new-style (from file)", cfg)
    finally:
        os.unlink(path)


def main() -> int:
    # ── Parse each config variant ────────────────────────────────────────────
    cfg_new    = SystemConfig.from_dict(NEW_STYLE_CONFIG)
    cfg_combo  = SystemConfig.from_dict(COMBO_CONFIG)
    cfg_legacy = SystemConfig.from_dict(LEGACY_CONFIG)

    print_config_summary("new-style (dual gimbal)", cfg_new)
    print_config_summary("combined payload (single gimbal)", cfg_combo)
    print_config_summary("legacy-style (auto-translated)", cfg_legacy)

    demo_load_from_file()

    # ── Round-trip: serialize back to JSON ───────────────────────────────────
    logger.info("=== Round-trip to JSON ===")
    d = cfg_new.to_dict()
    logger.info("Keys in serialized config: %s", list(d.keys()))
    logger.info("gimbals[0] serialized:")
    for k, v in d["gimbals"][0].items():
        logger.info("  %-14s = %s", k, v)

    return 0


if __name__ == "__main__":
    sys.exit(main())
