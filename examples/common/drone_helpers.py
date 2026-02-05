#!/usr/bin/env python3
"""
drone_helpers.py - Common Drone Operations

Provides shared functionality for PX4 drone control scripts:
- Connection management
- Preflight checks
- Takeoff and landing
- Telemetry helpers
- Logging setup

Usage:
    from examples.common import (
        DroneConnection,
        connect_drone,
        preflight_check,
        arm_and_takeoff,
        land_and_disarm,
    )

    async with DroneConnection(connection_string) as drone:
        await preflight_check(drone)
        await arm_and_takeoff(drone, altitude=10.0)
        # ... do something ...
        await land_and_disarm(drone)
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/../..")

from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)

# Module-level logger
logger = logging.getLogger(__name__)

# Global shutdown flag for signal handling
_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle shutdown signals (Ctrl+C)."""
    global _shutdown_requested
    logger.warning("Shutdown requested (Ctrl+C)")
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """
    Check if shutdown has been requested.

    Returns:
        bool: True if shutdown was requested via signal.
    """
    return _shutdown_requested


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def setup_logging(
    level: int = logging.INFO,
    format_string: str = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt: str = "%H:%M:%S",
) -> logging.Logger:
    """
    Configure logging for drone scripts.

    Args:
        level: Logging level (default: INFO).
        format_string: Log message format.
        datefmt: Date format string.

    Returns:
        logging.Logger: Configured root logger.
    """
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt=datefmt,
    )
    return logging.getLogger()


def create_argument_parser(
    description: str,
    add_altitude: bool = True,
    altitude_default: float = 5.0,
    add_verbose: bool = True,
) -> argparse.ArgumentParser:
    """
    Create a standard argument parser with connection options.

    Args:
        description: Script description.
        add_altitude: Add --altitude argument.
        altitude_default: Default altitude value.
        add_verbose: Add --verbose flag.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(description=description)

    if add_altitude:
        parser.add_argument(
            "--altitude",
            type=float,
            default=altitude_default,
            help=f"Takeoff altitude in meters (default: {altitude_default})",
        )

    if add_verbose:
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Enable verbose logging",
        )

    # Add standard connection arguments
    add_connection_arguments(parser)

    return parser


def get_connection_string_from_args(args: argparse.Namespace) -> str:
    """
    Build connection string from parsed arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        str: MAVSDK connection string.
    """
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

    return config.get_connection_string()


@dataclass
class TelemetrySnapshot:
    """
    Snapshot of current telemetry data.

    Attributes:
        armed: Whether drone is armed.
        in_air: Whether drone is in the air.
        latitude: Current latitude in degrees.
        longitude: Current longitude in degrees.
        altitude: Relative altitude in meters.
        heading: Current heading in degrees.
        battery_percent: Battery remaining (0.0-1.0).
        battery_voltage: Battery voltage.
        gps_satellites: Number of GPS satellites.
        gps_fix_ok: Whether GPS fix is sufficient.
    """

    armed: bool = False
    in_air: bool = False
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    heading: float = 0.0
    battery_percent: float = 0.0
    battery_voltage: float = 0.0
    gps_satellites: int = 0
    gps_fix_ok: bool = False


class DroneConnection:
    """
    Context manager for drone connections.

    Handles connection setup, cleanup, and provides convenient access
    to the MAVSDK System instance.

    Usage:
        async with DroneConnection("tcpout://localhost:5760") as drone:
            await drone.action.arm()

    Attributes:
        connection_string: MAVSDK connection string.
        timeout: Connection timeout in seconds.
        drone: The connected MAVSDK System instance.
    """

    def __init__(self, connection_string: str, timeout: float = 30.0):
        """
        Initialize drone connection.

        Args:
            connection_string: MAVSDK connection string.
            timeout: Connection timeout in seconds.
        """
        self.connection_string = connection_string
        self.timeout = timeout
        self.drone = None
        self._connected = False

    async def __aenter__(self):
        """Connect to the drone when entering context."""
        self.drone = await connect_drone(
            self.connection_string,
            timeout=self.timeout,
        )
        if self.drone:
            self._connected = True
        return self.drone

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up when exiting context."""
        if self._connected and self.drone:
            # Try to land if in air
            try:
                async for in_air in self.drone.telemetry.in_air():
                    if in_air:
                        logger.warning("Drone still in air, attempting landing...")
                        await safe_land(self.drone)
                    break
            except Exception:
                pass
        return False  # Don't suppress exceptions


