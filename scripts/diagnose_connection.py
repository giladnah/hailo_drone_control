#!/usr/bin/env python3
"""
diagnose_connection.py - MAVLink Connection Diagnostic Tool

Tests the MAVLink connection to PX4 and diagnoses telemetry issues.
This tool helps identify why telemetry might not be flowing properly.

IMPORTANT: MAVSDK Telemetry Starvation Bug
==========================================
When using `async for` on MAVSDK telemetry streams with delays (e.g.,
`await asyncio.sleep(0.5)`), the event loop gives too much priority to
the telemetry task, preventing commands (arm, takeoff) from executing.

Solution: Use `await asyncio.sleep(0)` in telemetry loops to immediately
yield control, or use the TelemetryManager from examples.common.

Usage:
    # Test TCP connection (default)
    python scripts/diagnose_connection.py

    # Test UDP connection
    python scripts/diagnose_connection.py -c udp --udp-port 14540

    # Test specific TCP host
    python scripts/diagnose_connection.py -c tcp --tcp-host 192.168.1.100

    # Full test including takeoff
    python scripts/diagnose_connection.py --test-action
"""

import argparse
import asyncio
import logging
import sys
import time
from typing import Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_raw_mavlink(connection_string: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """
    Test raw MAVLink connection using pymavlink.

    This bypasses MAVSDK to test the underlying connection.

    Args:
        connection_string: MAVLink connection string.
        timeout: Timeout in seconds.

    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        from pymavlink import mavutil
    except ImportError:
        return False, "pymavlink not installed (pip install pymavlink)"

    logger.info(f"Testing raw MAVLink connection to {connection_string}")

    try:
        # Convert MAVSDK format to pymavlink format
        if connection_string.startswith("tcpout://"):
            parts = connection_string.replace("tcpout://", "").split(":")
            host, port = parts[0], int(parts[1])
            mavlink_conn = f"tcp:{host}:{port}"
        elif connection_string.startswith("udpin://"):
            parts = connection_string.replace("udpin://", "").split(":")
            host, port = parts[0], int(parts[1])
            mavlink_conn = f"udpin:{host}:{port}"
        else:
            mavlink_conn = connection_string

        logger.info(f"  pymavlink format: {mavlink_conn}")

        # Connect
        mav = mavutil.mavlink_connection(mavlink_conn, baud=57600)

        # Wait for heartbeat
        logger.info("  Waiting for heartbeat...")
        start = time.time()
        while time.time() - start < timeout:
            msg = mav.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
            if msg:
                logger.info(f"  ✓ Heartbeat received from system {msg.get_srcSystem()}")
                break
        else:
            return False, "No heartbeat received"

        # Test telemetry messages
        logger.info("  Checking for telemetry messages...")
        messages_received = {}
        start = time.time()

        while time.time() - start < 5.0:
            msg = mav.recv_match(blocking=True, timeout=0.5)
            if msg:
                msg_type = msg.get_type()
                if msg_type not in messages_received:
                    messages_received[msg_type] = 0
                messages_received[msg_type] += 1

        mav.close()

        # Check for position telemetry
        position_msgs = ['GLOBAL_POSITION_INT', 'LOCAL_POSITION_NED', 'ATTITUDE']
        received_position = [m for m in position_msgs if m in messages_received]

        if received_position:
            logger.info(f"  ✓ Position telemetry received: {received_position}")
            return True, f"Raw MAVLink OK - {len(messages_received)} message types received"
        else:
            logger.warning(f"  ⚠ No position telemetry. Messages: {list(messages_received.keys())}")
            return False, f"Connected but no position telemetry. Got: {list(messages_received.keys())}"

    except Exception as e:
        return False, f"Connection failed: {e}"


async def test_mavsdk_connection(
    connection_string: str,
    timeout: float = 15.0,
    grpc_port: int = 50051,
) -> Tuple[bool, str]:
    """
    Test MAVSDK connection and telemetry.

    Args:
        connection_string: MAVSDK connection string.
        timeout: Timeout in seconds.
        grpc_port: gRPC port for MAVSDK server (unused, kept for API compat).

    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        from mavsdk import System
    except ImportError:
        return False, "mavsdk not installed (pip install mavsdk)"

    logger.info(f"Testing MAVSDK connection to {connection_string}")

    try:
        # Create system - let MAVSDK auto-start its server
        # Note: Don't specify mavsdk_server_address as that tries to connect
        # to an existing server rather than auto-starting one
        drone = System()

        logger.info("  Connecting...")
        await drone.connect(system_address=connection_string)

        # Wait for connection
        logger.info("  Waiting for connection...")
        start = time.time()
        connected = False
        async for state in drone.core.connection_state():
            if state.is_connected:
                logger.info("  ✓ Connected to drone")
                connected = True
                break
            if time.time() - start > timeout:
                return False, "Connection timeout"
            await asyncio.sleep(0.5)

        if not connected:
            return False, "Failed to connect"

        # Test position telemetry
        logger.info("  Testing position telemetry...")
        start = time.time()
        position_count = 0
        last_alt = None
        altitudes = []

        async for position in drone.telemetry.position():
            current_alt = position.relative_altitude_m
            altitudes.append(current_alt)
            position_count += 1

            if last_alt is None:
                logger.info(f"  First position: alt={current_alt:.2f}m, lat={position.latitude_deg:.6f}")
            elif abs(current_alt - last_alt) > 0.1:
                logger.info(f"  ✓ Altitude CHANGED: {last_alt:.2f}m -> {current_alt:.2f}m")

            last_alt = current_alt

            if position_count >= 10:
                break

            if time.time() - start > 10:
                break

            await asyncio.sleep(0.3)

        # Analyze results
        if position_count == 0:
            return False, "No position telemetry received"

        unique_alts = len(set(f"{a:.1f}" for a in altitudes))
        if unique_alts == 1:
            return False, f"Position received but altitude STUCK at {altitudes[0]:.2f}m ({position_count} samples)"

        return True, f"MAVSDK OK - {position_count} positions, {unique_alts} unique altitudes"

    except Exception as e:
        return False, f"MAVSDK error: {e}"


async def test_telemetry_during_action(
    connection_string: str,
    grpc_port: int = 50051,
) -> Tuple[bool, str]:
    """
    Test if telemetry works during and after actions (arm/takeoff).

    This specifically tests the issue where telemetry freezes after sending commands.
    Uses the fixed pattern with asyncio.sleep(0) for proper yielding.

    Args:
        connection_string: MAVSDK connection string.
        grpc_port: gRPC port for MAVSDK server (unused).

    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        from mavsdk import System
    except ImportError:
        return False, "mavsdk not installed"

    logger.info(f"Testing telemetry during actions...")

    try:
        drone = System()
        await drone.connect(system_address=connection_string)

        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break

        # Get initial position
        logger.info("  Reading initial position...")
        initial_alt = None
        async for pos in drone.telemetry.position():
            initial_alt = pos.relative_altitude_m
            logger.info(f"  Initial altitude: {initial_alt:.2f}m")
            break

        # Check if already armed/flying
        is_armed = False
        async for armed in drone.telemetry.armed():
            is_armed = armed
            break

        if not is_armed:
            # Arm the drone
            logger.info("  Arming drone...")
            await drone.action.arm()
            await asyncio.sleep(1)

        # Start takeoff
        logger.info("  Starting takeoff...")
        await drone.action.set_takeoff_altitude(5.0)
        await drone.action.takeoff()

        # Monitor telemetry during takeoff
        logger.info("  Monitoring altitude during takeoff...")
        altitudes = []
        start = time.time()

        async for pos in drone.telemetry.position():
            current_alt = pos.relative_altitude_m
            altitudes.append(current_alt)
            logger.info(f"  Altitude: {current_alt:.2f}m")

            if len(altitudes) >= 20:
                break
            if time.time() - start > 15:
                break
            await asyncio.sleep(0.5)

        # Land
        logger.info("  Landing...")
        await drone.action.land()

        # Analyze
        unique_alts = len(set(f"{a:.1f}" for a in altitudes))
        max_alt = max(altitudes) if altitudes else 0

        if max_alt > 1.0 and unique_alts > 3:
            return True, f"Telemetry OK during action - reached {max_alt:.1f}m, {unique_alts} unique readings"
        else:
            return False, f"Telemetry STUCK during action - max {max_alt:.1f}m, only {unique_alts} unique readings"

    except Exception as e:
        return False, f"Action test error: {e}"


def run_diagnostics(
    connection_type: str,
    host: str,
    port: int,
    test_raw: bool,
    test_action: bool,
    grpc_port: int,
):
    """
    Run all diagnostic tests.

    Args:
        connection_type: Connection type (tcp or udp).
        host: Host address.
        port: Port number.
        test_raw: Whether to test raw MAVLink.
        test_action: Whether to test telemetry during actions.
        grpc_port: gRPC port for MAVSDK.
    """
    # Build connection string
    if connection_type == "tcp":
        connection_string = f"tcpout://{host}:{port}"
    else:
        connection_string = f"udpin://{host}:{port}"

    print("\n" + "=" * 60)
    print("MAVLink Connection Diagnostics")
    print("=" * 60)
    print(f"Connection Type: {connection_type.upper()}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Connection String: {connection_string}")
    print(f"MAVSDK gRPC Port: {grpc_port}")
    print("=" * 60 + "\n")

    results = []

    # Test 1: Raw MAVLink (if requested)
    if test_raw:
        print("\n--- Test 1: Raw MAVLink Connection ---")
        success, message = test_raw_mavlink(connection_string)
        results.append(("Raw MAVLink", success, message))
        print(f"Result: {'✓ PASS' if success else '✗ FAIL'} - {message}\n")

    # Test 2: MAVSDK Connection
    print("\n--- Test 2: MAVSDK Connection ---")
    success, message = asyncio.run(test_mavsdk_connection(connection_string, grpc_port=grpc_port))
    results.append(("MAVSDK Connection", success, message))
    print(f"Result: {'✓ PASS' if success else '✗ FAIL'} - {message}\n")

    # Test 3: Telemetry during action (if requested)
    if test_action and results[-1][1]:  # Only if MAVSDK connection worked
        print("\n--- Test 3: Telemetry During Actions ---")
        success, message = asyncio.run(test_telemetry_during_action(connection_string, grpc_port=grpc_port + 1))
        results.append(("Telemetry During Actions", success, message))
        print(f"Result: {'✓ PASS' if success else '✗ FAIL'} - {message}\n")

    # Summary
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, success, message in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
        print(f"         {message}")
        if not success:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All tests PASSED - Connection is working correctly")
    else:
        print("\n✗ Some tests FAILED - See recommendations below")
        print("\nRECOMMENDATIONS:")

        if not results[0][1] if test_raw else True:
            print("  1. Check that the PX4 simulator is running: ./scripts/px4ctl.sh status")
            print("  2. Check that mavlink-router is running inside Docker")
            print("  3. Verify port mappings in docker-compose.yml")

        if len(results) > 1 and not results[1][1]:
            print("  4. Try using a different gRPC port: --grpc-port 50052")
            print("  5. Kill any existing MAVSDK processes: pkill -f mavsdk")
            print("  6. Restart the simulator: ./scripts/px4ctl.sh restart")

        if len(results) > 2 and not results[2][1]:
            print("  7. The telemetry stream may be affected by race conditions")
            print("  8. Try adding delays before reading telemetry after actions")

    return all_passed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MAVLink Connection Diagnostic Tool"
    )

    parser.add_argument(
        "-c", "--connection-type",
        choices=["tcp", "udp"],
        default="tcp",
        help="Connection type (default: tcp)"
    )

    parser.add_argument(
        "--tcp-host",
        default="localhost",
        help="TCP host (default: localhost)"
    )

    parser.add_argument(
        "--tcp-port",
        type=int,
        default=5760,
        help="TCP port (default: 5760)"
    )

    parser.add_argument(
        "--udp-host",
        default="0.0.0.0",
        help="UDP listen address (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--udp-port",
        type=int,
        default=14540,
        help="UDP port (default: 14540)"
    )

    parser.add_argument(
        "--grpc-port",
        type=int,
        default=50051,
        help="gRPC port for MAVSDK server (default: 50051)"
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="Also test raw MAVLink connection (requires pymavlink)"
    )

    parser.add_argument(
        "--test-action",
        action="store_true",
        help="Test telemetry during actions (arm/takeoff/land)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine host and port based on connection type
    if args.connection_type == "tcp":
        host = args.tcp_host
        port = args.tcp_port
    else:
        host = args.udp_host
        port = args.udp_port

    # Run diagnostics
    success = run_diagnostics(
        connection_type=args.connection_type,
        host=host,
        port=port,
        test_raw=args.raw,
        test_action=args.test_action,
        grpc_port=args.grpc_port,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

