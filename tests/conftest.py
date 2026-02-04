"""
Pytest configuration and shared fixtures for PX4 tests.

This module provides:
- Async test support via pytest-asyncio
- Shared fixtures for drone connection
- Test markers configuration
"""

import asyncio
import os
import time
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Test configuration from environment
MAVLINK_HOST = os.environ.get("MAVLINK_HOST", "localhost")
MAVLINK_PORT = int(os.environ.get("MAVLINK_PORT", "14540"))
TEST_TIMEOUT = float(os.environ.get("TEST_TIMEOUT", "60"))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers",
        "flight: mark test as requiring actual flight"
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for all tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def drone():
    """
    Fixture providing a connected MAVSDK drone instance.

    Yields:
        mavsdk.System: Connected drone instance.
    """
    from mavsdk import System

    drone = System()
    await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")

    # Wait for connection
    start_time = time.time()
    async for state in drone.core.connection_state():
        if state.is_connected:
            break
        if time.time() - start_time > TEST_TIMEOUT:
            pytest.fail("Connection timeout")
        await asyncio.sleep(0.5)

    yield drone

    # Cleanup - ensure disarmed
    try:
        async for armed in drone.telemetry.armed():
            if armed:
                # Try to land first
                try:
                    await drone.action.land()
                    await asyncio.sleep(5)
                except Exception:
                    pass
                # Disarm
                try:
                    await drone.action.disarm()
                except Exception:
                    pass
            break
    except Exception:
        pass


@pytest_asyncio.fixture
async def ready_drone(drone):
    """
    Fixture providing a drone that is ready for flight (GPS lock etc).

    Args:
        drone: Connected drone from drone fixture.

    Yields:
        mavsdk.System: Flight-ready drone instance.
    """
    # Wait for GPS and home position
    start_time = time.time()

    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break
        if time.time() - start_time > TEST_TIMEOUT:
            pytest.skip("Drone not ready for flight (no GPS)")
        await asyncio.sleep(1)

    # Ensure disarmed
    async for armed in drone.telemetry.armed():
        if armed:
            try:
                await drone.action.disarm()
            except Exception:
                pytest.skip("Could not disarm drone")
        break

    yield drone


@pytest.fixture
def mavlink_config():
    """
    Fixture providing MAVLink configuration.

    Returns:
        dict: MAVLink host and port configuration.
    """
    return {
        "host": MAVLINK_HOST,
        "port": MAVLINK_PORT,
        "address": f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}"
    }


# Configure pytest-asyncio
pytest_plugins = ['pytest_asyncio']

