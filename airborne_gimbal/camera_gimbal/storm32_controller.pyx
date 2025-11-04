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


cdef class Storm32Controller:
    """
    Controller for Storm32bgc brushless gimbal.
    
    Communicates with the Storm32bgc controller via serial UART connection
    to control camera gimbal pitch, roll, and yaw.
    """
    
    cdef public str port
    cdef public int baudrate
    cdef public double timeout
    cdef object serial_conn
    cdef bint _is_connected
    
    def __init__(
        self,
        str port = "/dev/ttyAMA0",
        int baudrate = 115200,
        double timeout = 1.0
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
        self.serial_conn = None
        self._is_connected = False
        
    cpdef bint connect(self):
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
    
    cpdef void disconnect(self):
        """Close serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self._is_connected = False
            logger.info("Disconnected from Storm32")
    
    cpdef bint is_connected(self):
        """Check if controller is connected."""
        return self._is_connected and self.serial_conn and self.serial_conn.is_open
    
    cpdef bint set_angle(self, double pitch, double roll, double yaw):
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
            if pitch < -90:
                pitch = -90
            elif pitch > 90:
                pitch = 90
                
            if roll < -90:
                roll = -90
            elif roll > 90:
                roll = 90
                
            if yaw < -180:
                yaw = -180
            elif yaw > 180:
                yaw = 180
            
            # Storm32 MAVLink command format (simplified)
            command = self._build_angle_command(pitch, roll, yaw)
            self.serial_conn.write(command)
            logger.debug(f"Set angles - Pitch: {pitch}, Roll: {roll}, Yaw: {yaw}")
            return True
        except Exception as e:
            logger.error(f"Failed to set angle: {e}")
            return False
    
    cpdef bint set_speed(self, double pitch_speed, double roll_speed, double yaw_speed):
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
    
    cpdef object get_status(self):
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
    
    cpdef bint center(self):
        """
        Center the gimbal (all axes to 0 degrees).
        
        Returns:
            True if command sent successfully, False otherwise
        """
        return self.set_angle(0, 0, 0)
    
    cdef bytes _build_angle_command(self, double pitch, double roll, double yaw):
        """
        Build MAVLink command for setting angles.
        
        In a real implementation, this would use proper MAVLink message encoding
        with checksums and proper message IDs.
        """
        cdef int pitch_int = int(pitch * 100)
        cdef int roll_int = int(roll * 100)
        cdef int yaw_int = int(yaw * 100)
        
        # Simplified command format
        command = bytearray([0xFA, 0x0E])  # Header
        command.extend(pitch_int.to_bytes(2, 'little', signed=True))
        command.extend(roll_int.to_bytes(2, 'little', signed=True))
        command.extend(yaw_int.to_bytes(2, 'little', signed=True))
        return bytes(command)
    
    cdef bytes _build_speed_command(self, double pitch_speed, double roll_speed, double yaw_speed):
        """Build MAVLink command for setting rotation speeds."""
        cdef int speed_p = int(pitch_speed * 10)
        cdef int speed_r = int(roll_speed * 10)
        cdef int speed_y = int(yaw_speed * 10)
        
        command = bytearray([0xFA, 0x0F])  # Header
        command.extend(speed_p.to_bytes(2, 'little', signed=True))
        command.extend(speed_r.to_bytes(2, 'little', signed=True))
        command.extend(speed_y.to_bytes(2, 'little', signed=True))
        return bytes(command)
    
    cdef bytes _build_status_request(self):
        """Build MAVLink status request command."""
        return bytes([0xFA, 0x10])  # Header for status request
    
    cdef dict _parse_status_response(self, bytes response):
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
