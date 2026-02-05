"""
Common utilities for PX4 example scripts.

This package provides shared functionality used across multiple examples,
reducing code duplication and ensuring consistent behavior.

Modules:
    drone_helpers: Common drone operations (connect, takeoff, land, etc.)
    telemetry_manager: Thread-safe telemetry management for MAVSDK.
"""

from .drone_helpers import (
    DroneConnection,
    TelemetrySnapshot,
    connect_drone,
    wait_for_gps,
    preflight_check,
    arm_and_takeoff,
    land_and_disarm,
    safe_land,
    emergency_stop,
    get_telemetry_snapshot,
    setup_logging,
    create_argument_parser,
    get_connection_string_from_args,
    is_shutdown_requested,
    setup_signal_handlers,
)

from .telemetry_manager import (
    TelemetryManager,
    PositionData,
    AttitudeData,
    BatteryData,
    FlightStateData,
    wait_for_altitude,
    wait_for_landed,
)

__all__ = [
    # drone_helpers
    "DroneConnection",
    "TelemetrySnapshot",
    "connect_drone",
    "wait_for_gps",
    "preflight_check",
    "arm_and_takeoff",
    "land_and_disarm",
    "safe_land",
    "emergency_stop",
    "get_telemetry_snapshot",
    "setup_logging",
    "create_argument_parser",
    "get_connection_string_from_args",
    "is_shutdown_requested",
    "setup_signal_handlers",
    # telemetry_manager
    "TelemetryManager",
    "PositionData",
    "AttitudeData",
    "BatteryData",
    "FlightStateData",
    "wait_for_altitude",
    "wait_for_landed",
]

