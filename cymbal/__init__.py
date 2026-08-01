"""
Cymbal Airborne Gimbal Control System

A Python/Cython package for controlling gimbals on fixed-wing drones.

Stable public exports — import what you need::

    from cymbal.controller import CymbalController
    from cymbal.gimbals import GimbalBase, Storm32GimbalAdapter, ServoGimbalAdapter
    from cymbal.video import VideoSink, HeadlessSink, DisplaySink
    from cymbal.utils.config import SystemConfig

Legacy imports (still supported)::

    from cymbal import Storm32Controller, SpotlightController, MPU6050

Note: Cython-backed exports require compiled extensions (.so on Linux).
      They are None when the package is imported from an uncompiled source tree.
"""

__version__ = "0.4.0"
__author__  = "gtraines"

# ---------------------------------------------------------------------------
# Pure-Python video sinks — always importable
# ---------------------------------------------------------------------------
from cymbal.video import VideoSink, HeadlessSink, DisplaySink

# ---------------------------------------------------------------------------
# Cython-backed exports — guarded for uncompiled source trees
# ---------------------------------------------------------------------------

try:
    from cymbal.controller import CymbalController, GimbalController
except ImportError:
    CymbalController = None   # type: ignore[assignment,misc]
    GimbalController = None   # type: ignore[assignment,misc]

try:
    from cymbal.gimbals import (
        GimbalBase,
        Storm32GimbalAdapter,
        ServoGimbalAdapter,
        SimpleBGCGimbalAdapter,
    )
except ImportError:
    GimbalBase = None              # type: ignore[assignment,misc]
    Storm32GimbalAdapter = None    # type: ignore[assignment,misc]
    ServoGimbalAdapter = None      # type: ignore[assignment,misc]
    SimpleBGCGimbalAdapter = None  # type: ignore[assignment,misc]

try:
    from cymbal.camera_gimbal.storm32_controller import Storm32Controller
except ImportError:
    Storm32Controller = None  # type: ignore[assignment,misc]

try:
    from cymbal.spotlight_gimbal.servo_controller import SpotlightController
except ImportError:
    SpotlightController = None  # type: ignore[assignment,misc]

try:
    from cymbal.sensors.mpu6050 import MPU6050
except ImportError:
    MPU6050 = None  # type: ignore[assignment,misc]

__all__ = [
    # New API
    "CymbalController",
    "GimbalController",
    "GimbalBase",
    "Storm32GimbalAdapter",
    "ServoGimbalAdapter",
    "SimpleBGCGimbalAdapter",
    "VideoSink",
    "HeadlessSink",
    "DisplaySink",
    # Legacy (None when Cython extensions not compiled)
    "Storm32Controller",
    "SpotlightController",
    "MPU6050",
]
