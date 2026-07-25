"""
Configuration management for cymbal airborne gimbal system.
"""

import json
import os
from typing import Dict, Any, List
from dataclasses import dataclass, asdict, field


@dataclass
class CameraGimbalConfig:
    """Configuration for Storm32 camera gimbal."""
    serial_port: str = "/dev/ttyAMA0"
    baudrate: int = 115200
    timeout: float = 1.0


@dataclass
class SpotlightGimbalConfig:
    """Configuration for spotlight gimbal."""
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


@dataclass
class SBUSConfig:
    """Configuration for S-BUS RC signal decoder."""
    gpio_pin: int = 4
    socket_path: str = "/run/cymbal/sbus.sock"
    failsafe_action: str = "center"
    frame_timeout_ms: int = 100
    enabled: bool = True


@dataclass
class ChannelMapConfig:
    """Mapping of S-BUS channels to gimbal control functions."""
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


@dataclass
class SystemConfig:
    """Main system configuration."""
    camera_gimbal: CameraGimbalConfig
    spotlight_gimbal: SpotlightGimbalConfig
    gps: GPSConfig = field(default_factory=GPSConfig)
    geo: GeoConfig = field(default_factory=GeoConfig)
    osd: OSDConfig = field(default_factory=OSDConfig)
    sbus: SBUSConfig = field(default_factory=SBUSConfig)
    channel_map: ChannelMapConfig = field(default_factory=ChannelMapConfig)
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
        channel_map_config = ChannelMapConfig(**config_dict.get('channel_map', {}))
        log_level = config_dict.get('log_level', 'INFO')
        return cls(
            camera_gimbal=camera_config,
            spotlight_gimbal=spotlight_config,
            gps=gps_config,
            geo=geo_config,
            osd=osd_config,
            sbus=sbus_config,
            channel_map=channel_map_config,
            log_level=log_level,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'camera_gimbal': asdict(self.camera_gimbal),
            'spotlight_gimbal': asdict(self.spotlight_gimbal),
            'gps': asdict(self.gps),
            'geo': asdict(self.geo),
            'osd': asdict(self.osd),
            'sbus': asdict(self.sbus),
            'channel_map': asdict(self.channel_map),
            'log_level': self.log_level,
        }

    @classmethod
    def load(cls, config_path: str) -> 'SystemConfig':
        """
        Load configuration from JSON file.

        Args:
            config_path: Path to configuration file

        Returns:
            SystemConfig instance
        """
        if not os.path.exists(config_path):
            # Return default configuration
            return cls(
                camera_gimbal=CameraGimbalConfig(),
                spotlight_gimbal=SpotlightGimbalConfig(),
            )

        with open(config_path, 'r') as f:
            config_dict = json.load(f)

        return cls.from_dict(config_dict)

    def save(self, config_path: str) -> None:
        """
        Save configuration to JSON file.

        Args:
            config_path: Path to save configuration file
        """
        with open(config_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
