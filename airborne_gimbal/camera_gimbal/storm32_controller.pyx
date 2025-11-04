"""
Storm32bgc Brushless Gimbal Controller

This module provides an interface to control the Storm32bgc brushless gimbal
controller via serial communication (UART).

The Storm32bgc uses the MAVLink protocol for communication.
"""

import serial
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class Storm32Controller:
    """
    Controller for Storm32bgc brushless gimbal.
    
    Communicates with the Storm32bgc controller via serial UART connection
    to control camera gimbal pitch, roll, and yaw.
    """
    
    def __init__(
        self,
        port: str = "/dev/ttyAMA0",
        baudrate: int = 115200,
        timeout: float = 1.0
    ):
        """
        Initialize Storm32 controller.
        
        Args:
            port: Serial port (default: /dev/ttyAMA0 for RPi UART)
            baudrate: Communication speed (default: 115200)
            timeout: Serial timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None
        self._is_connected = False
        
    def connect(self) -> bool:
        """
        Establish serial connection to Storm32 controller.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self._is_connected = True
            logger.info(f"Connected to Storm32 on {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to Storm32: {e}")
            self._is_connected = False
            return False
    
    def disconnect(self) -> None:
        """Close serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self._is_connected = False
            logger.info("Disconnected from Storm32")
    
    def is_connected(self) -> bool:
        """Check if controller is connected."""
        return self._is_connected and self.serial_conn and self.serial_conn.is_open
    
    def set_angle(self, pitch: float, roll: float, yaw: float) -> bool:
        """
        Set gimbal angles.
        
        Args:
            pitch: Pitch angle in degrees (-90 to +90)
            roll: Roll angle in degrees (-90 to +90)
            yaw: Yaw angle in degrees (-180 to +180)
            
        Returns:
            True if command sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot set angle: Not connected to Storm32")
            return False
        
        try:
            # Clamp values to valid ranges
            pitch = max(-90, min(90, pitch))
            roll = max(-90, min(90, roll))
            yaw = max(-180, min(180, yaw))
            
            # Storm32 MAVLink command format (simplified)
            # In a real implementation, this would use proper MAVLink encoding
            command = self._build_angle_command(pitch, roll, yaw)
            self.serial_conn.write(command)
            logger.debug(f"Set angles - Pitch: {pitch}, Roll: {roll}, Yaw: {yaw}")
            return True
        except Exception as e:
            logger.error(f"Failed to set angle: {e}")
            return False
    
    def set_speed(self, pitch_speed: float, roll_speed: float, yaw_speed: float) -> bool:
        """
        Set gimbal rotation speeds.
        
        Args:
            pitch_speed: Pitch rotation speed in degrees/second
            roll_speed: Roll rotation speed in degrees/second
            yaw_speed: Yaw rotation speed in degrees/second
            
        Returns:
            True if command sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot set speed: Not connected to Storm32")
            return False
        
        try:
            command = self._build_speed_command(pitch_speed, roll_speed, yaw_speed)
            self.serial_conn.write(command)
            logger.debug(f"Set speeds - Pitch: {pitch_speed}, Roll: {roll_speed}, Yaw: {yaw_speed}")
            return True
        except Exception as e:
            logger.error(f"Failed to set speed: {e}")
            return False
    
    def get_status(self) -> Optional[dict]:
        """
        Get current gimbal status.
        
        Returns:
            Dictionary with status information or None if failed
        """
        if not self.is_connected():
            logger.error("Cannot get status: Not connected to Storm32")
            return None
        
        try:
            # Request status
            self.serial_conn.write(self._build_status_request())
            time.sleep(0.1)  # Wait for response
            
            if self.serial_conn.in_waiting > 0:
                response = self.serial_conn.read(self.serial_conn.in_waiting)
                return self._parse_status_response(response)
            return None
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return None
    
    def center(self) -> bool:
        """
        Center the gimbal (all axes to 0 degrees).
        
        Returns:
            True if command sent successfully, False otherwise
        """
        return self.set_angle(0, 0, 0)
    
    def _build_angle_command(self, pitch: float, roll: float, yaw: float) -> bytes:
        """
        Build MAVLink command for setting angles.
        
        In a real implementation, this would use proper MAVLink message encoding
        with checksums and proper message IDs.
        """
        # Placeholder - real implementation would use pymavlink
        # Converting angles to int16 values (degrees * 100)
        pitch_int = int(pitch * 100)
        roll_int = int(roll * 100)
        yaw_int = int(yaw * 100)
        
        # Simplified command format
        command = bytearray([0xFA, 0x0E])  # Header
        command.extend(pitch_int.to_bytes(2, 'little', signed=True))
        command.extend(roll_int.to_bytes(2, 'little', signed=True))
        command.extend(yaw_int.to_bytes(2, 'little', signed=True))
        return bytes(command)
    
    def _build_speed_command(self, pitch_speed: float, roll_speed: float, yaw_speed: float) -> bytes:
        """Build MAVLink command for setting rotation speeds."""
        # Placeholder implementation
        speed_p = int(pitch_speed * 10)
        speed_r = int(roll_speed * 10)
        speed_y = int(yaw_speed * 10)
        
        command = bytearray([0xFA, 0x0F])  # Header
        command.extend(speed_p.to_bytes(2, 'little', signed=True))
        command.extend(speed_r.to_bytes(2, 'little', signed=True))
        command.extend(speed_y.to_bytes(2, 'little', signed=True))
        return bytes(command)
    
    def _build_status_request(self) -> bytes:
        """Build MAVLink status request command."""
        # Placeholder implementation
        return bytes([0xFA, 0x10])  # Header for status request
    
    def _parse_status_response(self, response: bytes) -> dict:
        """Parse status response from Storm32."""
        # Placeholder implementation
        return {
            "connected": True,
            "pitch": 0,
            "roll": 0,
            "yaw": 0,
            "voltage": 12.0,
            "status": "OK"
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
