"""
Integration tests for the PX4 development environment.

These tests verify end-to-end connectivity and functionality:
- MAVLink heartbeat reception
- Telemetry data streaming
- Vehicle state transitions
- Arm/disarm commands

Requirements:
    - PX4 SITL running (use ./scripts/px4ctl.sh start)
    - MAVLink router configured

Usage:
    pytest tests/test_integration.py -v --timeout=60
    ./scripts/px4ctl.sh test
"""

import asyncio
import os
import sys
import time
from typing import Optional

import pytest


# Test configuration from environment
MAVLINK_HOST = os.environ.get("MAVLINK_HOST", "localhost")
MAVLINK_PORT = int(os.environ.get("MAVLINK_PORT", "14540"))
CONNECTION_TIMEOUT = float(os.environ.get("CONNECTION_TIMEOUT", "15"))


def get_connection_string():
    """Get MAVSDK connection string based on environment."""
    # Use udpin:// since mavlink-router pushes data to us
    return f"udpin://0.0.0.0:{MAVLINK_PORT}"


class TestMAVLinkConnectivity:
    """Tests for MAVLink connectivity."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_heartbeat_received(self):
        """
        Test that MAVLink heartbeat is received within timeout.

        This is the most basic connectivity test - if this fails,
        the entire stack is not working.
        """
        from mavsdk import System

        drone = System()
        connection = get_connection_string()
        print(f"Connecting to {connection}...")
        await drone.connect(system_address=connection)

        start_time = time.time()
        connected = False

        async for state in drone.core.connection_state():
            if state.is_connected:
                connected = True
                print("Connected!")
                break

            if time.time() - start_time > CONNECTION_TIMEOUT:
                break

            await asyncio.sleep(0.5)

        assert connected, f"No heartbeat received within {CONNECTION_TIMEOUT}s"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_system_info_available(self):
        """Test that system information is available."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection with timeout
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get system info with timeout
        info = await asyncio.wait_for(drone.info.get_identification(), timeout=10)

        assert info is not None, "System identification not available"
        assert info.hardware_uid != "", "Hardware UID is empty"


class TestTelemetry:
    """Tests for telemetry data streaming."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_position_telemetry(self):
        """Test that position telemetry is streaming."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection with timeout
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get position with timeout
        position = None
        start_time = time.time()
        async for pos in drone.telemetry.position():
            position = pos
            break

        assert position is not None, "Position telemetry not available"
        assert position.latitude_deg != 0 or position.longitude_deg != 0, \
            "Invalid position (0, 0)"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_attitude_telemetry(self):
        """Test that attitude telemetry is streaming."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get attitude
        attitude = None
        async for att in drone.telemetry.attitude_euler():
            attitude = att
            break

        assert attitude is not None, "Attitude telemetry not available"
        assert -180 <= attitude.roll_deg <= 180, f"Invalid roll: {attitude.roll_deg}"
        assert -90 <= attitude.pitch_deg <= 90, f"Invalid pitch: {attitude.pitch_deg}"
        assert -180 <= attitude.yaw_deg <= 180, f"Invalid yaw: {attitude.yaw_deg}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_battery_telemetry(self):
        """Test that battery telemetry is streaming."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get battery
        battery = None
        async for bat in drone.telemetry.battery():
            battery = bat
            break

        assert battery is not None, "Battery telemetry not available"
        assert battery.voltage_v > 0, f"Invalid voltage: {battery.voltage_v}"
        # remaining_percent is 0-100, not 0-1
        assert 0 <= battery.remaining_percent <= 100, \
            f"Invalid remaining: {battery.remaining_percent}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_health_telemetry(self):
        """Test that health telemetry is streaming."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get health
        health = None
        async for h in drone.telemetry.health():
            health = h
            break

        assert health is not None, "Health telemetry not available"


class TestVehicleState:
    """Tests for vehicle state management."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_armed_state_readable(self):
        """Test that armed state is readable."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get armed state
        armed = None
        async for a in drone.telemetry.armed():
            armed = a
            break

        assert armed is not None, "Armed state not available"
        assert isinstance(armed, bool), f"Armed state is not bool: {type(armed)}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_flight_mode_readable(self):
        """Test that flight mode is readable."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get flight mode
        mode = None
        async for m in drone.telemetry.flight_mode():
            mode = m
            break

        assert mode is not None, "Flight mode not available"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_in_air_state_readable(self):
        """Test that in-air state is readable."""
        from mavsdk import System

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Get in-air state
        in_air = None
        async for ia in drone.telemetry.in_air():
            in_air = ia
            break

        assert in_air is not None, "In-air state not available"
        assert isinstance(in_air, bool), f"In-air state is not bool: {type(in_air)}"


class TestActions:
    """Tests for vehicle actions (arm/disarm)."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_arm_disarm_cycle(self):
        """
        Test that we can arm and disarm the vehicle.

        This test actually arms the vehicle, so it's more invasive.
        Only run in SITL environment.
        """
        from mavsdk import System
        from mavsdk.action import ActionError

        drone = System()
        await drone.connect(system_address=get_connection_string())

        # Wait for connection
        start_time = time.time()
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            if time.time() - start_time > CONNECTION_TIMEOUT:
                pytest.fail("Connection timeout")
            await asyncio.sleep(0.5)

        # Wait for ready to arm with timeout
        start_time = time.time()
        async for health in drone.telemetry.health():
            if health.is_armable:
                break
            if time.time() - start_time > 20:
                pytest.skip("Vehicle not armable within timeout")
            await asyncio.sleep(1)

        # Arm with timeout
        try:
            await asyncio.wait_for(drone.action.arm(), timeout=5)
        except (asyncio.TimeoutError, ActionError) as e:
            pytest.skip(f"Cannot arm: {e}")

        # Verify armed
        async for armed in drone.telemetry.armed():
            assert armed, "Vehicle should be armed"
            break

        # Disarm with timeout
        await asyncio.wait_for(drone.action.disarm(), timeout=5)

        # Verify disarmed
        await asyncio.sleep(1)
        async for armed in drone.telemetry.armed():
            assert not armed, "Vehicle should be disarmed"
            break


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as async"
    )


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "--tb=short"])

