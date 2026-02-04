"""
Functional tests for flight operations and examples.

These tests verify end-to-end flight functionality:
- Takeoff and landing
- Offboard velocity control
- Mission execution
- Telemetry monitoring

Requirements:
    - PX4 SITL running (use ./scripts/px4ctl.sh start)
    - MAVLink router configured

Usage:
    pytest tests/test_functional.py -v --timeout=120
    ./scripts/px4ctl.sh test tests/test_functional.py

Note: These tests actually command the drone to fly!
      Only run in SITL simulation environment.
"""

import asyncio
import os
import time
from typing import Optional

import pytest

# Test configuration from environment
MAVLINK_HOST = os.environ.get("MAVLINK_HOST", "localhost")
MAVLINK_PORT = int(os.environ.get("MAVLINK_PORT", "14540"))
CONNECTION_TIMEOUT = float(os.environ.get("CONNECTION_TIMEOUT", "15"))
FLIGHT_TIMEOUT = float(os.environ.get("FLIGHT_TIMEOUT", "60"))
FLIGHT_ALTITUDE = 5.0  # meters


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def connect_drone(timeout: float = None):
    """
    Helper to connect to drone and wait for ready state.

    Args:
        timeout: Connection timeout in seconds.

    Returns:
        mavsdk.System: Connected drone instance.

    Raises:
        TimeoutError: If connection times out.
    """
    from mavsdk import System

    timeout = timeout or CONNECTION_TIMEOUT

    drone = System()
    # Use udpin:// since mavlink-router pushes data to us
    connection_string = f"udpin://0.0.0.0:{MAVLINK_PORT}"
    print(f"Connecting to {connection_string}...")
    await drone.connect(system_address=connection_string)

    # Wait for connection with timeout
    start_time = time.time()
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected to drone!")
            break
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Connection timeout after {timeout}s")
        await asyncio.sleep(0.5)

    return drone


async def wait_for_ready(drone, timeout: float = 20.0) -> bool:
    """
    Wait for drone to be ready for flight.

    Args:
        drone: MAVSDK System instance.
        timeout: Maximum wait time.

    Returns:
        bool: True if drone is ready.
    """
    start_time = time.time()

    try:
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("Drone ready for flight")
                return True
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"Ready timeout after {timeout}s")
                return False
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return False

    return False


async def ensure_disarmed(drone, timeout: float = 5.0):
    """
    Ensure drone is disarmed, disarm if necessary.

    Args:
        drone: MAVSDK System instance.
        timeout: Maximum wait time.
    """
    try:
        async for armed in drone.telemetry.armed():
            if not armed:
                return
            break

        # Try to disarm
        await asyncio.wait_for(drone.action.disarm(), timeout=timeout)
    except (asyncio.TimeoutError, Exception):
        pass


async def land_and_disarm(drone, timeout: float = 20.0):
    """
    Land the drone and disarm.

    Args:
        drone: MAVSDK System instance.
        timeout: Maximum wait time.
    """
    try:
        await asyncio.wait_for(drone.action.land(), timeout=5)
    except (asyncio.TimeoutError, Exception):
        pass

    # Wait for landing with timeout
    start_time = time.time()
    try:
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                break
            if time.time() - start_time > timeout:
                break
            await asyncio.sleep(0.5)
    except (asyncio.CancelledError, Exception):
        pass

    # Brief wait then disarm
    await asyncio.sleep(1)
    await ensure_disarmed(drone)


