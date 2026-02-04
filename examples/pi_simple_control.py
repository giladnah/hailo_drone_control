#!/usr/bin/env python3
"""
pi_simple_control.py - Minimal Control Example for Raspberry Pi

A minimal example showing how to connect and control a drone from Raspberry Pi.
Demonstrates the core workflow without complex logic.

Features:
- Connect via UART or WiFi
- Subscribe to telemetry
- Execute simple commands (arm, takeoff, land)
- Works with both SITL and real hardware

Usage:
    # WiFi mode (testing with SITL)
    python3 pi_simple_control.py -c wifi --wifi-host 192.168.1.100

    # UART mode (production with Cube+ Orange)
    python3 pi_simple_control.py -c uart

    # Monitor telemetry only (no flight)
    python3 pi_simple_control.py -c wifi --wifi-host 192.168.1.100 --monitor-only

Example:
    python3 pi_simple_control.py -c uart --altitude 5
    python3 pi_simple_control.py -c wifi --wifi-host 192.168.1.100 --monitor-only --duration 60
"""

import argparse
import asyncio
import signal
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/..")

from scripts.mavlink_connection import (
    ConnectionConfig,
    add_connection_arguments,
    print_connection_info,
)

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_requested
    print("\nShutdown requested...")
    shutdown_requested = True


async def monitor_telemetry(drone, duration: float = 30.0) -> None:
    """
    Monitor and display telemetry for a specified duration.

    Args:
        drone: Connected MAVSDK System instance.
        duration: Monitoring duration in seconds.
    """
    global shutdown_requested

    print(f"\nMonitoring telemetry for {duration}s (Ctrl+C to stop)")
    print("-" * 60)

    start_time = time.time()
    last_print = 0

    while not shutdown_requested:
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        # Print every second
        if int(elapsed) > last_print:
            last_print = int(elapsed)

            # Get current telemetry
            position = None
            battery = None
            armed = None
            mode = None

            try:
                async for pos in drone.telemetry.position():
                    position = pos
                    break
            except Exception:
                pass

            try:
                async for bat in drone.telemetry.battery():
                    battery = bat
                    break
            except Exception:
                pass

            try:
                async for arm in drone.telemetry.armed():
                    armed = arm
                    break
            except Exception:
                pass

            try:
                async for m in drone.telemetry.flight_mode():
                    mode = m
                    break
            except Exception:
                pass

            # Format output
            pos_str = f"{position.latitude_deg:.6f}, {position.longitude_deg:.6f}" if position else "N/A"
            alt_str = f"{position.relative_altitude_m:.1f}m" if position else "N/A"
            bat_str = f"{battery.remaining_percent * 100:.0f}%" if battery else "N/A"
            armed_str = "ARMED" if armed else "DISARMED"
            mode_str = str(mode) if mode else "N/A"

            print(f"[{int(elapsed):3d}s] Pos: {pos_str} | Alt: {alt_str} | Bat: {bat_str} | {armed_str} | {mode_str}")

        await asyncio.sleep(0.1)

    print("-" * 60)
    print("Monitoring complete")


async def simple_flight(drone, altitude: float = 5.0) -> bool:
    """
    Execute a simple takeoff and land sequence.

    Args:
        drone: Connected MAVSDK System instance.
        altitude: Target altitude in meters.

    Returns:
        bool: True if successful.
    """
    global shutdown_requested

    print(f"\nExecuting simple flight to {altitude}m")
    print("-" * 40)

    try:
        # Wait for GPS
        print("Waiting for GPS lock...")
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("  GPS OK")
                break
            if shutdown_requested:
                return False
            await asyncio.sleep(1)

        # Arm
        print("Arming...")
        await drone.action.arm()
        print("  Armed")

        # Takeoff
        print(f"Taking off to {altitude}m...")
        await drone.action.set_takeoff_altitude(altitude)
        await drone.action.takeoff()

        # Wait for altitude
        async for position in drone.telemetry.position():
            if shutdown_requested:
                print("  Shutdown requested during takeoff")
                break
            if position.relative_altitude_m >= altitude * 0.95:
                print(f"  Reached {position.relative_altitude_m:.1f}m")
                break
            await asyncio.sleep(0.5)

        # Hover
        if not shutdown_requested:
            print("Hovering for 5 seconds...")
            for i in range(5):
                if shutdown_requested:
                    break
                await asyncio.sleep(1)
                print(f"  {5-i}...")

        # Land
        print("Landing...")
        await drone.action.land()

        # Wait for landing
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                print("  Landed")
                break
            await asyncio.sleep(0.5)

        print("-" * 40)
        print("Flight complete!")
        return True

    except Exception as e:
        print(f"Error during flight: {e}")

        # Emergency landing
        try:
            print("Attempting emergency landing...")
            await drone.action.land()
        except Exception:
            pass

        return False


async def run(
    connection_string: str,
    altitude: float = 5.0,
    monitor_only: bool = False,
    duration: float = 30.0,
    timeout: float = 30.0,
) -> bool:
    """
    Main control function.

    Args:
        connection_string: MAVSDK connection string.
        altitude: Target altitude for flight.
        monitor_only: Only monitor telemetry, no flight.
        duration: Monitoring duration in seconds.
        timeout: Connection timeout in seconds.

    Returns:
        bool: True if successful.
    """
    global shutdown_requested

    try:
        from mavsdk import System
    except ImportError:
        print("ERROR: MAVSDK not installed. Run: pip install mavsdk")
        return False

    print(f"\nConnecting to: {connection_string}")

    drone = System()

    try:
        await drone.connect(system_address=connection_string)

        # Wait for connection
        print("Waiting for connection...")
        connected = False
        start_time = time.time()

        async for state in drone.core.connection_state():
            if state.is_connected:
                connected = True
                print("  Connected!")
                break

            if time.time() - start_time > timeout:
                print(f"  Connection timeout after {timeout}s")
                return False

            if shutdown_requested:
                return False

            await asyncio.sleep(0.5)

        if not connected:
            return False

        # Execute based on mode
        if monitor_only:
            await monitor_telemetry(drone, duration)
            return True
        else:
            return await simple_flight(drone, altitude)

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description="Minimal control example for Raspberry Pi"
    )

    parser.add_argument(
        "--altitude",
        type=float,
        default=5.0,
        help="Takeoff altitude in meters (default: 5.0)"
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Only monitor telemetry, do not fly"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Monitoring duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Connection timeout in seconds (default: 30)"
    )

    # Add connection arguments
    add_connection_arguments(parser)

    args = parser.parse_args()

    # Build connection config
    config = ConnectionConfig.from_args(
        connection_type=args.connection_type,
        uart_device=args.uart_device,
        uart_baud=args.uart_baud,
        wifi_host=args.wifi_host,
        wifi_port=args.wifi_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
    )

    # Print connection info
    print_connection_info(config)

    # Get connection string
    connection_string = config.get_connection_string()

    # Run
    success = asyncio.get_event_loop().run_until_complete(
        run(
            connection_string=connection_string,
            altitude=args.altitude,
            monitor_only=args.monitor_only,
            duration=args.duration,
            timeout=args.timeout,
        )
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

