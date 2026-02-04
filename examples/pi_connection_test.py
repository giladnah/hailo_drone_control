#!/usr/bin/env python3
"""
pi_connection_test.py - Comprehensive MAVLink Connection Test for Raspberry Pi

Tests MAVLink connectivity via UART or WiFi and displays diagnostic information.
Designed to verify the Raspberry Pi can communicate with PX4 autopilots.

Features:
- Tests both UART and WiFi connections
- Verifies heartbeat reception
- Displays basic telemetry
- Checks bidirectional communication
- Provides connection diagnostics

Usage:
    # WiFi mode (testing with SITL)
    python3 pi_connection_test.py -c wifi --wifi-host 192.168.1.100

    # UART mode (production with Cube+ Orange)
    python3 pi_connection_test.py -c uart

    # Full diagnostic mode
    python3 pi_connection_test.py -c uart --full-diagnostic

Example:
    python3 pi_connection_test.py -c wifi --wifi-host 192.168.1.100 --timeout 60
    python3 pi_connection_test.py -c uart --uart-device /dev/ttyAMA0
"""

import argparse
import asyncio
import sys
import time
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from scripts.mavlink_connection import (
    ConnectionConfig,
    ConnectionType,
    add_connection_arguments,
    check_serial_port,
    detect_serial_ports,
    print_connection_info,
    validate_config,
)


async def test_connection(
    connection_string: str,
    timeout: float = 30.0,
    full_diagnostic: bool = False,
) -> dict:
    """
    Test MAVLink connection and gather diagnostic information.

    Args:
        connection_string: MAVSDK connection string.
        timeout: Connection timeout in seconds.
        full_diagnostic: Run extended diagnostic tests.

    Returns:
        dict: Test results with connection status and telemetry.
    """
    try:
        from mavsdk import System
    except ImportError:
        return {
            "success": False,
            "error": "MAVSDK not installed. Run: pip install mavsdk",
        }

    results = {
        "success": False,
        "connection_string": connection_string,
        "connected": False,
        "heartbeat_received": False,
        "telemetry": {},
        "errors": [],
        "warnings": [],
        "timing": {},
    }

    start_time = time.time()
    print(f"\nConnecting to: {connection_string}")
    print(f"Timeout: {timeout}s")
    print("-" * 50)

    drone = System()

    try:
        # Connect
        connect_start = time.time()
        await drone.connect(system_address=connection_string)

        # Wait for heartbeat
        print("Waiting for heartbeat...")
        connected = False

        async for state in drone.core.connection_state():
            elapsed = time.time() - connect_start
            if state.is_connected:
                connected = True
                results["connected"] = True
                results["heartbeat_received"] = True
                results["timing"]["connection_time"] = elapsed
                print(f"  Heartbeat received after {elapsed:.1f}s")
                break

            if elapsed > timeout:
                results["errors"].append(f"Connection timeout after {timeout}s")
                print(f"  Timeout after {timeout}s")
                break

            if int(elapsed) % 5 == 0 and elapsed > 0:
                print(f"  Waiting... ({int(elapsed)}s)")

            await asyncio.sleep(0.5)

        if not connected:
            results["success"] = False
            return results

        # Gather telemetry
        print("\nGathering telemetry...")
        telemetry_start = time.time()

        # Armed status
        try:
            async for armed in drone.telemetry.armed():
                results["telemetry"]["armed"] = armed
                print(f"  Armed: {armed}")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get armed status: {e}")

        # In air status
        try:
            async for in_air in drone.telemetry.in_air():
                results["telemetry"]["in_air"] = in_air
                print(f"  In Air: {in_air}")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get in_air status: {e}")

        # Position
        try:
            async for position in drone.telemetry.position():
                results["telemetry"]["position"] = {
                    "latitude": position.latitude_deg,
                    "longitude": position.longitude_deg,
                    "altitude": position.relative_altitude_m,
                }
                print(f"  Position: {position.latitude_deg:.6f}, {position.longitude_deg:.6f}")
                print(f"  Altitude: {position.relative_altitude_m:.1f}m (relative)")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get position: {e}")

        # Battery
        try:
            async for battery in drone.telemetry.battery():
                results["telemetry"]["battery"] = {
                    "voltage": battery.voltage_v,
                    "remaining": battery.remaining_percent,
                }
                print(f"  Battery: {battery.remaining_percent * 100:.0f}% ({battery.voltage_v:.1f}V)")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get battery: {e}")

        # Flight mode
        try:
            async for mode in drone.telemetry.flight_mode():
                results["telemetry"]["flight_mode"] = str(mode)
                print(f"  Flight Mode: {mode}")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get flight mode: {e}")

        # GPS info
        try:
            async for gps in drone.telemetry.gps_info():
                results["telemetry"]["gps"] = {
                    "num_satellites": gps.num_satellites,
                    "fix_type": str(gps.fix_type),
                }
                print(f"  GPS: {gps.num_satellites} satellites, {gps.fix_type}")
                break
        except Exception as e:
            results["warnings"].append(f"Could not get GPS info: {e}")

        results["timing"]["telemetry_time"] = time.time() - telemetry_start

        # Extended diagnostics
        if full_diagnostic:
            print("\nRunning extended diagnostics...")

            # Health check
            try:
                async for health in drone.telemetry.health():
                    results["telemetry"]["health"] = {
                        "is_gyrometer_calibration_ok": health.is_gyrometer_calibration_ok,
                        "is_accelerometer_calibration_ok": health.is_accelerometer_calibration_ok,
                        "is_magnetometer_calibration_ok": health.is_magnetometer_calibration_ok,
                        "is_local_position_ok": health.is_local_position_ok,
                        "is_global_position_ok": health.is_global_position_ok,
                        "is_home_position_ok": health.is_home_position_ok,
                        "is_armable": health.is_armable,
                    }
                    print(f"  Gyro calibration: {'OK' if health.is_gyrometer_calibration_ok else 'FAIL'}")
                    print(f"  Accel calibration: {'OK' if health.is_accelerometer_calibration_ok else 'FAIL'}")
                    print(f"  Mag calibration: {'OK' if health.is_magnetometer_calibration_ok else 'FAIL'}")
                    print(f"  Local position: {'OK' if health.is_local_position_ok else 'FAIL'}")
                    print(f"  Global position: {'OK' if health.is_global_position_ok else 'FAIL'}")
                    print(f"  Home position: {'OK' if health.is_home_position_ok else 'FAIL'}")
                    print(f"  Armable: {'YES' if health.is_armable else 'NO'}")
                    break
            except Exception as e:
                results["warnings"].append(f"Could not get health: {e}")

            # Attitude
            try:
                async for attitude in drone.telemetry.attitude_euler():
                    results["telemetry"]["attitude"] = {
                        "roll": attitude.roll_deg,
                        "pitch": attitude.pitch_deg,
                        "yaw": attitude.yaw_deg,
                    }
                    print(f"  Attitude: Roll={attitude.roll_deg:.1f}, Pitch={attitude.pitch_deg:.1f}, Yaw={attitude.yaw_deg:.1f}")
                    break
            except Exception as e:
                results["warnings"].append(f"Could not get attitude: {e}")

        results["timing"]["total_time"] = time.time() - start_time
        results["success"] = True

    except Exception as e:
        results["errors"].append(str(e))
        results["success"] = False

    return results