async def connect_drone(
    connection_string: str,
    timeout: float = 30.0,
) -> Optional["System"]:
    """
    Connect to a drone and wait for heartbeat.

    Args:
        connection_string: MAVSDK connection string.
        timeout: Connection timeout in seconds.

    Returns:
        System: Connected MAVSDK System, or None if failed.
    """
    from mavsdk import System

    logger.info(f"Connecting to drone: {connection_string}")

    drone = System()
    await drone.connect(system_address=connection_string)

    # Wait for connection
    start_time = time.time()
    async for state in drone.core.connection_state():
        if state.is_connected:
            logger.info("Connected to drone")
            return drone

        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.error(f"Connection timeout after {timeout}s")
            return None

        if is_shutdown_requested():
            logger.warning("Connection cancelled by user")
            return None

        await asyncio.sleep(0.5)

    return None


async def wait_for_gps(
    drone: "System",
    timeout: float = 60.0,
) -> bool:
    """
    Wait for GPS lock (global position OK).

    Args:
        drone: Connected MAVSDK System.
        timeout: Timeout in seconds.

    Returns:
        bool: True if GPS lock acquired.
    """
    logger.info("Waiting for GPS lock...")
    start_time = time.time()

    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            logger.info("GPS lock acquired")
            return True

        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.error(f"GPS timeout after {timeout}s")
            return False

        if is_shutdown_requested():
            return False

        if int(elapsed) % 10 == 0 and elapsed > 0:
            logger.info(f"  Still waiting for GPS... ({int(elapsed)}s)")

        await asyncio.sleep(1)

    return False


async def preflight_check(
    drone: "System",
    min_battery: float = 0.2,
) -> bool:
    """
    Perform standard preflight checks.

    Checks:
        - GPS lock
        - Battery level
        - Armed state
        - Current position

    Args:
        drone: Connected MAVSDK System.
        min_battery: Minimum battery level (0.0-1.0).

    Returns:
        bool: True if all checks pass.
    """
    logger.info("Running preflight checks...")

    # Check GPS
    if not await wait_for_gps(drone, timeout=30.0):
        logger.error("Preflight: GPS check failed")
        return False
    logger.info("  GPS: OK")

    # Check armed state
    async for armed in drone.telemetry.armed():
        if armed:
            logger.warning("  Armed state: ARMED (already armed)")
        else:
            logger.info("  Armed state: DISARMED")
        break

    # Check position
    async for position in drone.telemetry.position():
        logger.info(
            f"  Position: {position.latitude_deg:.6f}, {position.longitude_deg:.6f}"
        )
        logger.info(f"  Altitude: {position.relative_altitude_m:.1f}m")
        break

    # Check battery
    async for battery in drone.telemetry.battery():
        percent = battery.remaining_percent
        voltage = battery.voltage_v
        logger.info(f"  Battery: {percent * 100:.0f}% ({voltage:.1f}V)")
        if percent < min_battery:
            logger.error(f"  Battery too low! ({percent * 100:.0f}% < {min_battery * 100:.0f}%)")
            return False
        break

    logger.info("Preflight checks complete")
    return True


async def arm_and_takeoff(
    drone: "System",
    altitude: float = 5.0,
    altitude_tolerance: float = 0.95,
    timeout: float = 60.0,
) -> bool:
    """
    Arm the drone and take off to specified altitude.

    Args:
        drone: Connected MAVSDK System.
        altitude: Target altitude in meters.
        altitude_tolerance: Fraction of altitude to consider "reached" (0.0-1.0).
        timeout: Takeoff timeout in seconds.

    Returns:
        bool: True if takeoff successful.
    """
    logger.info(f"Arming and taking off to {altitude}m...")

    try:
        # Arm
        logger.info("  Arming...")
        await drone.action.arm()
        logger.info("  Armed")

        # Brief delay to let simulator stabilize
        await asyncio.sleep(1.0)

        # Set takeoff altitude and take off
        await drone.action.set_takeoff_altitude(altitude)
        logger.info(f"  Taking off to {altitude}m...")
        await drone.action.takeoff()

        # Brief delay to let takeoff command propagate
        await asyncio.sleep(2.0)

        # Wait for altitude
        target_alt = altitude * altitude_tolerance
        start_time = time.time()
        last_alt = 0.0
        stable_count = 0

        async for position in drone.telemetry.position():
            current_alt = position.relative_altitude_m
            elapsed = time.time() - start_time

            # Check if target reached
            if current_alt >= target_alt:
                logger.info(f"  Reached altitude: {current_alt:.1f}m")
                break

            # Check for stabilization (altitude not increasing)
            if abs(current_alt - last_alt) < 0.1:
                stable_count += 1
            else:
                stable_count = 0
            last_alt = current_alt

            # Accept stabilized altitude if above 70%
            if stable_count >= 10 and current_alt >= altitude * 0.70:
                logger.info(f"  Altitude stabilized at {current_alt:.1f}m")
                break

            # Timeout check
            if elapsed > timeout:
                if current_alt >= altitude * 0.70:
                    logger.warning(f"  Timeout, but altitude acceptable: {current_alt:.1f}m")
                    break
                logger.error(f"  Takeoff timeout at {current_alt:.1f}m")
                return False

            # Shutdown check
            if is_shutdown_requested():
                logger.warning("  Takeoff cancelled by user")
                return False

            # Critical: yield immediately to allow other async tasks to run
            # Using sleep(0) instead of sleep(0.5) prevents telemetry starvation
            await asyncio.sleep(0)

        # Stabilize
        logger.info("  Stabilizing...")
        await asyncio.sleep(2)

        return True

    except Exception as e:
        logger.error(f"Takeoff failed: {e}")
        return False