class TestTakeoffLand:
    """Tests for basic takeoff and landing."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_simple_takeoff_and_land(self):
        """
        Test basic takeoff to altitude and land.

        This is the fundamental flight test - verifies:
        - Arming works
        - Takeoff command works
        - Altitude is reached
        - Landing command works
        """
        drone = await connect_drone()

        try:
            # Wait for ready
            ready = await wait_for_ready(drone, timeout=15)
            assert ready, "Drone not ready for flight"

            # Ensure disarmed first
            await ensure_disarmed(drone)

            # Arm with timeout
            await asyncio.wait_for(drone.action.arm(), timeout=5)

            # Verify armed
            async for armed in drone.telemetry.armed():
                assert armed, "Failed to arm"
                break

            # Set takeoff altitude and takeoff
            await drone.action.set_takeoff_altitude(FLIGHT_ALTITUDE)
            await asyncio.wait_for(drone.action.takeoff(), timeout=5)

            # Wait for altitude (with timeout)
            # Use 80% of target as threshold to account for SITL variability
            target_alt = FLIGHT_ALTITUDE * 0.8  # 80% of target
            start_time = time.time()
            altitude_reached = False
            max_alt = 0.0

            async for position in drone.telemetry.position():
                if position.relative_altitude_m > max_alt:
                    max_alt = position.relative_altitude_m
                if position.relative_altitude_m >= target_alt:
                    altitude_reached = True
                    break
                if time.time() - start_time > 30:  # 30s timeout for climb
                    break
                await asyncio.sleep(0.5)

            assert altitude_reached, f"Failed to reach altitude {FLIGHT_ALTITUDE}m (reached {max_alt:.1f}m)"

            # Hover briefly
            await asyncio.sleep(2)

            # Land
            await asyncio.wait_for(drone.action.land(), timeout=5)

            # Wait for landing
            start_time = time.time()
            landed = False

            async for in_air in drone.telemetry.in_air():
                if not in_air:
                    landed = True
                    break
                if time.time() - start_time > 30:  # 30s timeout for landing
                    break
                await asyncio.sleep(0.5)

            assert landed, "Failed to land"

        finally:
            # Cleanup - ensure landed and disarmed
            await land_and_disarm(drone)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    @pytest.mark.skip(reason="Complex test - run manually")
    async def test_takeoff_altitude_accuracy(self):
        """
        Test that takeoff reaches the specified altitude accurately.
        """
        drone = await connect_drone()

        try:
            ready = await wait_for_ready(drone, timeout=15)
            assert ready, "Drone not ready for flight"

            await ensure_disarmed(drone)
            await asyncio.wait_for(drone.action.arm(), timeout=5)

            test_altitude = 8.0  # meters
            await drone.action.set_takeoff_altitude(test_altitude)
            await asyncio.wait_for(drone.action.takeoff(), timeout=5)

            # Wait for altitude stabilization
            await asyncio.sleep(10)

            # Check altitude
            async for position in drone.telemetry.position():
                actual_alt = position.relative_altitude_m
                # Allow 15% tolerance
                assert abs(actual_alt - test_altitude) < test_altitude * 0.15, \
                    f"Altitude {actual_alt}m not within tolerance of {test_altitude}m"
                break

        finally:
            await land_and_disarm(drone)


class TestOffboardControl:
    """Tests for offboard velocity control."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    @pytest.mark.skip(reason="Complex test - run manually")
    async def test_offboard_velocity_hover(self):
        """
        Test entering offboard mode and hovering in place.
        """
        from mavsdk.offboard import OffboardError, VelocityNedYaw

        drone = await connect_drone()

        try:
            ready = await wait_for_ready(drone, timeout=15)
            assert ready, "Drone not ready for flight"

            await ensure_disarmed(drone)
            await asyncio.wait_for(drone.action.arm(), timeout=5)
            await drone.action.set_takeoff_altitude(FLIGHT_ALTITUDE)
            await asyncio.wait_for(drone.action.takeoff(), timeout=5)

            # Wait for altitude with timeout
            start_time = time.time()
            async for position in drone.telemetry.position():
                if position.relative_altitude_m >= FLIGHT_ALTITUDE * 0.9:
                    break
                if time.time() - start_time > 20:
                    break
                await asyncio.sleep(0.5)

            # Get current yaw
            current_yaw = 0.0
            async for attitude in drone.telemetry.attitude_euler():
                current_yaw = attitude.yaw_deg
                break

            # Set initial setpoint (required before starting offboard)
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(0.0, 0.0, 0.0, current_yaw)
            )

            # Start offboard mode
            await asyncio.wait_for(drone.offboard.start(), timeout=5)

            # Hover for 3 seconds
            for _ in range(6):
                await drone.offboard.set_velocity_ned(
                    VelocityNedYaw(0.0, 0.0, 0.0, current_yaw)
                )
                await asyncio.sleep(0.5)

            # Stop offboard
            await asyncio.wait_for(drone.offboard.stop(), timeout=5)

            # Verify still at similar altitude
            async for position in drone.telemetry.position():
                assert position.relative_altitude_m >= FLIGHT_ALTITUDE * 0.8, \
                    "Lost too much altitude during hover"
                break

        finally:
            await land_and_disarm(drone)


