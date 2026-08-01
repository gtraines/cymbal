"""
Configuration management for cymbal airborne gimbal system.
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class CameraGimbalConfig:
    """Configuration for Storm32 camera gimbal (legacy; use GimbalDef for new code)."""
    serial_port: str = "/dev/ttyAMA0"
    baudrate: int = 115200
    timeout: float = 1.0


@dataclass
class SpotlightGimbalConfig:
    """Configuration for spotlight gimbal (legacy; use GimbalDef for new code)."""
    pitch_pin: int = 17
    yaw_pin: int = 27
    i2c_address: int = 0x68
    i2c_bus: int = 1
    use_stabilization: bool = True


@dataclass
class GPSConfig:
    """Configuration for USB GPS receiver and terrain elevation."""
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    update_rate_hz: int = 5
    terrain_db_path: str = "/opt/cymbal/srtm"
    use_terrain_db: bool = True
    min_fix_quality: int = 1


@dataclass
class GeoConfig:
    """Configuration for offline reverse geocoding database."""
    address_db_path: str = "/opt/cymbal/addresses.db"
    search_radius_deg: float = 0.01
    enabled: bool = True


@dataclass
class OSDConfig:
    """Configuration for on-screen display overlay."""
    enabled: bool = True
    font_scale: float = 0.6
    font_thickness: int = 1
    text_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    background_color: List[int] = field(default_factory=lambda: [0, 0, 0])
    background_alpha: float = 0.5
    show_sbus_channels: bool = False
    show_compass: bool = True
    compass_radius: int = 45


@dataclass
class SBUSConfig:
    """Configuration for S-BUS RC signal decoder."""
    gpio_pin: int = 4
    socket_path: str = "/run/cymbal/sbus.sock"
    failsafe_action: str = "center"
    frame_timeout_ms: int = 100
    enabled: bool = True


@dataclass
class TelemetryConfig:
    """
    Configuration for the telemetry pipeline.

    mode:
        "in_process"  — GPS + terrain + address lookup run inside the
                        main cymbal process (legacy behaviour).
        "sidecar"     — the cymbal-telemetry service publishes TelemetrySnapshot
                        datagrams; the controller consumes them via a
                        SocketTelemetryProvider (no serial/SQLite blocking in
                        the control loop).

    socket_path:
        Unix domain socket path used by the sidecar publisher and reader.
        Must match the path configured in cymbal-telemetry.service.

    frame_timeout_ms:
        If no snapshot arrives within this many milliseconds the
        SocketTelemetryProvider clears has_fix and address to signal stale
        data.  Recommended: 2× the sidecar publish interval (default 5 Hz
        → 200 ms; use 500 ms for safety margin).
    """
    mode: str = "in_process"
    socket_path: str = "/run/cymbal/telemetry.sock"
    frame_timeout_ms: int = 500


@dataclass
class ChannelMapConfig:
    """Mapping of S-BUS channels to gimbal control functions (legacy schema)."""
    camera_pitch: int = 6
    camera_yaw: int = 7
    spotlight_pitch: int = 8
    spotlight_yaw: int = 9
    mode_select: int = 5
    poi_lock: int = 10
    camera_pitch_range: List[float] = field(default_factory=lambda: [-90.0, 30.0])
    camera_yaw_range: List[float] = field(default_factory=lambda: [-90.0, 90.0])
    spotlight_pitch_range: List[float] = field(default_factory=lambda: [-90.0, 30.0])
    spotlight_yaw_range: List[float] = field(default_factory=lambda: [-180.0, 180.0])


# ---------------------------------------------------------------------------
# New modular gimbal model
# ---------------------------------------------------------------------------

@dataclass
class AxisConfig:
    """
    Configuration for one axis of a gimbal.

    Attributes:
        name:         Axis name, e.g. "pitch", "roll", "yaw".
        min_deg:      Minimum commanded angle in degrees.
        max_deg:      Maximum commanded angle in degrees.
        sbus_channel: S-BUS channel number driving this axis (1-indexed),
                      or None if the axis is not RC-controlled.
    """
    name: str
    min_deg: float
    max_deg: float
    sbus_channel: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "min_deg": self.min_deg,
            "max_deg": self.max_deg,
            "sbus_channel": self.sbus_channel,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'AxisConfig':
        return cls(
            name=d["name"],
            min_deg=float(d.get("min_deg", -90.0)),
            max_deg=float(d.get("max_deg", 90.0)),
            sbus_channel=d.get("sbus_channel"),
        )


@dataclass
class GimbalDef:
    """
    Definition of one gimbal in the system.

    Attributes:
        id:           Unique identifier used to reference this gimbal.
        backend_type: Hardware backend.  One of:
                          "storm32"    — Storm32bgc serial UART
                          "servo_gpio" — GPIO PWM servos via pigpio
                          "simplebgc"  — SimpleBGC (not yet implemented)
        roles:        List of functional role strings.
                      Common values: "camera", "spotlight", "camera+spotlight".
        axes:         List of AxisConfig objects describing each controlled axis.
        hardware:     Dict of backend-specific hardware parameters.
                      storm32    → serial_port, baudrate, timeout
                      servo_gpio → pitch_pin, yaw_pin, i2c_address, i2c_bus,
                                   use_stabilization
                      simplebgc  → port, baudrate
        enabled:      Set False to disable this gimbal without removing its entry.
    """
    id: str
    backend_type: str
    roles: List[str]
    axes: List[AxisConfig]
    hardware: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "backend_type": self.backend_type,
            "roles": list(self.roles),
            "axes": [a.to_dict() for a in self.axes],
            "hardware": dict(self.hardware),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'GimbalDef':
        axes = [AxisConfig.from_dict(a) for a in d.get("axes", [])]
        return cls(
            id=d["id"],
            backend_type=d.get("backend_type", "servo_gpio"),
            roles=list(d.get("roles", [])),
            axes=axes,
            hardware=dict(d.get("hardware", {})),
            enabled=bool(d.get("enabled", True)),
        )

    def get_axes_dict(self) -> Dict[str, List[float]]:
        """Return {axis_name: [min_deg, max_deg]} for GimbalBase.axes."""
        return {a.name: [a.min_deg, a.max_deg] for a in self.axes}


@dataclass
class VideoOutputConfig:
    """
    Configuration for the video output pipeline.

    Attributes:
        mode:          Output mode.  One of:
                           "headless"  — render OSD onto frames but never display
                           "display"   — display via cv2.imshow (requires desktop)
                           "composite" — write frames to VideoWriter / composite
        camera_source: Camera device index (int, e.g. 0 for /dev/video0) or a
                       file/stream path (str).  Use -1 to disable camera capture
                       and run OSD on a synthetic blank frame.
        window_title:  Window title for display mode.
        output_path:   File path for composite mode VideoWriter.
        fps:           Frame rate for composite mode VideoWriter.
        width:         Frame width in pixels.
        height:        Frame height in pixels.
    """
    mode: str = "headless"
    camera_source: int = 0
    window_title: str = "Cymbal OSD"
    output_path: str = ""
    fps: float = 30.0
    width: int = 640
    height: int = 480

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "window_title": self.window_title,
            "output_path": self.output_path,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'VideoOutputConfig':
        return cls(
            mode=d.get("mode", "headless"),
            camera_source=int(d.get("camera_source", 0)),
            window_title=d.get("window_title", "Cymbal OSD"),
            output_path=d.get("output_path", ""),
            fps=float(d.get("fps", 30.0)),
            width=int(d.get("width", 640)),
            height=int(d.get("height", 480)),
        )


# ---------------------------------------------------------------------------
# Helper: synthesize GimbalDef list from legacy camera/spotlight config
# ---------------------------------------------------------------------------

def _legacy_to_gimbal_defs(
    cam: CameraGimbalConfig,
    spot: SpotlightGimbalConfig,
    channel_map: ChannelMapConfig,
) -> List[GimbalDef]:
    """
    Build a two-element GimbalDef list from the legacy dual-gimbal config.

    This lets old JSON files (with camera_gimbal / spotlight_gimbal keys) work
    with the new list-based orchestration path.
    """
    camera_def = GimbalDef(
        id="camera_1",
        backend_type="storm32",
        roles=["camera"],
        axes=[
            AxisConfig("pitch", channel_map.camera_pitch_range[0],
                       channel_map.camera_pitch_range[1],
                       sbus_channel=channel_map.camera_pitch),
            AxisConfig("roll",  -90.0, 90.0, sbus_channel=None),
            AxisConfig("yaw",   channel_map.camera_yaw_range[0],
                       channel_map.camera_yaw_range[1],
                       sbus_channel=channel_map.camera_yaw),
        ],
        hardware={
            "serial_port": cam.serial_port,
            "baudrate": cam.baudrate,
            "timeout": cam.timeout,
        },
    )

    spotlight_def = GimbalDef(
        id="spotlight_1",
        backend_type="servo_gpio",
        roles=["spotlight"],
        axes=[
            AxisConfig("pitch", channel_map.spotlight_pitch_range[0],
                       channel_map.spotlight_pitch_range[1],
                       sbus_channel=channel_map.spotlight_pitch),
            AxisConfig("yaw",   channel_map.spotlight_yaw_range[0],
                       channel_map.spotlight_yaw_range[1],
                       sbus_channel=channel_map.spotlight_yaw),
        ],
        hardware={
            "pitch_pin": spot.pitch_pin,
            "yaw_pin": spot.yaw_pin,
            "i2c_address": spot.i2c_address,
            "i2c_bus": spot.i2c_bus,
            "use_stabilization": spot.use_stabilization,
        },
    )

    return [camera_def, spotlight_def]


# ---------------------------------------------------------------------------
# SystemConfig
# ---------------------------------------------------------------------------

@dataclass
class SystemConfig:
    """
    Main system configuration.

    The ``gimbals`` list is the primary way to specify hardware.  When an old
    JSON file is loaded that only contains ``camera_gimbal`` / ``spotlight_gimbal``
    keys, those are automatically translated into a two-element ``gimbals`` list
    (with a deprecation warning) so existing deployments continue to work.

    Backward-compatible fields (camera_gimbal, spotlight_gimbal) are retained
    for direct access by legacy code paths in main.pyx.
    """
    camera_gimbal: CameraGimbalConfig = field(default_factory=CameraGimbalConfig)
    spotlight_gimbal: SpotlightGimbalConfig = field(default_factory=SpotlightGimbalConfig)
    gps: GPSConfig = field(default_factory=GPSConfig)
    geo: GeoConfig = field(default_factory=GeoConfig)
    osd: OSDConfig = field(default_factory=OSDConfig)
    sbus: SBUSConfig = field(default_factory=SBUSConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    channel_map: ChannelMapConfig = field(default_factory=ChannelMapConfig)
    gimbals: List[GimbalDef] = field(default_factory=list)
    video: VideoOutputConfig = field(default_factory=VideoOutputConfig)
    log_level: str = "INFO"

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'SystemConfig':
        """Create configuration from dictionary."""
        camera_config = CameraGimbalConfig(**config_dict.get('camera_gimbal', {}))
        spotlight_config = SpotlightGimbalConfig(**config_dict.get('spotlight_gimbal', {}))
        gps_config = GPSConfig(**config_dict.get('gps', {}))
        geo_config = GeoConfig(**config_dict.get('geo', {}))
        osd_config = OSDConfig(**config_dict.get('osd', {}))
        sbus_config = SBUSConfig(**config_dict.get('sbus', {}))
        telemetry_config = TelemetryConfig(**config_dict.get('telemetry', {}))
        channel_map_config = ChannelMapConfig(**config_dict.get('channel_map', {}))
        log_level = config_dict.get('log_level', 'INFO')

        # New modular gimbal list
        raw_gimbals = config_dict.get('gimbals', [])
        if raw_gimbals:
            gimbals = [GimbalDef.from_dict(g) for g in raw_gimbals]
        else:
            # Legacy path: synthesize from camera_gimbal + spotlight_gimbal
            has_legacy = (
                'camera_gimbal' in config_dict
                or 'spotlight_gimbal' in config_dict
            )
            if has_legacy:
                logger.warning(
                    "config: 'camera_gimbal'/'spotlight_gimbal' keys are deprecated; "
                    "migrate to a 'gimbals' list.  Auto-translating for this session."
                )
            gimbals = _legacy_to_gimbal_defs(
                camera_config, spotlight_config, channel_map_config
            )

        video_config = VideoOutputConfig.from_dict(config_dict.get('video', {}))

        return cls(
            camera_gimbal=camera_config,
            spotlight_gimbal=spotlight_config,
            gps=gps_config,
            geo=geo_config,
            osd=osd_config,
            sbus=sbus_config,
            telemetry=telemetry_config,
            channel_map=channel_map_config,
            gimbals=gimbals,
            video=video_config,
            log_level=log_level,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (new schema, includes gimbals list)."""
        return {
            'camera_gimbal':  asdict(self.camera_gimbal),
            'spotlight_gimbal': asdict(self.spotlight_gimbal),
            'gimbals':        [g.to_dict() for g in self.gimbals],
            'video':          self.video.to_dict(),
            'gps':            asdict(self.gps),
            'geo':            asdict(self.geo),
            'osd':            asdict(self.osd),
            'sbus':           asdict(self.sbus),
            'telemetry':      asdict(self.telemetry),
            'channel_map':    asdict(self.channel_map),
            'log_level':      self.log_level,
        }

    @classmethod
    def load(cls, config_path: str) -> 'SystemConfig':
        """
        Load configuration from JSON file.

        Returns a default configuration when the file does not exist.
        """
        if not os.path.exists(config_path):
            # Default: synthesise a standard dual-gimbal setup
            default = cls()
            default.gimbals = _legacy_to_gimbal_defs(
                default.camera_gimbal,
                default.spotlight_gimbal,
                default.channel_map,
            )
            return default

        with open(config_path, 'r') as f:
            config_dict = json.load(f)

        return cls.from_dict(config_dict)

    def save(self, config_path: str) -> None:
        """Save configuration to JSON file."""
        with open(config_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
