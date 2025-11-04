#!/usr/bin/env python3
"""
Example: Synchronized control of both gimbals.

This script demonstrates coordinated control of camera and spotlight gimbals.
"""

import time
import sys
from airborne_gimbal.utils.config import SystemConfig
from airborne_gimbal.main import GimbalController


def main():
    """Main function."""
    print("Dual Gimbal Control Example")
    print("=" * 40)
    
    # Load configuration
    config = SystemConfig.load('config.json')
    
    # Create controller
    controller = GimbalController(config)
    
    # Initialize
    print("Initializing gimbal system...")
    if not controller.initialize():
        print("ERROR: Failed to initialize gimbal system")
        return 1
    
    print("Initialized successfully!")
    
    try:
        # Center both gimbals
        print("\nCentering all gimbals...")
        controller.center_all()
        time.sleep(2)
        
        # Get status
        print("\nGimbal Status:")
        status = controller.get_status()
        print(f"Camera Gimbal: {status['camera_gimbal']}")
        print(f"Spotlight Gimbal: {status['spotlight_gimbal']}")
        
        # Synchronized movements
        print("\nPerforming synchronized movements...")
        
        movements = [
            (30, 0, "Both looking down 30 degrees"),
            (0, 45, "Both looking right 45 degrees"),
            (-20, -45, "Both looking up 20 degrees, left 45 degrees"),
            (0, 0, "Both back to center")
        ]
        
        for pitch, yaw, description in movements:
            print(f"\n{description}")
            controller.sync_gimbals(pitch, yaw)
            time.sleep(3)
        
        print("\nExample complete!")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Shutdown
        print("\nShutting down...")
        controller.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
