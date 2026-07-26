"""Sensor modules for gimbal stabilization and navigation."""

from cymbal.sensors.mpu6050 import MPU6050
from cymbal.sensors.gps_sensor import GPSSensor

__all__ = ["MPU6050", "GPSSensor"]