def print_results(results: dict) -> None:
    """Print test results in a formatted manner."""
    print("\n" + "=" * 50)

    if results["success"]:
        print("  CONNECTION TEST: PASSED")
    else:
        print("  CONNECTION TEST: FAILED")

    print("=" * 50)

    print(f"\nConnection: {results['connection_string']}")
    print(f"Connected: {'Yes' if results['connected'] else 'No'}")
    print(f"Heartbeat: {'Received' if results['heartbeat_received'] else 'Not received'}")

    if results.get("timing"):
        print(f"\nTiming:")
        for key, value in results["timing"].items():
            print(f"  {key}: {value:.2f}s")

    if results.get("errors"):
        print(f"\nErrors:")
        for error in results["errors"]:
            print(f"  - {error}")

    if results.get("warnings"):
        print(f"\nWarnings:")
        for warning in results["warnings"]:
            print(f"  - {warning}")

    print("=" * 50)


def run_pre_checks(config: ConnectionConfig) -> bool:
    """Run pre-connection checks."""
    print("\n" + "=" * 50)
    print("  PRE-CONNECTION CHECKS")
    print("=" * 50)

    passed = True

    if config.connection_type == ConnectionType.UART:
        # Check serial port
        print(f"\nChecking serial port: {config.uart_device}")
        port_status = check_serial_port(config.uart_device)

        if port_status["exists"]:
            print(f"  Port exists: YES")
        else:
            print(f"  Port exists: NO")
            passed = False

        if port_status["readable"]:
            print(f"  Readable: YES")
        else:
            print(f"  Readable: NO")
            passed = False

        if port_status["writable"]:
            print(f"  Writable: YES")
        else:
            print(f"  Writable: NO")
            passed = False

        if port_status.get("error"):
            print(f"  Error: {port_status['error']}")

        # List available ports
        print("\nAvailable serial ports:")
        ports = detect_serial_ports()
        if ports:
            for port in ports:
                marker = " <-- configured" if port == config.uart_device else ""
                print(f"  {port}{marker}")
        else:
            print("  None found")

    else:
        # WiFi checks
        print(f"\nWiFi configuration:")
        print(f"  Host: {config.wifi_host}")
        print(f"  Port: {config.wifi_port}")

        # Validate config
        validation = validate_config(config)
        if validation["valid"]:
            print("  Configuration: VALID")
        else:
            print("  Configuration: INVALID")
            for error in validation["errors"]:
                print(f"    - {error}")
            passed = False

    return passed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive MAVLink connection test for Raspberry Pi"
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Connection timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--full-diagnostic",
        action="store_true",
        help="Run extended diagnostic tests"
    )
    parser.add_argument(
        "--skip-pre-checks",
        action="store_true",
        help="Skip pre-connection checks"
    )

    # Add connection arguments
    add_connection_arguments(parser)

    args = parser.parse_args()

    # Build connection config
    config = ConnectionConfig.from_args(
        connection_type=args.connection_type,
        uart_device=args.uart_device,
        uart_baud=args.uart_baud,
        wifi_host=args.wifi_host,
        wifi_port=args.wifi_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
    )

    # Print connection info
    print_connection_info(config)

    # Run pre-checks
    if not args.skip_pre_checks:
        if not run_pre_checks(config):
            print("\nPre-checks failed. Use --skip-pre-checks to bypass.")
            sys.exit(1)

    # Get connection string
    connection_string = config.get_connection_string()

    # Run connection test
    results = asyncio.get_event_loop().run_until_complete(
        test_connection(
            connection_string=connection_string,
            timeout=args.timeout,
            full_diagnostic=args.full_diagnostic,
        )
    )

    # Print results
    print_results(results)

    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)


if __name__ == "__main__":
    main()

