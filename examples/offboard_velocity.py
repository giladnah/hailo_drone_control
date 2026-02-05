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
    # TCP mode (default - for SITL testing)
    python3 offboard_velocity.py --altitude 10 --speed 2.0

    # UART mode (for production with Cube+ Orange)
    python3 offboard_velocity.py -c uart --altitude 10

Example:
    python3 offboard_velocity.py --altitude 10 --tcp-host 192.168.1.100
    python3 offboard_velocity.py -c uart --uart-device /dev/ttyAMA0
"""

import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from mavsdk.offboard import OffboardError, VelocityNedYaw
from examples.common import (
    connect_drone,
    wait_for_gps,
    arm_and_takeoff,
    land_and_disarm,
    safe_land,
    setup_logging,
    create_argument_parser,
    get_connection_string_from_args,
    is_shutdown_requested,
    setup_signal_handlers,
)

# Set up logging
logger = setup_logging()


async def fly_square_pattern(drone, speed: float, leg_duration: float = 5.0) -> bool:
    """
    Fly a square pattern using offboard velocity control.

    Args:
        drone: Connected MAVSDK System.
        speed: Flight speed in m/s.
        leg_duration: Duration for each leg in seconds.

    Returns:
        bool: True if pattern completed successfully.
    """
    # Get current heading for reference
    current_yaw = 0.0
    async for attitude in drone.telemetry.attitude_euler():
        current_yaw = attitude.yaw_deg
        logger.info(f"  Current heading: {current_yaw:.1f}")
        break

    # Start offboard mode
    logger.info("Setting initial setpoint...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, current_yaw))

    logger.info("Starting offboard mode...")
    try:
        await drone.offboard.start()
    except OffboardError as e:
        logger.error(f"Starting offboard mode failed: {e}")
        return False

    logger.info(f"Flying square pattern at {speed} m/s")

    # Fly the square pattern
    legs = [
        ("North", speed, 0.0),
        ("East", 0.0, speed),
        ("South", -speed, 0.0),
        ("West", 0.0, -speed),
    ]

    for i, (direction, north_vel, east_vel) in enumerate(legs, 1):
        if is_shutdown_requested():
            logger.warning("Pattern interrupted by user")
            break

        logger.info(f"  Leg {i}: Flying {direction}...")
        await drone.offboard.set_velocity_ned(
            VelocityNedYaw(north_vel, east_vel, 0.0, current_yaw)
        )
        await asyncio.sleep(leg_duration)

    # Stop and hover
    logger.info("Stopping (hover)...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, current_yaw))
    await asyncio.sleep(2)

    # Stop offboard mode
    logger.info("Stopping offboard mode...")
    try:
        await drone.offboard.stop()
    except OffboardError as e:
        logger.error(f"Stopping offboard mode failed: {e}")
        return False

    return True


async def run(connection_string: str, altitude: float = 10.0, speed: float = 2.0):
    """
    Execute offboard velocity control sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Takeoff altitude in meters.
        speed: Flight speed in m/s.

    Returns:
        bool: True if successful, False otherwise.
    """
    logger.info("=" * 50)
    logger.info("Offboard Velocity Control Demo")
    logger.info("=" * 50)
    logger.info(f"  Altitude: {altitude}m")
    logger.info(f"  Speed: {speed} m/s")
    logger.info("=" * 50)

    # Connect to drone
    drone = await connect_drone(connection_string)
    if not drone:
        return False

    try:
        # Wait for GPS
        if not await wait_for_gps(drone):
            return False

        # Arm and takeoff
        if not await arm_and_takeoff(drone, altitude):
            return False

        # Stabilize before offboard
        logger.info("Stabilizing before offboard mode...")
        await asyncio.sleep(3)

        # Fly square pattern
        if not await fly_square_pattern(drone, speed):
            logger.warning("Pattern incomplete, proceeding to land")

        # Land
        if not await land_and_disarm(drone):
            logger.error("Landing failed!")
            await safe_land(drone)
            return False

        logger.info("=" * 50)
        logger.info("Offboard velocity demo complete!")
        logger.info("=" * 50)
        return True

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        await safe_land(drone)
        return False

    except Exception as e:
        logger.error(f"Error: {e}")
        await safe_land(drone)
        return False


def main():
    """Main entry point."""
    # Set up signal handlers
    setup_signal_handlers()

    # Create parser with standard arguments
    parser = create_argument_parser(
        description="Offboard velocity control example using MAVSDK",
        add_altitude=True,
        altitude_default=10.0,
    )

    # Add demo-specific arguments
    parser.add_argument(
        "--speed",
        type=float,
        default=2.0,
        help="Flight speed in m/s (default: 2.0)",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    # Get connection string from arguments
    connection_string = get_connection_string_from_args(args)

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
