#!/usr/bin/env python3
"""
offboard_velocity.py - Offboard Velocity Control Example

Demonstrates offboard control using velocity setpoints:
1. Connect to the drone
2. Arm and takeoff
3. Enter offboard mode
4. Execute velocity commands (fly a square pattern)
5. Exit offboard mode and land

This example follows official MAVSDK-Python patterns from:
https://github.com/mavlink/MAVSDK-Python/tree/main/examples

Supports both WiFi (UDP) and UART (serial) connections for Raspberry Pi.

Usage:
    # WiFi mode (default - for SITL testing)
    python3 offboard_velocity.py --altitude 10 --speed 2.0

    # UART mode (for production with Cube+ Orange)
    python3 offboard_velocity.py -c uart --altitude 10

Example:
    python3 offboard_velocity.py --altitude 10 --wifi-host 192.168.1.100
    python3 offboard_velocity.py -c uart --uart-device /dev/ttyAMA0
"""

import argparse
import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityNedYaw
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)


async def run(
    connection_string: str,
    altitude: float = 10.0,
    speed: float = 2.0,
):
    """
    Execute offboard velocity control sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Takeoff altitude in meters.
        speed: Flight speed in m/s.

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

    # Arm the drone
    print("-- Arming")
    await drone.action.arm()

    # Set takeoff altitude and take off
    print(f"-- Taking off to {altitude}m")
    await drone.action.set_takeoff_altitude(altitude)
    await drone.action.takeoff()

    # Wait until altitude reached
    print(f"-- Waiting to reach {altitude}m...")
    async for position in drone.telemetry.position():
        if position.relative_altitude_m >= altitude * 0.95:
            print(f"-- Reached altitude: {position.relative_altitude_m:.1f}m")
            break

    # Stabilize
    print("-- Stabilizing...")
    await asyncio.sleep(3)

    # Get current heading for reference
    current_yaw = 0.0
    async for attitude in drone.telemetry.attitude_euler():
        current_yaw = attitude.yaw_deg
        print(f"-- Current heading: {current_yaw:.1f}")
        break

    # Start offboard mode
    print("-- Setting initial setpoint")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, current_yaw))

    print("-- Starting offboard mode")
    try:
        await drone.offboard.start()
    except OffboardError as e:
        print(f"Starting offboard mode failed: {e}")
        print("-- Landing")
        await drone.action.land()
        return False

    # Fly a square pattern using velocity commands
    # Duration for each leg (seconds)
    leg_duration = 5.0

    print(f"-- Flying square pattern at {speed} m/s")

    # Leg 1: North (positive X in NED)
    print("   Leg 1: Flying North...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(speed, 0.0, 0.0, current_yaw))
    await asyncio.sleep(leg_duration)

    # Leg 2: East (positive Y in NED)
    print("   Leg 2: Flying East...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, speed, 0.0, current_yaw))
    await asyncio.sleep(leg_duration)

    # Leg 3: South (negative X in NED)
    print("   Leg 3: Flying South...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(-speed, 0.0, 0.0, current_yaw))
    await asyncio.sleep(leg_duration)

    # Leg 4: West (negative Y in NED)
    print("   Leg 4: Flying West...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, -speed, 0.0, current_yaw))
    await asyncio.sleep(leg_duration)

    # Stop and hover
    print("-- Stopping (hover)")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, current_yaw))
    await asyncio.sleep(2)

    # Stop offboard mode
    print("-- Stopping offboard mode")
    try:
        await drone.offboard.stop()
    except OffboardError as e:
        print(f"Stopping offboard mode failed: {e}")

    # Land
    print("-- Landing")
    await drone.action.land()

    # Wait until landed
    print("-- Waiting for landing...")
    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("-- Landed!")
            break

    print("-- Offboard velocity demo complete!")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Offboard velocity control example using MAVSDK"
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=10.0,
        help="Takeoff altitude in meters (default: 10.0)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=2.0,
        help="Flight speed in m/s (default: 2.0)"
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
    )

    # Print connection info
    print_connection_info(config)

    # Get connection string
    connection_string = config.get_connection_string()

    # Run the async function
    success = asyncio.get_event_loop().run_until_complete(
        run(
            connection_string=connection_string,
            altitude=args.altitude,
            speed=args.speed,
        )
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
