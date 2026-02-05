#!/usr/bin/env python3
"""
hover_rotate.py - Demo Flight Control Script

Demonstrates autonomous flight control using MAVSDK:
1. Connect to the drone (SITL or real)
2. Arm and takeoff to specified altitude
3. Hover and rotate 360 degrees (yaw)
4. Land safely

Supports both WiFi (UDP) and UART (serial) connections for Raspberry Pi.

Usage:
    # TCP mode (default - for SITL testing)
    python3 hover_rotate.py --altitude 10 --rotation 360

    # UART mode (for production with Cube+ Orange)
    python3 hover_rotate.py -c uart --altitude 10

Options:
    --altitude METERS   Takeoff altitude (default: 5.0)
    --rotation DEGREES  Rotation amount (default: 360)
    --speed DEG/SEC     Rotation speed (default: 30)
    -c, --connection-type  Connection type: uart, udp, or tcp (default: tcp)

Example:
    python3 hover_rotate.py --altitude 10 --rotation 720 --tcp-host 192.168.1.100
    python3 hover_rotate.py -c uart --uart-device /dev/ttyAMA0
"""

import asyncio
import math
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from examples.common import (
    connect_drone,
    preflight_check,
    arm_and_takeoff,
    land_and_disarm,
    safe_land,
    emergency_stop,
    setup_logging,
    create_argument_parser,
    get_connection_string_from_args,
    is_shutdown_requested,
    setup_signal_handlers,
)

# Set up logging
logger = setup_logging()


