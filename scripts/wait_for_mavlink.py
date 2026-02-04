#!/usr/bin/env python3
"""
wait_for_mavlink.py - MAVLink Health Check Utility

Waits for a MAVLink heartbeat to verify connectivity to the autopilot.
Used for Docker health checks and startup orchestration.

Usage:
    python3 wait_for_mavlink.py [options]

Options:
    --host HOST       MAVLink host (default: localhost)
    --port PORT       MAVLink port (default: 14540)
    --timeout SECS    Timeout in seconds (default: 30)
    --check-only      Exit immediately with status (for health checks)
    --verbose         Enable verbose output
"""

import argparse
import asyncio
import os
import sys
import time
from typing import Optional


async def wait_for_heartbeat(
    host: str = "localhost",
    port: int = 14540,
    timeout: float = 30.0,
    verbose: bool = False
) -> bool:
    """
    Wait for a MAVLink heartbeat using MAVSDK.

    Args:
        host: MAVLink server host.
        port: MAVLink server port.
        timeout: Maximum time to wait in seconds.
        verbose: Enable verbose logging.

    Returns:
        bool: True if heartbeat received, False otherwise.
    """
    try:
        from mavsdk import System
        from mavsdk.core import ConnectionState
    except ImportError:
        print("ERROR: MAVSDK not installed. Install with: pip install mavsdk")
        return False

    if verbose:
        print(f"Connecting to MAVLink at {host}:{port}...")

    drone = System()

    try:
        # Connect to the drone
        await drone.connect(system_address=f"udp://{host}:{port}")

        start_time = time.time()

        # Wait for connection
        async for state in drone.core.connection_state():
            elapsed = time.time() - start_time

            if state.is_connected:
                if verbose:
                    print(f"Connected! Heartbeat received after {elapsed:.1f}s")
                return True

            if elapsed >= timeout:
                if verbose:
                    print(f"Timeout after {timeout}s - no heartbeat received")
                return False

            if verbose and int(elapsed) % 5 == 0:
                print(f"Waiting for heartbeat... ({int(elapsed)}s)")

            await asyncio.sleep(0.5)

    except Exception as e:
        if verbose:
            print(f"Error: {e}")
        return False

    return False


async def check_telemetry(
    host: str = "localhost",
    port: int = 14540,
    timeout: float = 10.0,
    verbose: bool = False
) -> dict:
    """
    Check basic telemetry data is available.

    Args:
        host: MAVLink server host.
        port: MAVLink server port.
        timeout: Maximum time to wait.
        verbose: Enable verbose logging.

    Returns:
        dict: Telemetry status with available data types.
    """
    try:
        from mavsdk import System
    except ImportError:
        return {"error": "MAVSDK not installed"}

    result = {
        "connected": False,
        "armed": None,
        "in_air": None,
        "position": None,
        "battery": None,
    }

    drone = System()

    try:
        await drone.connect(system_address=f"udp://{host}:{port}")

        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                result["connected"] = True
                break
            await asyncio.sleep(0.5)

        if not result["connected"]:
            return result

        # Get telemetry with timeout
        try:
            async for armed in drone.telemetry.armed():
                result["armed"] = armed
                break
        except asyncio.TimeoutError:
            pass

        try:
            async for in_air in drone.telemetry.in_air():
                result["in_air"] = in_air
                break
        except asyncio.TimeoutError:
            pass

        try:
            async for position in drone.telemetry.position():
                result["position"] = {
                    "lat": position.latitude_deg,
                    "lon": position.longitude_deg,
                    "alt": position.relative_altitude_m
                }
                break
        except asyncio.TimeoutError:
            pass

        try:
            async for battery in drone.telemetry.battery():
                result["battery"] = {
                    "voltage": battery.voltage_v,
                    "remaining": battery.remaining_percent
                }
                break
        except asyncio.TimeoutError:
            pass

        if verbose:
            print(f"Telemetry status: {result}")

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Wait for MAVLink heartbeat and check connectivity"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MAVLINK_HOST", "localhost"),
        help="MAVLink host (default: localhost or MAVLINK_HOST env)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MAVLINK_PORT", "14540")),
        help="MAVLink port (default: 14540 or MAVLINK_PORT env)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Quick check mode for health checks"
    )
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Also check telemetry data"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.check_only:
        # Quick check mode - shorter timeout
        timeout = min(args.timeout, 5.0)
    else:
        timeout = args.timeout

    if args.verbose:
        print(f"MAVLink Health Check")
        print(f"  Host: {args.host}")
        print(f"  Port: {args.port}")
        print(f"  Timeout: {timeout}s")
        print()

    # Run the async check
    loop = asyncio.get_event_loop()

    connected = loop.run_until_complete(
        wait_for_heartbeat(
            host=args.host,
            port=args.port,
            timeout=timeout,
            verbose=args.verbose
        )
    )

    if connected and args.telemetry:
        telemetry = loop.run_until_complete(
            check_telemetry(
                host=args.host,
                port=args.port,
                timeout=10.0,
                verbose=args.verbose
            )
        )

        if args.verbose:
            print(f"\nTelemetry: {telemetry}")

    if connected:
        if args.verbose:
            print("\n✓ MAVLink connection OK")
        sys.exit(0)
    else:
        if args.verbose:
            print("\n✗ MAVLink connection FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