async def land_and_disarm(
    drone: "System",
    timeout: float = 60.0,
) -> bool:
    """
    Land the drone and wait for disarm.

    Args:
        drone: Connected MAVSDK System.
        timeout: Landing timeout in seconds.

    Returns:
        bool: True if landing successful.
    """
    logger.info("Landing...")

    try:
        await drone.action.land()

        # Wait for landing
        start_time = time.time()
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                logger.info("  Landed")
                break

            if time.time() - start_time > timeout:
                logger.warning(f"  Landing timeout after {timeout}s")
                break

            # Critical: yield immediately to allow other tasks to run
            await asyncio.sleep(0)

        # Wait for disarm
        logger.info("  Waiting for disarm...")
        await asyncio.sleep(2)

        async for armed in drone.telemetry.armed():
            if not armed:
                logger.info("  Disarmed")
                break
            # Critical: yield immediately
            await asyncio.sleep(0)

        return True

    except Exception as e:
        logger.error(f"Landing failed: {e}")
        return False


async def safe_land(drone: "System", timeout: float = 30.0) -> bool:
    """
    Emergency landing - attempt to land safely regardless of state.

    Args:
        drone: Connected MAVSDK System.
        timeout: Landing timeout in seconds.

    Returns:
        bool: True if landing command was sent.
    """
    logger.warning("Initiating safe landing...")

    try:
        await drone.action.land()
        logger.info("  Landing command sent")

        # Wait for landing
        start_time = time.time()
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                logger.info("  Landed safely")
                return True

            if time.time() - start_time > timeout:
                logger.warning(f"  Landing timeout, but command was sent")
                return True

            # Critical: yield immediately to allow other tasks to run
            await asyncio.sleep(0)

        return True

    except Exception as e:
        logger.error(f"Safe landing failed: {e}")
        return False


async def emergency_stop(drone: "System") -> bool:
    """
    Emergency stop - kill motors immediately.

    WARNING: This will cause the drone to fall from the sky!
    Only use in emergencies when landing is not possible.

    Args:
        drone: Connected MAVSDK System.

    Returns:
        bool: True if kill command sent.
    """
    logger.error("EMERGENCY STOP - KILLING MOTORS!")

    try:
        await drone.action.kill()
        logger.info("  Kill command sent")
        return True
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        return False


async def get_telemetry_snapshot(drone: "System") -> TelemetrySnapshot:
    """
    Get a snapshot of current telemetry data.

    Args:
        drone: Connected MAVSDK System.

    Returns:
        TelemetrySnapshot: Current telemetry values.
    """
    snapshot = TelemetrySnapshot()

    try:
        async for armed in drone.telemetry.armed():
            snapshot.armed = armed
            break
    except Exception:
        pass

    try:
        async for in_air in drone.telemetry.in_air():
            snapshot.in_air = in_air
            break
    except Exception:
        pass

    try:
        async for position in drone.telemetry.position():
            snapshot.latitude = position.latitude_deg
            snapshot.longitude = position.longitude_deg
            snapshot.altitude = position.relative_altitude_m
            break
    except Exception:
        pass

    try:
        async for attitude in drone.telemetry.attitude_euler():
            snapshot.heading = attitude.yaw_deg
            break
    except Exception:
        pass

    try:
        async for battery in drone.telemetry.battery():
            snapshot.battery_percent = battery.remaining_percent
            snapshot.battery_voltage = battery.voltage_v
            break
    except Exception:
        pass

    try:
        async for gps in drone.telemetry.gps_info():
            snapshot.gps_satellites = gps.num_satellites
            break
    except Exception:
        pass

    try:
        async for health in drone.telemetry.health():
            snapshot.gps_fix_ok = health.is_global_position_ok
            break
    except Exception:
        pass

    return snapshot

