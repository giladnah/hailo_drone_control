"""
PX4 Example Scripts

This package contains example flight control scripts demonstrating
how to use MAVSDK to control a PX4-based drone.

Examples:
    simple_takeoff_land.py  - Basic takeoff, hover, and land
    hover_rotate.py         - Takeoff, rotate 360°, and land
    offboard_velocity.py    - Offboard velocity control (fly square)
    mission_upload.py       - Upload and execute waypoint mission
    telemetry_monitor.py    - Real-time telemetry monitoring
    geofence_setup.py       - Configure geofence boundaries
    pi_connection_test.py   - Test MAVLink connectivity
    pi_simple_control.py    - Minimal control from Raspberry Pi

Common Module:
    examples/common/        - Shared utilities for all examples
        drone_helpers.py    - Connection, preflight, takeoff, land helpers

Connection Types:
    All examples support multiple connection types via command line:
    - TCP (default): --tcp-host HOST --tcp-port PORT
    - UDP: -c udp --udp-host HOST --udp-port PORT
    - UART: -c uart --uart-device DEVICE --uart-baud BAUD

Usage:
    # Run from project root with Docker:
    ./scripts/px4ctl.sh run examples/hover_rotate.py --altitude 10

    # Run directly (requires MAVSDK installed):
    python3 examples/simple_takeoff_land.py --tcp-host px4-sitl

    # UART mode for Raspberry Pi:
    python3 examples/hover_rotate.py -c uart --uart-device /dev/ttyAMA0
"""
