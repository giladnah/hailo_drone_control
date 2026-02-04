#!/usr/bin/env python3
"""
simple_takeoff_land.py - Basic Takeoff and Land Example

A minimal example demonstrating the core MAVSDK workflow:
1. Connect to the drone
2. Wait for GPS lock
3. Arm and takeoff
4. Hover briefly
5. Land safely

This example follows official MAVSDK-Python patterns from:
https://github.com/mavlink/MAVSDK-Python/tree/main/examples

Supports both WiFi (UDP) and UART (serial) connections for Raspberry Pi.

Usage:
    # WiFi mode (default - for SITL testing)
    python3 simple_takeoff_land.py --altitude 10

    # UART mode (for production with Cube+ Orange)
    python3 simple_takeoff_land.py -c uart --altitude 10

Example:
    python3 simple_takeoff_land.py --altitude 10 --wifi-host 192.168.1.100
    python3 simple_takeoff_land.py -c uart --uart-device /dev/ttyAMA0
"""

import argparse
import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from mavsdk.action import ActionError
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)


async def run(connection_string: str, altitude: float = 5.0):
    """
    Execute simple takeoff and land sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Target altitude in meters.

    Returns:
        bool: True if successful, False otherwise.
    """
    drone = System()

    print(f"Connecting to drone: {connection_string}")
    await drone.connect(system_address=connection_string)

    # Wait for connection
    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("-- Connected to drone!")
            break

    # Wait for GPS fix
    print("Waiting for drone to have a global position estimate...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("-- Global position estimate OK")
            break

    # Arm the drone
    print("-- Arming")
    try:
        await drone.action.arm()
    except ActionError as e:
        print(f"Arming failed: {e}")
        return False

    # Set takeoff altitude
    print(f"-- Setting takeoff altitude to {altitude}m")
    await drone.action.set_takeoff_altitude(altitude)

    # Take off
    print("-- Taking off")
    try:
        await drone.action.takeoff()
    except ActionError as e:
        print(f"Takeoff failed: {e}")
        return False

    # Wait until altitude reached
    print(f"-- Waiting to reach {altitude}m...")
    async for position in drone.telemetry.position():
        if position.relative_altitude_m >= altitude * 0.95:
            print(f"-- Reached altitude: {position.relative_altitude_m:.1f}m")
            break

    # Hover for 5 seconds
    print("-- Hovering for 5 seconds...")
    await asyncio.sleep(5)

    # Land
    print("-- Landing")
    try:
        await drone.action.land()
    except ActionError as e:
        print(f"Landing failed: {e}")
        return False

    # Wait until landed
    print("-- Waiting for landing...")
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("-- Landed!")
            break

    print("-- Mission complete!")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Simple takeoff and land example using MAVSDK"
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=5.0,
        help="Takeoff altitude in meters (default: 5.0)"
    )

    # Add connection arguments (--connection-type, --uart-*, --wifi-*)
    add_connection_arguments(parser)

    args = parser.parse_args()

    # Build connection config from arguments
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

    # Get connection string
    connection_string = config.get_connection_string()

    # Run the async function
    success = asyncio.get_event_loop().run_until_complete(
        run(connection_string=connection_string, altitude=args.altitude)
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