class HoverRotateDemo:
    """
    Autonomous flight demo: takeoff, rotate, and land.

    Attributes:
        altitude: Target altitude in meters.
        rotation: Total rotation in degrees.
        rotation_speed: Rotation speed in degrees per second.
    """

    def __init__(
        self,
        connection_string: str,
        altitude: float = 5.0,
        rotation: float = 360.0,
        rotation_speed: float = 30.0,
    ):
        """
        Initialize the demo.

        Args:
            connection_string: MAVSDK connection string (UDP or serial).
            altitude: Target altitude in meters.
            rotation: Total rotation in degrees (can be > 360).
            rotation_speed: Rotation speed in degrees/second.
        """
        self.connection_string = connection_string
        self.altitude = altitude
        self.rotation = rotation
        self.rotation_speed = rotation_speed
        self.drone = None
        self._initial_yaw = 0.0

    async def _get_initial_yaw(self) -> float:
        """
        Get and store the initial yaw/heading.

        Returns:
            float: Initial yaw in degrees.
        """
        async for attitude in self.drone.telemetry.attitude_euler():
            self._initial_yaw = attitude.yaw_deg
            logger.info(f"  Initial heading: {self._initial_yaw:.1f} deg")
            return self._initial_yaw
        return 0.0

    async def rotate(self) -> bool:
        """
        Perform yaw rotation while hovering.

        Returns:
            bool: True if rotation completed.
        """
        logger.info(
            f"Starting {self.rotation} deg rotation at {self.rotation_speed} deg/s..."
        )

        try:
            # Get current position for hold
            current_pos = None
            async for position in self.drone.telemetry.position():
                current_pos = position
                break

            if current_pos is None:
                logger.error("Could not get current position")
                return False

            # Start offboard mode for precise control
            from mavsdk.offboard import OffboardError, VelocityNedYaw

            logger.info("  Entering offboard mode...")

            # Set initial setpoint (hold position, no yaw rate)
            await self.drone.offboard.set_velocity_ned(
                VelocityNedYaw(0.0, 0.0, 0.0, self._initial_yaw)
            )

            try:
                await self.drone.offboard.start()
                logger.info("  Offboard mode active")
            except OffboardError as e:
                logger.error(f"  Offboard start failed: {e}")
                return False

            # Perform rotation
            direction = 1 if self.rotation >= 0 else -1
            yaw_rate = direction * self.rotation_speed  # deg/s

            start_time = time.time()
            rotated = 0.0

            while abs(rotated) < abs(self.rotation):
                if is_shutdown_requested():
                    logger.warning("  Rotation cancelled by user")
                    break

                elapsed = time.time() - start_time
                rotated = elapsed * yaw_rate

                # Calculate current target yaw
                target_yaw = self._initial_yaw + rotated
                # Normalize to -180 to 180
                target_yaw = ((target_yaw + 180) % 360) - 180

                # Send velocity command (hold position, rotate)
                await self.drone.offboard.set_velocity_ned(
                    VelocityNedYaw(0.0, 0.0, 0.0, target_yaw)
                )

                progress = abs(rotated) / abs(self.rotation) * 100
                logger.info(
                    f"  Rotating: {abs(rotated):.1f} deg / "
                    f"{abs(self.rotation)} deg ({progress:.0f}%)"
                )

                await asyncio.sleep(0.1)

            # Stop rotation
            logger.info("  Stopping rotation...")
            final_yaw = self._initial_yaw + self.rotation
            final_yaw = ((final_yaw + 180) % 360) - 180

            await self.drone.offboard.set_velocity_ned(
                VelocityNedYaw(0.0, 0.0, 0.0, final_yaw)
            )

            await asyncio.sleep(2)  # Stabilize

            # Exit offboard mode
            logger.info("  Exiting offboard mode...")
            await self.drone.offboard.stop()

            logger.info(f"  Rotation complete: {self.rotation} deg")
            return True

        except Exception as e:
            logger.error(f"Rotation failed: {e}")
            # Try to stop offboard mode
            try:
                await self.drone.offboard.stop()
            except Exception:
                pass
            return False

    async def run(self) -> bool:
        """
        Execute the full demo sequence.

        Returns:
            bool: True if demo completed successfully.
        """
        logger.info("=" * 50)
        logger.info("PX4 Hover & Rotate Demo")
        logger.info("=" * 50)
        logger.info(f"  Altitude: {self.altitude}m")
        logger.info(f"  Rotation: {self.rotation} deg")
        logger.info(f"  Speed: {self.rotation_speed} deg/s")
        logger.info("=" * 50)

        success = False

        try:
            # Step 1: Connect
            self.drone = await connect_drone(self.connection_string)
            if not self.drone:
                return False

            # Step 2: Preflight check
            if not await preflight_check(self.drone):
                return False

            # Get initial yaw before takeoff
            await self._get_initial_yaw()

            # Step 3: Arm and takeoff
            if not await arm_and_takeoff(self.drone, self.altitude):
                return False

            # Step 4: Rotate
            if not await self.rotate():
                logger.warning("Rotation incomplete, proceeding to land")

            # Step 5: Land
            if not await land_and_disarm(self.drone):
                logger.error("Landing failed!")
                await emergency_stop(self.drone)
                return False

            success = True
            logger.info("=" * 50)
            logger.info("Demo completed successfully!")
            logger.info("=" * 50)

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            if self.drone:
                await safe_land(self.drone)

        except Exception as e:
            logger.error(f"Demo failed: {e}")
            if self.drone:
                try:
                    await safe_land(self.drone)
                except Exception:
                    await emergency_stop(self.drone)

        return success


def main():
    """Main entry point."""
    # Set up signal handlers
    setup_signal_handlers()

    # Create parser with standard arguments
    parser = create_argument_parser(
        description="PX4 Hover & Rotate Demo - Takeoff, rotate 360 deg, and land",
        add_altitude=True,
        altitude_default=5.0,
    )

    # Add demo-specific arguments
    parser.add_argument(
        "--rotation",
        type=float,
        default=360.0,
        help="Rotation amount in degrees (default: 360)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=30.0,
        help="Rotation speed in degrees/second (default: 30)",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    # Get connection string from arguments
    connection_string = get_connection_string_from_args(args)

    # Create and run demo
    demo = HoverRotateDemo(
        connection_string=connection_string,
        altitude=args.altitude,
        rotation=args.rotation,
        rotation_speed=args.speed,
    )

    # Run async
    success = asyncio.get_event_loop().run_until_complete(demo.run())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
