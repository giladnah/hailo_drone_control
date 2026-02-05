#!/usr/bin/env python3
"""
geofence_setup.py - Geofence Configuration Example

Demonstrates how to configure geofence parameters:
1. Connect to the drone
2. Create a circular geofence around current position
3. Upload the geofence
4. Monitor geofence status

This example follows official MAVSDK-Python patterns from:
https://github.com/mavlink/MAVSDK-Python/tree/main/examples

Supports TCP (default), UDP, and UART (serial) connections.

Usage:
    # TCP mode (default - recommended for SITL testing)
    python3 geofence_setup.py --radius 100 --max-altitude 50

    # UART mode (for production with Cube+ Orange)
    python3 geofence_setup.py -c uart --radius 100

Example:
    python3 geofence_setup.py --tcp-host px4-sitl --radius 100
    python3 geofence_setup.py -c uart --clear
"""

import argparse
import asyncio
import math
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from mavsdk.geofence import Point, Polygon
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)


async def run(connection_string: str, radius: float = 100.0, max_altitude: float = 50.0):
    """
    Configure geofence around current position.

    Args:
        connection_string: MAVSDK connection string.
        radius: Geofence radius in meters.
        max_altitude: Maximum altitude in meters.

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
    print("Waiting for global position estimate...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("-- Global position estimate OK")
            break

    # Get current position
    print("Getting current position...")
    current_lat = 0.0
    current_lon = 0.0
    async for position in drone.telemetry.position():
        current_lat = position.latitude_deg
        current_lon = position.longitude_deg
        print(f"-- Current position: {current_lat:.6f}, {current_lon:.6f}")
        break

    # Create geofence polygon (circular approximation with 8 points)
    num_points = 8
    points = []

    # Convert radius to approximate degrees (at equator, 1 degree ≈ 111km)
    radius_deg = radius / 111000.0

    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        lat = current_lat + radius_deg * math.cos(angle)
        lon = current_lon + radius_deg * math.sin(angle) / math.cos(
            math.radians(current_lat)
        )
        points.append(Point(lat, lon))

    # Create polygon (inclusive fence - stay inside)
    polygon = Polygon(points, Polygon.FenceType.INCLUSION)

    print("-- Creating geofence:")
    print(f"   Center: {current_lat:.6f}, {current_lon:.6f}")
    print(f"   Radius: {radius}m")
    print(f"   Max altitude: {max_altitude}m")
    print(f"   Points: {num_points}")

    # Upload geofence
    print("-- Uploading geofence...")
    await drone.geofence.upload_geofence([polygon])
    print("-- Geofence uploaded!")

    print("-- Geofence configuration complete!")
    print("\nNote: The geofence is now active. The drone will:")
    print("  - Stay within the defined polygon boundary")
    print("  - Respect altitude limits set in PX4 parameters")
    print("\nTo clear the geofence, run with --clear flag")

    return True


async def clear_geofence(connection_string: str):
    """
    Clear all geofence data.

    Args:
        connection_string: MAVSDK connection string.

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

    print("-- Clearing geofence...")
    await drone.geofence.clear_geofence()
    print("-- Geofence cleared!")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Geofence configuration example using MAVSDK"
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=100.0,
        help="Geofence radius in meters (default: 100)",
    )
    parser.add_argument(
        "--max-altitude",
        type=float,
        default=50.0,
        help="Maximum altitude in meters (default: 50)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing geofence instead of creating new one",
    )

    # Add connection arguments (--connection-type, --uart-*, --udp-*, --tcp-*)
    add_connection_arguments(parser)

    args = parser.parse_args()

    # Build connection config from arguments
    config = ConnectionConfig.from_args(
        connection_type=args.connection_type,
        uart_device=args.uart_device,
        uart_baud=args.uart_baud,
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
    )

    # Print connection info
    print_connection_info(config)

    # Get connection string
    connection_string = config.get_connection_string()

    # Run the async function
    if args.clear:
        success = asyncio.get_event_loop().run_until_complete(
            clear_geofence(connection_string=connection_string)
        )
    else:
        success = asyncio.get_event_loop().run_until_complete(
            run(
                connection_string=connection_string,
                radius=args.radius,
                max_altitude=args.max_altitude,
            )
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
