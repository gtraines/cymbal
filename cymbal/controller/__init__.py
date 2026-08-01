"""Controller package — exports CymbalController and backward-compat alias."""

try:
    from cymbal.controller.telemetry_provider import (
        TelemetryProvider,
        InProcessTelemetryProvider,
    )
except ImportError:
    TelemetryProvider = None              # type: ignore[assignment,misc]
    InProcessTelemetryProvider = None     # type: ignore[assignment,misc]

try:
    from cymbal.controller.socket_telemetry_provider import SocketTelemetryProvider
except ImportError:
    SocketTelemetryProvider = None        # type: ignore[assignment,misc]

try:
    from cymbal.controller.cymbal_controller import CymbalController, GimbalController
except ImportError:
    CymbalController = None   # type: ignore[assignment,misc]
    GimbalController = None   # type: ignore[assignment,misc]

from cymbal.controller.ipc_schemas import (
    TelemetrySnapshotSchema,
    HealthStatusSchema,
    GimbalCommandSchema,
    SOCKET_SBUS_PATH,
    SOCKET_TELEMETRY_PATH,
    SOCKET_HEALTH_PATH,
)

__all__ = [
    "CymbalController",
    "GimbalController",
    "TelemetryProvider",
    "InProcessTelemetryProvider",
    "SocketTelemetryProvider",
    "TelemetrySnapshotSchema",
    "HealthStatusSchema",
    "GimbalCommandSchema",
    "SOCKET_SBUS_PATH",
    "SOCKET_TELEMETRY_PATH",
    "SOCKET_HEALTH_PATH",
]
