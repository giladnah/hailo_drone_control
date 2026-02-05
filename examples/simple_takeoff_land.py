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

import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

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


async def run(connection_string: str, altitude: float = 5.0, hover_time: float = 5.0):
    """
    Execute simple takeoff and land sequence.

    Args:
        connection_string: MAVSDK connection string (UDP or serial).
        altitude: Target altitude in meters.
        hover_time: Time to hover in seconds.

    Returns:
        bool: True if successful, False otherwise.
    """
    logger.info("=" * 50)
    logger.info("Simple Takeoff and Land Demo")
    logger.info("=" * 50)
    logger.info(f"  Altitude: {altitude}m")
    logger.info(f"  Hover time: {hover_time}s")
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

        # Hover for specified time (with interrupt check)
        logger.info(f"Hovering for {hover_time} seconds...")
        hover_start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - hover_start < hover_time:
            if is_shutdown_requested():
                logger.warning("Hover interrupted by user")
                break
            await asyncio.sleep(0.5)

        # Land
        if not await land_and_disarm(drone):
            logger.error("Landing failed!")
            await safe_land(drone)
            return False

        logger.info("=" * 50)
        logger.info("Mission complete!")
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
        description="Simple takeoff and land example using MAVSDK",
        add_altitude=True,
        altitude_default=5.0,
    )

    # Add demo-specific arguments
    parser.add_argument(
        "--hover-time",
        type=float,
        default=5.0,
        help="Time to hover in seconds (default: 5.0)",
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
            hover_time=args.hover_time,
        )
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
