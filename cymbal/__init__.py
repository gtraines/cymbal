"""
Airborne Gimbal Control System

A Python package for controlling dual gimbals (camera and spotlight) 
on a fixed-wing drone via Raspberry Pi 3B+.
"""

__version__ = "0.1.0"
__author__ = "gtraines"

from cymbal.camera_gimbal.storm32_controller import Storm32Controller
from cymbal.spotlight_gimbal.servo_controller import SpotlightController
from cymbal.sensors.mpu6050 import MPU6050

__all__ = [
    "Storm32Controller",
    "SpotlightController",
    "MPU6050",
]
