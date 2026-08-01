"""Gimbal abstraction layer for Cymbal."""

try:
    from cymbal.gimbals.base import GimbalBase
except ImportError:
    GimbalBase = None  # type: ignore[assignment,misc]

try:
    from cymbal.gimbals.storm32_adapter import Storm32GimbalAdapter
except ImportError:
    Storm32GimbalAdapter = None  # type: ignore[assignment,misc]

try:
    from cymbal.gimbals.servo_adapter import ServoGimbalAdapter
except ImportError:
    ServoGimbalAdapter = None  # type: ignore[assignment,misc]

try:
    from cymbal.gimbals.simplebgc_stub import SimpleBGCGimbalAdapter
except ImportError:
    SimpleBGCGimbalAdapter = None  # type: ignore[assignment,misc]

__all__ = [
    "GimbalBase",
    "Storm32GimbalAdapter",
    "ServoGimbalAdapter",
    "SimpleBGCGimbalAdapter",
]
