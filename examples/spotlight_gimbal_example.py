#!/usr/bin/env python3
"""
Example: Control spotlight gimbal using servos and MPU6050.

This script demonstrates basic control of the spotlight gimbal with stabilization.
"""

import time
import sys
from cymbal.spotlight_gimbal import SpotlightController


def main():
    """Main function."""
    print("Spotlight Gimbal Control Example")
    print("=" * 40)
    
    # Create controller
    controller = SpotlightController(
        pitch_pin=17,
        yaw_pin=27,
        use_stabilization=True
    )
    
    # Initialize controller
    print("Initializing spotlight gimbal...")
    if not controller.initialize():
        print("ERROR: Failed to initialize spotlight gimbal")
        return 1
    
    print("Initialized successfully!")
    
    try:
        # Center the gimbal
        print("\nCentering gimbal...")
        controller.center()
        time.sleep(2)
        
        # Check orientation
        orientation = controller.get_orientation()
        if orientation:
            pitch, roll = orientation
            print(f"Current orientation - Pitch: {pitch:.2f}°, Roll: {roll:.2f}°")
        
        # Move to various positions
        positions = [
            (30, 0, "Looking down 30 degrees"),
            (0, 45, "Looking right 45 degrees"),
            (-20, -45, "Looking up 20 degrees, left 45 degrees"),
            (0, 0, "Back to center")
        ]
        
        for pitch, yaw, description in positions:
            print(f"\n{description}")
            print(f"Setting position: pitch={pitch}, yaw={yaw}")
            controller.set_position(pitch, yaw)
            time.sleep(3)
        
        # Demonstrate speed control
        print("\nDemonstrating speed control...")
        print("Rotating slowly...")
        controller.set_speed(20, 20)
        time.sleep(3)
        
        print("Stopping...")
        controller.stop()
        time.sleep(1)
        
        # Run stabilization for a few seconds
        print("\nDemonstrating stabilization...")
        print("The gimbal will now maintain its position despite movement")
        print("(Try tilting the drone if mounted)")
        
        for i in range(30):
            controller.stabilize()
            time.sleep(0.1)
        
        print("\nExample complete!")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Cleanup
        print("\nShutting down...")
        controller.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
