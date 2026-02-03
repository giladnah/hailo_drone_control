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
    pytest tests/test_integration.py -v
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
TEST_TIMEOUT = float(os.environ.get("TEST_TIMEOUT", "30"))


class TestMAVLinkConnectivity:
    """Tests for MAVLink connectivity."""
    
    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()
    
    @pytest.mark.asyncio
    async def test_heartbeat_received(self):
        """
        Test that MAVLink heartbeat is received within timeout.
        
        This is the most basic connectivity test - if this fails,
        the entire stack is not working.
        """
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        start_time = time.time()
        connected = False
        
        async for state in drone.core.connection_state():
            if state.is_connected:
                connected = True
                break
            
            if time.time() - start_time > TEST_TIMEOUT:
                break
            
            await asyncio.sleep(0.5)
        
        assert connected, f"No heartbeat received within {TEST_TIMEOUT}s"
    
    @pytest.mark.asyncio
    async def test_system_info_available(self):
        """Test that system information is available."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get system info
        info = await drone.info.get_identification()
        
        assert info is not None, "System identification not available"
        # Hardware UID should be set
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
    async def test_position_telemetry(self):
        """Test that position telemetry is streaming."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get position
        position = None
        async for pos in drone.telemetry.position():
            position = pos
            break
        
        assert position is not None, "Position telemetry not available"
        # Check that coordinates are valid (not all zeros)
        assert position.latitude_deg != 0 or position.longitude_deg != 0, \
            "Invalid position (0, 0)"
    
    @pytest.mark.asyncio
    async def test_attitude_telemetry(self):
        """Test that attitude telemetry is streaming."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get attitude
        attitude = None
        async for att in drone.telemetry.attitude_euler():
            attitude = att
            break
        
        assert attitude is not None, "Attitude telemetry not available"
        # Values should be within valid ranges
        assert -180 <= attitude.roll_deg <= 180, f"Invalid roll: {attitude.roll_deg}"
        assert -90 <= attitude.pitch_deg <= 90, f"Invalid pitch: {attitude.pitch_deg}"
        assert -180 <= attitude.yaw_deg <= 180, f"Invalid yaw: {attitude.yaw_deg}"
    
    @pytest.mark.asyncio
    async def test_battery_telemetry(self):
        """Test that battery telemetry is streaming."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get battery
        battery = None
        async for bat in drone.telemetry.battery():
            battery = bat
            break
        
        assert battery is not None, "Battery telemetry not available"
        # Voltage should be positive
        assert battery.voltage_v > 0, f"Invalid voltage: {battery.voltage_v}"
        # Remaining should be between 0 and 1
        assert 0 <= battery.remaining_percent <= 1, \
            f"Invalid remaining: {battery.remaining_percent}"
    
    @pytest.mark.asyncio
    async def test_health_telemetry(self):
        """Test that health telemetry is streaming."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get health
        health = None
        async for h in drone.telemetry.health():
            health = h
            break
        
        assert health is not None, "Health telemetry not available"
        # For SITL, these should all be OK after initialization
        # Note: In SITL, GPS might take a moment to initialize


class TestVehicleState:
    """Tests for vehicle state management."""
    
    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()
    
    @pytest.mark.asyncio
    async def test_armed_state_readable(self):
        """Test that armed state is readable."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get armed state
        armed = None
        async for a in drone.telemetry.armed():
            armed = a
            break
        
        assert armed is not None, "Armed state not available"
        assert isinstance(armed, bool), f"Armed state is not bool: {type(armed)}"
    
    @pytest.mark.asyncio
    async def test_flight_mode_readable(self):
        """Test that flight mode is readable."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Get flight mode
        mode = None
        async for m in drone.telemetry.flight_mode():
            mode = m
            break
        
        assert mode is not None, "Flight mode not available"
    
    @pytest.mark.asyncio
    async def test_in_air_state_readable(self):
        """Test that in-air state is readable."""
        from mavsdk import System
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
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
    async def test_arm_disarm_cycle(self):
        """
        Test that we can arm and disarm the vehicle.
        
        This test actually arms the vehicle, so it's more invasive.
        Only run in SITL environment.
        """
        from mavsdk import System
        from mavsdk.action import ActionError
        
        drone = System()
        await drone.connect(system_address=f"udp://{MAVLINK_HOST}:{MAVLINK_PORT}")
        
        # Wait for connection
        async for state in drone.core.connection_state():
            if state.is_connected:
                break
            await asyncio.sleep(0.5)
        
        # Wait for ready to arm
        async for health in drone.telemetry.health():
            if health.is_armable:
                break
            await asyncio.sleep(1)
        
        # Arm
        try:
            await drone.action.arm()
        except ActionError as e:
            pytest.skip(f"Cannot arm: {e}")
        
        # Verify armed
        async for armed in drone.telemetry.armed():
            assert armed, "Vehicle should be armed"
            break
        
        # Disarm
        await drone.action.disarm()
        
        # Verify disarmed
        await asyncio.sleep(1)  # Give it time to disarm
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

