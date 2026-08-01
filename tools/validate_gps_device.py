#!/usr/bin/env python3
"""
GPS Device Validation Utility

Tests serial communication with a GPS device and validates NMEA sentence
parsing with pynmea2. Use this to verify GPS hardware connectivity before
integrating with the cymbal GPSSensor component.

Usage:
    python tools/validate_gps_device.py                    # Auto-detect device
    python tools/validate_gps_device.py /dev/ttyUSB0       # Specific device
    python tools/validate_gps_device.py /dev/ttyUSB0 9600  # Custom baud rate

Exit codes:
    0 - GPS device validated successfully
    1 - Missing dependencies
    2 - Device not found or cannot open
    3 - No valid NMEA data received
    4 - GPS fix not acquired (timeout)
"""

import argparse
import glob
import logging
import sys
import time
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    
    try:
        import serial
    except ImportError:
        missing.append('pyserial')
    
    try:
        import pynmea2
    except ImportError:
        missing.append('pynmea2')
    
    if missing:
        logger.error(f"Missing required packages: {', '.join(missing)}")
        logger.error("Install with: pip install pyserial pynmea2")
        return False
    
    return True


def find_gps_devices():
    """
    Auto-detect potential GPS devices.
    
    Returns:
        List of device paths that might be GPS receivers.
    """
    candidates = []
    
    # Common USB GPS device patterns
    patterns = [
        '/dev/ttyUSB*',
        '/dev/ttyACM*',
        '/dev/serial/by-id/*GPS*',
        '/dev/serial/by-id/*u-blox*',
        '/dev/serial/by-id/*GlobalTop*',
    ]
    
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    
    return sorted(set(candidates))


def validate_gps_device(port, baudrate=9600, timeout=30):
    """
    Validate GPS device connectivity and NMEA parsing.
    
    Args:
        port: Serial device path (e.g., /dev/ttyUSB0)
        baudrate: Baud rate (default 9600 for NMEA)
        timeout: Maximum seconds to wait for GPS fix
    
    Returns:
        Dictionary with validation results, or None on failure.
    """
    import serial
    import pynmea2
    
    logger.info(f"Opening {port} at {baudrate} baud...")
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=1.0,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
    except (serial.SerialException, OSError) as e:
        logger.error(f"Cannot open {port}: {e}")
        return None
    
    logger.info(f"Serial port opened: {ser.name}")
    logger.info("Waiting for NMEA sentences...")
    
    stats = {
        'port': port,
        'baudrate': baudrate,
        'total_lines': 0,
        'valid_nmea': 0,
        'parse_errors': 0,
        'sentence_types': {},
        'has_fix': False,
        'fix_quality': 0,
        'latitude': None,
        'longitude': None,
        'altitude_msl': None,
        'satellites': 0,
        'hdop': None,
        'groundspeed_kmh': None,
        'track_degrees': None,
    }
    
    start_time = time.time()
    first_valid = False
    
    try:
        while (time.time() - start_time) < timeout:
            try:
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if not line:
                    continue
                
                stats['total_lines'] += 1
                
                if not line.startswith('$'):
                    continue
                
                # Try parsing as NMEA
                try:
                    msg = pynmea2.parse(line)
                    stats['valid_nmea'] += 1
                    
                    # Track sentence types
                    msg_type = msg.sentence_type
                    stats['sentence_types'][msg_type] = stats['sentence_types'].get(msg_type, 0) + 1
                    
                    if not first_valid:
                        logger.info(f"✓ First valid NMEA sentence received: {msg_type}")
                        first_valid = True
                    
                    # Extract GGA (position/fix) data
                    if msg_type == 'GGA':
                        if hasattr(msg, 'gps_qual') and msg.gps_qual:
                            stats['fix_quality'] = int(msg.gps_qual)
                            stats['has_fix'] = stats['fix_quality'] > 0
                        
                        if hasattr(msg, 'latitude') and msg.latitude:
                            stats['latitude'] = msg.latitude
                        if hasattr(msg, 'longitude') and msg.longitude:
                            stats['longitude'] = msg.longitude
                        if hasattr(msg, 'altitude') and msg.altitude:
                            stats['altitude_msl'] = float(msg.altitude)
                        if hasattr(msg, 'num_sats') and msg.num_sats:
                            stats['satellites'] = int(msg.num_sats)
                        if hasattr(msg, 'horizontal_dil') and msg.horizontal_dil:
                            stats['hdop'] = float(msg.horizontal_dil)
                        
                        if stats['has_fix']:
                            logger.info(f"✓ GPS fix acquired: quality={stats['fix_quality']}, sats={stats['satellites']}")
                            logger.info(f"  Position: {stats['latitude']:.6f}°, {stats['longitude']:.6f}°")
                            if stats['altitude_msl']:
                                logger.info(f"  Altitude: {stats['altitude_msl']:.1f}m MSL")
                            break  # Success!
                    
                    # Extract VTG (speed/track) data
                    if msg_type == 'VTG':
                        if hasattr(msg, 'spd_over_grnd_kmph') and msg.spd_over_grnd_kmph:
                            stats['groundspeed_kmh'] = float(msg.spd_over_grnd_kmph)
                        if hasattr(msg, 'true_track') and msg.true_track:
                            stats['track_degrees'] = float(msg.true_track)
                    
                    # Extract RMC (combined) data
                    if msg_type == 'RMC':
                        if hasattr(msg, 'status') and msg.status == 'A':
                            stats['has_fix'] = True
                            if hasattr(msg, 'latitude') and msg.latitude:
                                stats['latitude'] = msg.latitude
                            if hasattr(msg, 'longitude') and msg.longitude:
                                stats['longitude'] = msg.longitude
                            if hasattr(msg, 'spd_over_grnd') and msg.spd_over_grnd:
                                stats['groundspeed_kmh'] = float(msg.spd_over_grnd) * 1.852  # knots to km/h
                            if hasattr(msg, 'true_course') and msg.true_course:
                                stats['track_degrees'] = float(msg.true_course)
                
                except pynmea2.ParseError as e:
                    stats['parse_errors'] += 1
                    if stats['parse_errors'] <= 3:
                        logger.warning(f"Parse error: {e} (line: {line[:50]}...)")
            
            except UnicodeDecodeError:
                continue
        
    finally:
        ser.close()
        logger.info(f"Serial port closed")
    
    elapsed = time.time() - start_time
    logger.info(f"\nValidation completed in {elapsed:.1f}s")
    logger.info(f"Total lines read: {stats['total_lines']}")
    logger.info(f"Valid NMEA sentences: {stats['valid_nmea']}")
    logger.info(f"Parse errors: {stats['parse_errors']}")
    
    if stats['sentence_types']:
        logger.info("Sentence types received:")
        for stype, count in sorted(stats['sentence_types'].items()):
            logger.info(f"  {stype}: {count}")
    
    return stats


