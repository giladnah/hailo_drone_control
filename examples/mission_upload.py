#!/usr/bin/env python3
"""
mission_upload.py - Mission Upload and Execute Example

Demonstrates how to create, upload, and execute a waypoint mission:
1. Connect to the drone
2. Create a mission with multiple waypoints
3. Upload the mission
4. Start the mission
5. Monitor progress
6. Land after completion

This example follows official MAVSDK-Python patterns from:
https://github.com/mavlink/MAVSDK-Python/tree/main/examples

Supports both WiFi (UDP) and UART (serial) connections for Raspberry Pi.

Usage:
    # WiFi mode (default - for SITL testing)
    python3 mission_upload.py --altitude 20

    # UART mode (for production with Cube+ Orange)
    python3 mission_upload.py -c uart --altitude 20

Example:
    python3 mission_upload.py --altitude 20 --tcp-host 192.168.1.100
    python3 mission_upload.py -c uart --uart-device /dev/ttyAMA0
"""

import argparse
import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from mavsdk.mission import MissionItem, MissionPlan
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)


async def run(connection_string: str, altitude: float = 10.0):
    """
    Execute mission upload and flight sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Mission altitude in meters.

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

    # Get current position for relative waypoints
    print("Getting current position...")
    current_lat = 0.0
    current_lon = 0.0
    async for position in drone.telemetry.position():
        current_lat = position.latitude_deg
        current_lon = position.longitude_deg
        print(f"-- Current position: {current_lat:.6f}, {current_lon:.6f}")
        break

    # Create mission items (square pattern around current position)
    # Offset in degrees (approximately 50m at equator)
    offset = 0.0005

    mission_items = [
        # Waypoint 1: North
        MissionItem(
            latitude_deg=current_lat + offset,
            longitude_deg=current_lon,
            relative_altitude_m=altitude,
            speed_m_s=5.0,
            is_fly_through=True,
            gimbal_pitch_deg=0.0,
            gimbal_yaw_deg=0.0,
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=0.0,
            camera_photo_interval_s=0.0,
            acceptance_radius_m=1.0,
            yaw_deg=0.0,
            camera_photo_distance_m=0.0,
        ),
        # Waypoint 2: Northeast
        MissionItem(
            latitude_deg=current_lat + offset,
            longitude_deg=current_lon + offset,
            relative_altitude_m=altitude,
            speed_m_s=5.0,
            is_fly_through=True,
            gimbal_pitch_deg=0.0,
            gimbal_yaw_deg=0.0,
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=0.0,
            camera_photo_interval_s=0.0,
            acceptance_radius_m=1.0,
            yaw_deg=90.0,
            camera_photo_distance_m=0.0,
        ),
        # Waypoint 3: East
        MissionItem(
            latitude_deg=current_lat,
            longitude_deg=current_lon + offset,
            relative_altitude_m=altitude,
            speed_m_s=5.0,
            is_fly_through=True,
            gimbal_pitch_deg=0.0,
            gimbal_yaw_deg=0.0,
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=0.0,
            camera_photo_interval_s=0.0,
            acceptance_radius_m=1.0,
            yaw_deg=180.0,
            camera_photo_distance_m=0.0,
        ),
        # Waypoint 4: Return to start
        MissionItem(
            latitude_deg=current_lat,
            longitude_deg=current_lon,
            relative_altitude_m=altitude,
            speed_m_s=5.0,
            is_fly_through=False,  # Stop at final waypoint
            gimbal_pitch_deg=0.0,
            gimbal_yaw_deg=0.0,
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=2.0,  # Loiter for 2 seconds
            camera_photo_interval_s=0.0,
            acceptance_radius_m=1.0,
            yaw_deg=0.0,
            camera_photo_distance_m=0.0,
        ),
    ]

    # Create mission plan
    mission_plan = MissionPlan(mission_items)

    # Upload mission
    print("-- Uploading mission...")
    await drone.mission.upload_mission(mission_plan)
    print("-- Mission uploaded!")

    # Arm the drone
    print("-- Arming")
    await drone.action.arm()

    # Start mission
    print("-- Starting mission")
    await drone.mission.start_mission()

    # Monitor mission progress
    print("-- Monitoring mission progress...")
    async for mission_progress in drone.mission.mission_progress():
        print(f"   Mission progress: {mission_progress.current}/{mission_progress.total}")
        if mission_progress.current == mission_progress.total:
            print("-- Mission complete!")
            break

    # Wait a moment
    await asyncio.sleep(2)

    # Land
    print("-- Landing")
    await drone.action.land()

    # Wait until landed
    print("-- Waiting for landing...")
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("-- Landed!")
            break

    print("-- Mission execution complete!")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mission upload and execute example using MAVSDK"
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=10.0,
        help="Mission altitude in meters (default: 10.0)"
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
    success = asyncio.get_event_loop().run_until_complete(
        run(connection_string=connection_string, altitude=args.altitude)
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