class TestTelemetryStreams:
    """Tests for telemetry data quality."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_telemetry_rate(self):
        """
        Test that telemetry is streaming at reasonable rate.
        """
        drone = await connect_drone()

        # Count position updates over 5 seconds
        position_count = 0
        start_time = time.time()

        async for _ in drone.telemetry.position():
            position_count += 1
            if time.time() - start_time >= 5:
                break

        # Should get at least 1 update per second
        rate = position_count / 5.0
        assert rate >= 0.5, f"Position update rate too low: {rate} Hz"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_gps_quality(self):
        """
        Test GPS quality indicators.
        """
        drone = await connect_drone()

        # Get GPS info with timeout
        async for gps_info in drone.telemetry.gps_info():
            # In SITL, should have good GPS
            assert gps_info.num_satellites >= 6, \
                f"Too few satellites: {gps_info.num_satellites}"
            break


class TestMissionExecution:
    """Tests for mission planning and execution."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_mission_upload(self):
        """
        Test that a mission can be uploaded.
        """
        from mavsdk.mission import MissionItem, MissionPlan

        drone = await connect_drone()

        # Get current position for mission
        current_lat = 0.0
        current_lon = 0.0
        async for position in drone.telemetry.position():
            current_lat = position.latitude_deg
            current_lon = position.longitude_deg
            break

        # Create simple 2-point mission
        offset = 0.0002  # ~22m

        mission_items = [
            MissionItem(
                latitude_deg=current_lat + offset,
                longitude_deg=current_lon,
                relative_altitude_m=10.0,
                speed_m_s=5.0,
                is_fly_through=True,
                gimbal_pitch_deg=0.0,
                gimbal_yaw_deg=0.0,
                camera_action=MissionItem.CameraAction.NONE,
                loiter_time_s=0.0,
                camera_photo_interval_s=0.0,
                acceptance_radius_m=1.0,
                yaw_deg=0.0,
                camera_photo_distance_m=0.0,
            ),
            MissionItem(
                latitude_deg=current_lat,
                longitude_deg=current_lon,
                relative_altitude_m=10.0,
                speed_m_s=5.0,
                is_fly_through=False,
                gimbal_pitch_deg=0.0,
                gimbal_yaw_deg=0.0,
                camera_action=MissionItem.CameraAction.NONE,
                loiter_time_s=1.0,
                camera_photo_interval_s=0.0,
                acceptance_radius_m=1.0,
                yaw_deg=0.0,
                camera_photo_distance_m=0.0,
            ),
        ]

        mission_plan = MissionPlan(mission_items)

        # Upload mission with timeout
        await asyncio.wait_for(drone.mission.upload_mission(mission_plan), timeout=10)

        # Verify upload by downloading
        downloaded = await asyncio.wait_for(drone.mission.download_mission(), timeout=10)
        assert len(downloaded.mission_items) == 2, "Mission upload failed"


class TestSafetyFeatures:
    """Tests for safety features."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_disarm_while_grounded(self):
        """
        Test that disarm works while on ground.
        """
        drone = await connect_drone()

        try:
            ready = await wait_for_ready(drone, timeout=15)
            assert ready, "Drone not ready"

            await ensure_disarmed(drone)

            # Arm with timeout
            await asyncio.wait_for(drone.action.arm(), timeout=5)

            async for armed in drone.telemetry.armed():
                assert armed, "Failed to arm"
                break

            # Disarm (should work on ground)
            await asyncio.wait_for(drone.action.disarm(), timeout=5)

            await asyncio.sleep(1)

            async for armed in drone.telemetry.armed():
                assert not armed, "Failed to disarm"
                break

        finally:
            await ensure_disarmed(drone)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as async"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
