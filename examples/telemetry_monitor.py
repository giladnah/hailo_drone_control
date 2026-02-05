#!/usr/bin/env python3
"""
telemetry_monitor.py - Real-time Telemetry Monitoring Example

Demonstrates how to subscribe to and monitor various telemetry streams:
- Position (GPS)
- Attitude (orientation)
- Battery status
- Flight mode
- Armed state
- GPS info
- Health status

This example follows official MAVSDK-Python patterns from:
https://github.com/mavlink/MAVSDK-Python/tree/main/examples

Supports TCP (default), UDP, and UART (serial) connections.

Usage:
    # TCP mode (default - recommended for SITL testing)
    python3 telemetry_monitor.py --duration 60

    # UART mode (for production with Cube+ Orange)
    python3 telemetry_monitor.py -c uart --duration 60

Example:
    python3 telemetry_monitor.py --tcp-host px4-sitl --duration 30
    python3 telemetry_monitor.py -c uart --simple
"""

import argparse
import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk import System
from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)


async def print_position(drone):
    """Print position telemetry."""
    async for position in drone.telemetry.position():
        print(
            f"Position: lat={position.latitude_deg:.6f}°, "
            f"lon={position.longitude_deg:.6f}°, "
            f"alt={position.relative_altitude_m:.1f}m (rel), "
            f"{position.absolute_altitude_m:.1f}m (abs)"
        )


async def print_attitude(drone):
    """Print attitude telemetry."""
    async for attitude in drone.telemetry.attitude_euler():
        print(
            f"Attitude: roll={attitude.roll_deg:.1f}°, "
            f"pitch={attitude.pitch_deg:.1f}°, "
            f"yaw={attitude.yaw_deg:.1f}°"
        )


async def print_battery(drone):
    """Print battery telemetry."""
    async for battery in drone.telemetry.battery():
        print(
            f"Battery: {battery.remaining_percent * 100:.0f}% "
            f"({battery.voltage_v:.2f}V)"
        )


async def print_flight_mode(drone):
    """Print flight mode changes."""
    async for flight_mode in drone.telemetry.flight_mode():
        print(f"Flight Mode: {flight_mode}")


async def print_armed(drone):
    """Print armed state changes."""
    async for armed in drone.telemetry.armed():
        state = "ARMED" if armed else "DISARMED"
        print(f"Armed State: {state}")


async def print_gps_info(drone):
    """Print GPS info."""
    async for gps_info in drone.telemetry.gps_info():
        print(
            f"GPS: {gps_info.num_satellites} satellites, "
            f"fix type: {gps_info.fix_type}"
        )


async def print_health(drone):
    """Print health status."""
    async for health in drone.telemetry.health():
        print(
            f"Health: "
            f"gyro={health.is_gyrometer_calibration_ok}, "
            f"accel={health.is_accelerometer_calibration_ok}, "
            f"mag={health.is_magnetometer_calibration_ok}, "
            f"gps={health.is_global_position_ok}, "
            f"home={health.is_home_position_ok}"
        )


async def print_velocity(drone):
    """Print velocity telemetry."""
    async for velocity in drone.telemetry.velocity_ned():
        print(
            f"Velocity NED: N={velocity.north_m_s:.2f}m/s, "
            f"E={velocity.east_m_s:.2f}m/s, "
            f"D={velocity.down_m_s:.2f}m/s"
        )


async def run(connection_string: str, duration: float = 30.0, rate: float = 1.0):
    """
    Run telemetry monitoring.

    Args:
        connection_string: MAVSDK connection string.
        duration: Monitoring duration in seconds.
        rate: Update rate in Hz.

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

    # Set telemetry rates
    # Note: Method names vary by MAVSDK version, using try/except for compatibility
    print(f"-- Setting telemetry rate to {rate} Hz")
    try:
        await drone.telemetry.set_rate_position(rate)
        await drone.telemetry.set_rate_attitude_euler(rate)
        await drone.telemetry.set_rate_battery(rate / 2)
        await drone.telemetry.set_rate_gps_info(rate / 2)
        await drone.telemetry.set_rate_velocity_ned(rate)
    except Exception as e:
        print(f"-- Note: Could not set telemetry rates: {e}")
        print("-- Continuing with default rates...")

    print(f"-- Monitoring telemetry for {duration} seconds...")
    print("=" * 60)

    # Create tasks for each telemetry stream
    tasks = [
        asyncio.create_task(print_position(drone)),
        asyncio.create_task(print_attitude(drone)),
        asyncio.create_task(print_battery(drone)),
        asyncio.create_task(print_flight_mode(drone)),
        asyncio.create_task(print_armed(drone)),
        asyncio.create_task(print_gps_info(drone)),
        asyncio.create_task(print_velocity(drone)),
    ]

    # Run for specified duration
    await asyncio.sleep(duration)

    # Cancel all tasks
    for task in tasks:
        task.cancel()

    # Wait for tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    print("=" * 60)
    print("-- Telemetry monitoring complete!")
    return True


async def run_simple(connection_string: str, duration: float = 30.0):
    """
    Run simplified telemetry monitoring (single stream).

    Args:
        connection_string: MAVSDK connection string.
        duration: Monitoring duration in seconds.

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

    print(f"-- Monitoring telemetry for {duration} seconds...")
    print("=" * 80)
    print(f"{'Time':<12} {'Position':<35} {'Attitude':<25} {'Battery':<10}")
    print("=" * 80)

    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= duration:
            break

        # Get current telemetry
        position = None
        attitude = None
        battery = None

        async for pos in drone.telemetry.position():
            position = pos
            break

        async for att in drone.telemetry.attitude_euler():
            attitude = att
            break

        async for bat in drone.telemetry.battery():
            battery = bat
            break

        # Format output
        time_str = f"{elapsed:.1f}s"
        pos_str = (
            f"{position.latitude_deg:.5f}, {position.longitude_deg:.5f}, "
            f"{position.relative_altitude_m:.1f}m"
        ) if position else "N/A"
        att_str = (
            f"R:{attitude.roll_deg:.1f} P:{attitude.pitch_deg:.1f} "
            f"Y:{attitude.yaw_deg:.1f}"
        ) if attitude else "N/A"
        bat_str = f"{battery.remaining_percent * 100:.0f}%" if battery else "N/A"

        print(f"{time_str:<12} {pos_str:<35} {att_str:<25} {bat_str:<10}")

        await asyncio.sleep(1.0)

    print("=" * 80)
    print("-- Telemetry monitoring complete!")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Telemetry monitoring example using MAVSDK"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Monitoring duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Telemetry update rate in Hz (default: 1.0)",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use simplified single-stream output",
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
    if args.simple:
        success = asyncio.get_event_loop().run_until_complete(
            run_simple(connection_string=connection_string, duration=args.duration)
        )
    else:
        success = asyncio.get_event_loop().run_until_complete(
            run(
                connection_string=connection_string,
                duration=args.duration,
                rate=args.rate,
            )
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
