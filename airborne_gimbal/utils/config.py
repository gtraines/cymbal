"""
Configuration management for airborne gimbal system.
"""

import json
import os
from typing import Dict, Any
from dataclasses import dataclass, asdict


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
class SystemConfig:
    """Main system configuration."""
    camera_gimbal: CameraGimbalConfig
    spotlight_gimbal: SpotlightGimbalConfig
    log_level: str = "INFO"
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'SystemConfig':
        """Create configuration from dictionary."""
        camera_config = CameraGimbalConfig(**config_dict.get('camera_gimbal', {}))
        spotlight_config = SpotlightGimbalConfig(**config_dict.get('spotlight_gimbal', {}))
        log_level = config_dict.get('log_level', 'INFO')
        return cls(camera_gimbal=camera_config, spotlight_gimbal=spotlight_config, log_level=log_level)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'camera_gimbal': asdict(self.camera_gimbal),
            'spotlight_gimbal': asdict(self.spotlight_gimbal),
            'log_level': self.log_level
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
                spotlight_gimbal=SpotlightGimbalConfig()
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
