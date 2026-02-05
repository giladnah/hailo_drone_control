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
    # WiFi mode (default - for SITL testing)
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

import argparse
import asyncio
import logging
import math
import sys
import time
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


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

    async def connect(self, timeout: float = 30.0) -> bool:
        """
        Connect to the drone via MAVSDK.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            bool: True if connected successfully.
        """
        from mavsdk import System

        logger.info(f"Connecting to drone: {self.connection_string}")

        self.drone = System()
        await self.drone.connect(system_address=self.connection_string)

        # Wait for connection
        start_time = time.time()
        async for state in self.drone.core.connection_state():
            if state.is_connected:
                logger.info("Connected to drone")
                return True

            if time.time() - start_time > timeout:
                logger.error(f"Connection timeout after {timeout}s")
                return False

            await asyncio.sleep(0.5)

        return False

    async def preflight_check(self) -> bool:
        """
        Perform preflight checks.

        Returns:
            bool: True if all checks pass.
        """
        logger.info("Running preflight checks...")

        # Check GPS
        async for health in self.drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                logger.info("  GPS OK")
                break
            logger.warning("  Waiting for GPS lock...")
            await asyncio.sleep(1)

        # Check if already armed
        async for armed in self.drone.telemetry.armed():
            if armed:
                logger.warning("  Drone is already armed")
            else:
                logger.info("  Drone disarmed")
            break

        # Get initial position
        async for position in self.drone.telemetry.position():
            logger.info(f"  Position: {position.latitude_deg:.6f}, {position.longitude_deg:.6f}")
            logger.info(f"  Altitude: {position.relative_altitude_m:.1f}m")
            break

        # Get battery status
        async for battery in self.drone.telemetry.battery():
            logger.info(f"  Battery: {battery.remaining_percent * 100:.0f}%")
            if battery.remaining_percent < 0.2:
                logger.error("  Battery too low!")
                return False
            break

        # Store initial yaw
        async for attitude in self.drone.telemetry.attitude_euler():
            self._initial_yaw = attitude.yaw_deg
            logger.info(f"  Initial heading: {self._initial_yaw:.1f} deg")
            break

        logger.info("Preflight checks complete")
        return True

    async def arm_and_takeoff(self) -> bool:
        """
        Arm the drone and take off to target altitude.

        Returns:
            bool: True if takeoff successful.
        """
        logger.info(f"Arming and taking off to {self.altitude}m...")

        try:
            # Arm the drone
            logger.info("  Arming...")
            await self.drone.action.arm()
            logger.info("  Armed")

            # Take off
            logger.info(f"  Taking off to {self.altitude}m...")
            await self.drone.action.set_takeoff_altitude(self.altitude)
            await self.drone.action.takeoff()

            # Wait for takeoff to complete
            target_alt = self.altitude * 0.95  # 95% of target

            async for position in self.drone.telemetry.position():
                alt = position.relative_altitude_m
                if alt >= target_alt:
                    logger.info(f"  Reached altitude: {alt:.1f}m")
                    break
                logger.info(f"  Climbing: {alt:.1f}m / {self.altitude}m")
                await asyncio.sleep(0.5)

            # Stabilize
            logger.info("  Stabilizing...")
            await asyncio.sleep(2)

            return True

        except Exception as e:
            logger.error(f"Takeoff failed: {e}")
            return False

    async def rotate(self) -> bool:
        """
        Perform yaw rotation while hovering.

        Returns:
            bool: True if rotation completed.
        """
        logger.info(f"Starting {self.rotation} deg rotation at {self.rotation_speed} deg/s...")

        try:
            # Calculate rotation parameters
            total_rotation_rad = math.radians(self.rotation)
            rotation_time = abs(self.rotation) / self.rotation_speed

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
                logger.info(f"  Rotating: {abs(rotated):.1f} deg / {abs(self.rotation)} deg ({progress:.0f}%)")

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

    async def land(self) -> bool:
        """
        Land the drone safely.

        Returns:
            bool: True if landing successful.
        """
        logger.info("Landing...")

        try:
            await self.drone.action.land()

            # Wait for landing
            async for in_air in self.drone.telemetry.in_air():
                if not in_air:
                    logger.info("  Landed")
                    break
                await asyncio.sleep(0.5)

            # Disarm
            logger.info("  Disarming...")
            await asyncio.sleep(2)  # Wait for motors to stop

            async for armed in self.drone.telemetry.armed():
                if not armed:
                    logger.info("  Disarmed")
                    break
                await asyncio.sleep(0.5)

            return True

        except Exception as e:
            logger.error(f"Landing failed: {e}")
            return False

    async def emergency_stop(self):
        """Emergency stop - kill motors."""
        logger.warning("EMERGENCY STOP!")
        try:
            await self.drone.action.kill()
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}")

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
            if not await self.connect():
                return False

            # Step 2: Preflight check
            if not await self.preflight_check():
                return False

            # Step 3: Arm and takeoff
            if not await self.arm_and_takeoff():
                return False

            # Step 4: Rotate
            if not await self.rotate():
                logger.warning("Rotation incomplete, proceeding to land")

            # Step 5: Land
            if not await self.land():
                logger.error("Landing failed!")
                await self.emergency_stop()
                return False

            success = True
            logger.info("=" * 50)
            logger.info("Demo completed successfully!")
            logger.info("=" * 50)

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            await self.land()

        except Exception as e:
            logger.error(f"Demo failed: {e}")
            try:
                await self.land()
            except Exception:
                await self.emergency_stop()

        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PX4 Hover & Rotate Demo - Takeoff, rotate 360 deg, and land"
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=5.0,
        help="Takeoff altitude in meters (default: 5.0)"
    )
    parser.add_argument(
        "--rotation",
        type=float,
        default=360.0,
        help="Rotation amount in degrees (default: 360)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=30.0,
        help="Rotation speed in degrees/second (default: 30)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    # Add connection arguments (--connection-type, --uart-*, --udp-*, --tcp-*)
    add_connection_arguments(parser)

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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
