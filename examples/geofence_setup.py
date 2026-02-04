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

Usage:
    python3 geofence_setup.py [options]

Example:
    python3 geofence_setup.py --radius 100 --max-altitude 50
"""

import argparse
import asyncio
import os
import sys

from mavsdk import System
from mavsdk.geofence import Point, Polygon


async def run(
    radius: float = 100.0,
    max_altitude: float = 50.0,
    host: str = "localhost",
    port: int = 14540
):
    """
    Configure geofence around current position.

    Args:
        radius: Geofence radius in meters.
        max_altitude: Maximum altitude in meters.
        host: MAVLink server host.
        port: MAVLink server port.

    Returns:
        bool: True if successful, False otherwise.
    """
    drone = System()

    print(f"Connecting to drone at {host}:{port}...")
    await drone.connect(system_address=f"udp://{host}:{port}")

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
    import math

    num_points = 8
    points = []

    # Convert radius to approximate degrees (at equator, 1 degree ≈ 111km)
    radius_deg = radius / 111000.0

    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        lat = current_lat + radius_deg * math.cos(angle)
        lon = current_lon + radius_deg * math.sin(angle) / math.cos(math.radians(current_lat))
        points.append(Point(lat, lon))

    # Create polygon (inclusive fence - stay inside)
    polygon = Polygon(points, Polygon.FenceType.INCLUSION)

    print(f"-- Creating geofence:")
    print(f"   Center: {current_lat:.6f}, {current_lon:.6f}")
    print(f"   Radius: {radius}m")
    print(f"   Max altitude: {max_altitude}m")
    print(f"   Points: {num_points}")

    # Upload geofence
    print("-- Uploading geofence...")
    await drone.geofence.upload_geofence([polygon])
    print("-- Geofence uploaded!")

    # Clear geofence (optional - uncomment to clear)
    # print("-- Clearing geofence...")
    # await drone.geofence.clear_geofence()
    # print("-- Geofence cleared!")

    print("-- Geofence configuration complete!")
    print("\nNote: The geofence is now active. The drone will:")
    print("  - Stay within the defined polygon boundary")
    print("  - Respect altitude limits set in PX4 parameters")
    print("\nTo clear the geofence, run with --clear flag")

    return True


async def clear_geofence(host: str = "localhost", port: int = 14540):
    """
    Clear all geofence data.

    Args:
        host: MAVLink server host.
        port: MAVLink server port.

    Returns:
        bool: True if successful, False otherwise.
    """
    drone = System()

    print(f"Connecting to drone at {host}:{port}...")
    await drone.connect(system_address=f"udp://{host}:{port}")

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
        help="Geofence radius in meters (default: 100)"
    )
    parser.add_argument(
        "--max-altitude",
        type=float,
        default=50.0,
        help="Maximum altitude in meters (default: 50)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing geofence instead of creating new one"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MAVLINK_HOST", "localhost"),
        help="MAVLink host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MAVLINK_PORT", "14540")),
        help="MAVLink port (default: 14540)"
    )

    args = parser.parse_args()

    # Run the async function
    if args.clear:
        success = asyncio.get_event_loop().run_until_complete(
            clear_geofence(host=args.host, port=args.port)
        )
    else:
        success = asyncio.get_event_loop().run_until_complete(
            run(
                radius=args.radius,
                max_altitude=args.max_altitude,
                host=args.host,
                port=args.port
            )
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

