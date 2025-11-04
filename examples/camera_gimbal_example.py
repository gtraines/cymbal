#!/usr/bin/env python3
"""
Example: Control camera gimbal using Storm32bgc controller.

This script demonstrates basic control of the Storm32bgc camera gimbal.
"""

import time
import sys
from cymbal.camera_gimbal import Storm32Controller


def main():
    """Main function."""
    print("Storm32 Camera Gimbal Control Example")
    print("=" * 40)
    
    # Create controller
    controller = Storm32Controller(
        port="/dev/ttyAMA0",
        baudrate=115200
    )
    
    # Connect to gimbal
    print("Connecting to Storm32 gimbal...")
    if not controller.connect():
        print("ERROR: Failed to connect to Storm32 gimbal")
        return 1
    
    print("Connected successfully!")
    
    try:
        # Center the gimbal
        print("\nCentering gimbal...")
        controller.center()
        time.sleep(2)
        
        # Move to various positions
        positions = [
            (30, 0, 0, "Looking down 30 degrees"),
            (0, 0, 45, "Looking right 45 degrees"),
            (-20, 0, -45, "Looking up 20 degrees, left 45 degrees"),
            (0, 0, 0, "Back to center")
        ]
        
        for pitch, roll, yaw, description in positions:
            print(f"\n{description}")
            print(f"Setting position: pitch={pitch}, roll={roll}, yaw={yaw}")
            controller.set_angle(pitch, roll, yaw)
            time.sleep(3)
        
        # Get status
        print("\nRetrieving gimbal status...")
        status = controller.get_status()
        if status:
            print(f"Status: {status}")
        
        print("\nExample complete!")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Disconnect
        print("\nDisconnecting...")
        controller.disconnect()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