def print_summary(stats):
    """Print validation summary and recommendations."""
    print("\n" + "="*60)
    print("GPS DEVICE VALIDATION SUMMARY")
    print("="*60)
    
    if not stats:
        print("❌ FAILED: Could not communicate with device")
        return False
    
    print(f"\nDevice: {stats['port']} @ {stats['baudrate']} baud")
    print(f"NMEA sentences: {stats['valid_nmea']} valid, {stats['parse_errors']} errors")
    
    if stats['valid_nmea'] == 0:
        print("\n❌ FAILED: No valid NMEA data received")
        print("\nTroubleshooting:")
        print("  1. Verify the GPS module is powered on")
        print("  2. Check if another process has the port open (e.g., gpsd)")
        print("  3. Try a different baud rate (common: 4800, 9600, 38400, 115200)")
        print("  4. Verify UART/USB cable connections")
        return False
    
    print(f"\n✓ NMEA communication established")
    
    if stats['has_fix']:
        print(f"✓ GPS fix acquired (quality: {stats['fix_quality']})")
        print(f"  Position: {stats['latitude']:.6f}°, {stats['longitude']:.6f}°")
        if stats['altitude_msl']:
            print(f"  Altitude: {stats['altitude_msl']:.1f}m MSL")
        print(f"  Satellites: {stats['satellites']}")
        if stats['hdop']:
            print(f"  HDOP: {stats['hdop']:.1f}")
        if stats['groundspeed_kmh'] is not None:
            print(f"  Speed: {stats['groundspeed_kmh']:.1f} km/h")
        if stats['track_degrees'] is not None:
            print(f"  Track: {stats['track_degrees']:.1f}°")
        
        print("\n✅ SUCCESS: GPS device validated and ready for use")
        print("\nTo use with cymbal GPSSensor:")
        print(f"  sensor = GPSSensor()")
        print(f"  sensor.initialize('{stats['port']}', {stats['baudrate']})")
        return True
    else:
        print(f"\n⚠ WARNING: No GPS fix acquired (yet)")
        print("\nPossible reasons:")
        print("  1. GPS receiver needs more time (try moving outdoors)")
        print("  2. Obstructed view of sky (GPS requires line-of-sight to satellites)")
        print("  3. Cold start can take 30-60 seconds (or longer indoors)")
        print("\nNMEA communication is working, so the device should work once it gets a fix.")
        print(f"\nTo use with cymbal GPSSensor:")
        print(f"  sensor = GPSSensor()")
        print(f"  sensor.initialize('{stats['port']}', {stats['baudrate']})")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Validate GPS device connectivity and NMEA parsing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Auto-detect GPS device
  %(prog)s /dev/ttyUSB0              # Test specific device
  %(prog)s /dev/ttyUSB0 38400        # Custom baud rate
  %(prog)s /dev/ttyUSB0 9600 --timeout 60  # Wait longer for fix
        """
    )
    parser.add_argument('port', nargs='?', help='Serial device path (e.g., /dev/ttyUSB0)')
    parser.add_argument('baudrate', type=int, nargs='?', default=9600,
                        help='Baud rate (default: 9600)')
    parser.add_argument('--timeout', type=int, default=30,
                        help='Max seconds to wait for GPS fix (default: 30)')
    parser.add_argument('--list', action='store_true',
                        help='List potential GPS devices and exit')
    
    args = parser.parse_args()
    
    # Check dependencies first
    if not check_dependencies():
        return 1
    
    # List devices if requested
    if args.list:
        devices = find_gps_devices()
        if devices:
            print("Potential GPS devices found:")
            for dev in devices:
                print(f"  {dev}")
        else:
            print("No GPS devices detected")
            print("Try connecting a USB GPS receiver or check /dev/tty* manually")
        return 0
    
    # Determine which port to test
    port = args.port
    if not port:
        devices = find_gps_devices()
        if not devices:
            logger.error("No GPS devices auto-detected")
            logger.error("Specify a device path manually, e.g.: /dev/ttyUSB0")
            logger.error("Or list available devices: --list")
            return 2
        
        logger.info(f"Found {len(devices)} potential GPS device(s)")
        port = devices[0]
        if len(devices) > 1:
            logger.info(f"Multiple devices found, using first: {port}")
            logger.info(f"Other devices: {', '.join(devices[1:])}")
    
    # Validate the device
    stats = validate_gps_device(port, args.baudrate, args.timeout)
    
    # Print summary
    success = print_summary(stats)
    
    if not stats:
        return 2
    elif stats['valid_nmea'] == 0:
        return 3
    elif not success:
        return 4
    else:
        return 0


if __name__ == '__main__':
    sys.exit(main())
