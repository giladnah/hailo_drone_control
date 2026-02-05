#!/usr/bin/env python3
"""
telemetry_manager.py - Thread-safe Telemetry Manager for MAVSDK

This module provides a proper way to read telemetry while executing commands.
The key insight is that MAVSDK telemetry async iterators can starve command
execution if they don't yield control properly.

Problem:
    When using `async for pos in drone.telemetry.position():` with delays,
    the event loop gives priority to the telemetry loop, preventing commands
    (arm, takeoff, etc.) from executing properly.

Solution:
    Use `await asyncio.sleep(0)` to immediately yield after each telemetry read,
    or use this TelemetryManager which handles it correctly.

Usage:
    from examples.common.telemetry_manager import TelemetryManager

    async def main():
        drone = System()
        await drone.connect(...)

        # Create telemetry manager
        telemetry = TelemetryManager(drone)
        await telemetry.start()

        # Now commands work properly while telemetry updates in background
        await drone.action.arm()
        await drone.action.takeoff()

        # Access latest telemetry (thread-safe)
        position = telemetry.position
        print(f"Altitude: {position.altitude_m:.2f}m")

        # Stop when done
        await telemetry.stop()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Any
import time

logger = logging.getLogger(__name__)


@dataclass
class PositionData:
    """Latest position telemetry data."""
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    absolute_altitude_m: float = 0.0
    relative_altitude_m: float = 0.0
    timestamp: float = 0.0

    @property
    def altitude_m(self) -> float:
        """Alias for relative_altitude_m."""
        return self.relative_altitude_m


@dataclass
class AttitudeData:
    """Latest attitude telemetry data."""
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    timestamp: float = 0.0


@dataclass
class BatteryData:
    """Latest battery telemetry data."""
    voltage_v: float = 0.0
    remaining_percent: float = 100.0
    timestamp: float = 0.0


@dataclass
class FlightStateData:
    """Latest flight state data."""
    armed: bool = False
    in_air: bool = False
    flight_mode: str = "UNKNOWN"
    landed_state: str = "UNKNOWN"
    timestamp: float = 0.0


class TelemetryManager:
    """
    Manages telemetry subscriptions without blocking command execution.

    This class runs telemetry readers in background tasks that properly
    yield control to the event loop, allowing commands to execute.

    Attributes:
        position: Latest position data.
        attitude: Latest attitude data.
        battery: Latest battery data.
        flight_state: Latest flight state data.

    Example:
        telemetry = TelemetryManager(drone)
        await telemetry.start()

        # Telemetry is now updating in background
        print(f"Altitude: {telemetry.position.altitude_m:.2f}m")

        # Commands work properly
        await drone.action.arm()

        await telemetry.stop()
    """

    def __init__(self, drone: "System", update_rate_hz: float = 10.0):
        """
        Initialize the telemetry manager.

        Args:
            drone: MAVSDK System instance.
            update_rate_hz: Target update rate (Hz). Higher = more CPU usage.
        """
        self._drone = drone
        self._update_interval = 1.0 / update_rate_hz
        self._stop_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []
        self._started = False
        self._callbacks: List[Callable[[str, Any], None]] = []

        # Telemetry data (updated by background tasks)
        self.position = PositionData()
        self.attitude = AttitudeData()
        self.battery = BatteryData()
        self.flight_state = FlightStateData()

    def add_callback(self, callback: Callable[[str, Any], None]) -> None:
        """
        Add a callback for telemetry updates.

        Args:
            callback: Function called with (telemetry_type, data) on each update.
                      telemetry_type is one of: "position", "attitude", "battery", "flight_state"
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, Any], None]) -> None:
        """Remove a previously added callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, telemetry_type: str, data: Any) -> None:
        """Notify all callbacks of a telemetry update."""
        for callback in self._callbacks:
            try:
                callback(telemetry_type, data)
            except Exception as e:
                logger.warning(f"Telemetry callback error: {e}")

    async def start(self) -> None:
        """
        Start background telemetry tasks.

        Call this after connecting to the drone.
        """
        if self._started:
            logger.warning("TelemetryManager already started")
            return

        self._stop_event.clear()

        # Create background tasks for each telemetry type
        self._tasks = [
            asyncio.create_task(self._read_position()),
            asyncio.create_task(self._read_attitude()),
            asyncio.create_task(self._read_battery()),
            asyncio.create_task(self._read_flight_state()),
        ]

        self._started = True
        logger.debug("TelemetryManager started")

        # Wait a moment for first data
        await asyncio.sleep(0.2)

    async def stop(self) -> None:
        """Stop background telemetry tasks."""
        if not self._started:
            return

        self._stop_event.set()

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to finish
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._started = False
        logger.debug("TelemetryManager stopped")

    @property
    def is_running(self) -> bool:
        """Check if telemetry manager is running."""
        return self._started

    async def _read_position(self) -> None:
        """Background task to read position telemetry."""
        try:
            async for pos in self._drone.telemetry.position():
                if self._stop_event.is_set():
                    break

                self.position = PositionData(
                    latitude_deg=pos.latitude_deg,
                    longitude_deg=pos.longitude_deg,
                    absolute_altitude_m=pos.absolute_altitude_m,
                    relative_altitude_m=pos.relative_altitude_m,
                    timestamp=time.time(),
                )
                self._notify_callbacks("position", self.position)

                # Critical: yield control immediately to allow commands to execute
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Position telemetry error: {e}")

    async def _read_attitude(self) -> None:
        """Background task to read attitude telemetry."""
        try:
            async for att in self._drone.telemetry.attitude_euler():
                if self._stop_event.is_set():
                    break

                self.attitude = AttitudeData(
                    roll_deg=att.roll_deg,
                    pitch_deg=att.pitch_deg,
                    yaw_deg=att.yaw_deg,
                    timestamp=time.time(),
                )
                self._notify_callbacks("attitude", self.attitude)

                # Critical: yield control immediately
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Attitude telemetry error: {e}")

    async def _read_battery(self) -> None:
        """Background task to read battery telemetry."""
        try:
            async for bat in self._drone.telemetry.battery():
                if self._stop_event.is_set():
                    break

                self.battery = BatteryData(
                    voltage_v=bat.voltage_v,
                    remaining_percent=bat.remaining_percent,
                    timestamp=time.time(),
                )
                self._notify_callbacks("battery", self.battery)

                # Yield control
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Battery telemetry error: {e}")

    async def _read_flight_state(self) -> None:
        """Background task to read flight state telemetry."""
        try:
            # These are separate streams, so we need to read them with tasks
            armed_task = asyncio.create_task(self._read_armed())
            in_air_task = asyncio.create_task(self._read_in_air())
            flight_mode_task = asyncio.create_task(self._read_flight_mode())
            landed_state_task = asyncio.create_task(self._read_landed_state())

            await asyncio.gather(
                armed_task, in_air_task, flight_mode_task, landed_state_task,
                return_exceptions=True
            )

        except asyncio.CancelledError:
            pass

    async def _read_armed(self) -> None:
        """Read armed state."""
        try:
            async for armed in self._drone.telemetry.armed():
                if self._stop_event.is_set():
                    break
                self.flight_state.armed = armed
                self.flight_state.timestamp = time.time()
                self._notify_callbacks("flight_state", self.flight_state)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Armed telemetry error: {e}")

    async def _read_in_air(self) -> None:
        """Read in_air state."""
        try:
            async for in_air in self._drone.telemetry.in_air():
                if self._stop_event.is_set():
                    break
                self.flight_state.in_air = in_air
                self.flight_state.timestamp = time.time()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"In-air telemetry error: {e}")

    async def _read_flight_mode(self) -> None:
        """Read flight mode."""
        try:
            async for mode in self._drone.telemetry.flight_mode():
                if self._stop_event.is_set():
                    break
                self.flight_state.flight_mode = str(mode)
                self.flight_state.timestamp = time.time()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Flight mode telemetry error: {e}")

    async def _read_landed_state(self) -> None:
        """Read landed state."""
        try:
            async for state in self._drone.telemetry.landed_state():
                if self._stop_event.is_set():
                    break
                self.flight_state.landed_state = str(state)
                self.flight_state.timestamp = time.time()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Landed state telemetry error: {e}")

    def get_summary(self) -> dict:
        """
        Get a summary of current telemetry state.

        Returns:
            dict: Current telemetry values.
        """
        return {
            "position": {
                "lat": self.position.latitude_deg,
                "lon": self.position.longitude_deg,
                "alt_m": self.position.relative_altitude_m,
            },
            "attitude": {
                "roll_deg": self.attitude.roll_deg,
                "pitch_deg": self.attitude.pitch_deg,
                "yaw_deg": self.attitude.yaw_deg,
            },
            "battery": {
                "voltage_v": self.battery.voltage_v,
                "remaining_pct": self.battery.remaining_percent,
            },
            "flight_state": {
                "armed": self.flight_state.armed,
                "in_air": self.flight_state.in_air,
                "mode": self.flight_state.flight_mode,
                "landed": self.flight_state.landed_state,
            },
        }


async def wait_for_altitude(
    telemetry: TelemetryManager,
    target_altitude: float,
    tolerance: float = 0.5,
    timeout: float = 30.0,
) -> bool:
    """
    Wait for drone to reach a target altitude.

    Args:
        telemetry: TelemetryManager instance.
        target_altitude: Target altitude in meters.
        tolerance: Altitude tolerance in meters.
        timeout: Maximum wait time in seconds.

    Returns:
        bool: True if altitude reached within timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        current_alt = telemetry.position.relative_altitude_m
        if abs(current_alt - target_altitude) <= tolerance:
            return True
        await asyncio.sleep(0.2)
    return False


async def wait_for_landed(
    telemetry: TelemetryManager,
    timeout: float = 60.0,
) -> bool:
    """
    Wait for drone to land.

    Args:
        telemetry: TelemetryManager instance.
        timeout: Maximum wait time in seconds.

    Returns:
        bool: True if landed within timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        if telemetry.flight_state.landed_state == "ON_GROUND":
            return True
        await asyncio.sleep(0.2)
    return False

