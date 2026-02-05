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

Supports TCP (default), UDP, and UART (serial) connections.

Usage:
    # TCP mode (default - recommended for SITL testing)
    python3 simple_takeoff_land.py --altitude 10

    # UART mode (for production with Cube+ Orange)
    python3 simple_takeoff_land.py -c uart --altitude 10

Example:
    python3 simple_takeoff_land.py --altitude 10 --tcp-host 192.168.1.100
    python3 simple_takeoff_land.py -c uart --uart-device /dev/ttyAMA0
"""

import argparse
import asyncio
import signal
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from mavsdk.action import ActionError
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)

# Global variable to track if landing was requested
landing_requested = False
drone_instance = None


async def safe_land(drone: System) -> bool:
    """
    Safely land the drone.

    Args:
        drone: Connected MAVSDK System instance.

    Returns:
        bool: True if landing was successful, False otherwise.
    """
    print("\n-- Initiating emergency landing...")
    try:
        await drone.action.land()
        print("-- Landing command sent, waiting for touchdown...")

        # Wait for landing with timeout
        start_time = time.time()
        timeout = 30.0
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                print("-- Landed safely!")
                return True
            if time.time() - start_time > timeout:
                print(f"WARNING: Landing timeout after {timeout}s, but landing command was sent")
                return False
    except Exception as e:
        print(f"ERROR during landing: {e}")
        return False


async def run(connection_string: str, altitude: float = 5.0):
    """
    Execute simple takeoff and land sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Target altitude in meters.

    Returns:
        bool: True if successful, False otherwise.
    """
    global drone_instance
    drone = System()
    drone_instance = drone

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
    start_time = time.time()
    timeout_seconds = 60.0  # 60 second timeout
    last_print_time = 0
    # Use 80% tolerance for SITL variability (as per test patterns)
    altitude_threshold = altitude * 0.80
    max_altitude_seen = 0.0
    altitude_stable_count = 0
    last_altitude = 0.0

    async for position in drone.telemetry.position():
        current_time = time.time()
        elapsed = current_time - start_time
        current_alt = position.relative_altitude_m

        # Track maximum altitude reached
        if current_alt > max_altitude_seen:
            max_altitude_seen = current_alt
            altitude_stable_count = 0  # Reset stability counter on new max
        else:
            # Check if altitude has stabilized (not increasing)
            if abs(current_alt - last_altitude) < 0.1:  # Within 0.1m
                altitude_stable_count += 1
            else:
                altitude_stable_count = 0

        last_altitude = current_alt

        # Print altitude every 2 seconds for debugging
        if current_time - last_print_time >= 2.0:
            print(f"  Current altitude: {current_alt:.2f}m (target: {altitude}m, threshold: {altitude_threshold:.2f}m, elapsed: {elapsed:.1f}s)")
            last_print_time = current_time

        # Check if landing was requested (Ctrl+C)
        if landing_requested:
            print("\n-- Landing requested by user...")
            await safe_land(drone)
            return False

        # Check if altitude reached (with 80% tolerance for SITL variability)
        if current_alt >= altitude_threshold:
            print(f"-- Reached altitude: {current_alt:.1f}m (target: {altitude}m, after {elapsed:.1f}s)")
            break

        # If altitude has stabilized below threshold but above 70%, accept it
        # (drone may have reached its practical max or hit a limit)
        if altitude_stable_count >= 5 and current_alt >= altitude * 0.70:
            print(f"-- Altitude stabilized at {current_alt:.1f}m (target: {altitude}m)")
            print(f"  Accepting stabilized altitude (reached {current_alt/altitude*100:.0f}% of target)")
            break

        # Check timeout - land safely before returning
        if elapsed > timeout_seconds:
            print(f"\nWARNING: Timeout waiting for altitude after {timeout_seconds}s")
            print(f"  Final altitude: {current_alt:.2f}m (max seen: {max_altitude_seen:.2f}m)")
            print(f"  Target was {altitude}m, reached {current_alt/altitude*100:.0f}%")
            # If we got reasonably close (70%+), continue anyway
            if current_alt >= altitude * 0.70:
                print(f"  Altitude is acceptable ({current_alt/altitude*100:.0f}%), continuing...")
                break
            else:
                await safe_land(drone)
                return False

    # Hover for 5 seconds (with interrupt check)
    print("-- Hovering for 5 seconds...")
    hover_start = time.time()
    while time.time() - hover_start < 5.0:
        if landing_requested:
            print("\n-- Landing requested by user during hover...")
            await safe_land(drone)
            return False
        await asyncio.sleep(0.5)

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


def signal_handler(signum, frame):
    """Handle Ctrl+C to safely land the drone."""
    global landing_requested
    print("\n\n-- Interrupt received (Ctrl+C)")
    landing_requested = True


def main():
    """Main entry point."""
    global landing_requested

    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
        description="Simple takeoff and land example using MAVSDK"
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=5.0,
        help="Takeoff altitude in meters (default: 5.0)"
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
    try:
        success = asyncio.run(
            run(connection_string=connection_string, altitude=args.altitude)
        )
    except KeyboardInterrupt:
        print("\n-- Interrupted by user")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
