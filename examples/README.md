# MAVSDK-Python Examples

This directory contains example scripts demonstrating common drone control operations using MAVSDK-Python.

## Prerequisites

- PX4 SITL running (use `./scripts/px4ctl.sh start`)
- MAVLink router configured
- MAVSDK-Python installed (`pip install mavsdk`)

## Project Structure

```
examples/
├── common/
│   ├── __init__.py
│   ├── drone_helpers.py     # Shared helper functions
│   └── telemetry_manager.py # Background telemetry (NEW)
├── manual_control/          # Keyboard-based manual control
│   ├── __init__.py
│   ├── keyboard_controller.py  # Non-blocking keyboard input
│   └── manual_control_app.py   # Main manual control app
├── person_tracker/          # AI-based person following
│   ├── __init__.py
│   ├── tracker_app.py       # Main tracker application
│   ├── tracking_controller.py  # PID controller
│   ├── mode_manager.py      # Enable/disable control
│   ├── distance_estimator.py   # Distance estimation
│   ├── config.py            # Configuration
│   └── README.md            # Tracker documentation
├── simple_takeoff_land.py   # Basic takeoff/land
├── hover_rotate.py          # Takeoff, rotate, land
├── mission_upload.py        # Waypoint missions
├── offboard_velocity.py     # Velocity control
├── telemetry_monitor.py     # Real-time monitoring
├── geofence_setup.py        # Geofence configuration
├── pi_connection_test.py    # Pi connection diagnostics
├── pi_simple_control.py     # Minimal Pi control
└── README.md                # This file
```

## Common Module

The `common/` directory contains shared functionality used across all example scripts:

### `drone_helpers.py`

Provides reusable functions for common drone operations:

| Function                            | Description                                            |
| ----------------------------------- | ------------------------------------------------------ |
| `connect_drone()`                   | Connect to drone and wait for heartbeat                |
| `wait_for_gps()`                    | Wait for GPS lock                                      |
| `preflight_check()`                 | Run standard preflight checks (GPS, battery, position) |
| `arm_and_takeoff()`                 | Arm and takeoff to specified altitude                  |
| `land_and_disarm()`                 | Land and wait for disarm                               |
| `safe_land()`                       | Emergency landing attempt                              |
| `emergency_stop()`                  | Kill motors (emergency only!)                          |
| `setup_logging()`                   | Configure logging                                      |
| `create_argument_parser()`          | Create parser with standard connection options         |
| `get_connection_string_from_args()` | Build MAVSDK connection string from args               |
| `get_telemetry_snapshot()`          | Get current telemetry values                           |

### `telemetry_manager.py` (NEW)

Thread-safe background telemetry manager that solves the MAVSDK "telemetry starvation" issue.

| Class/Function        | Description                                            |
| --------------------- | ------------------------------------------------------ |
| `TelemetryManager`    | Background telemetry reader with proper async yielding |
| `PositionData`        | Position telemetry dataclass                           |
| `AttitudeData`        | Attitude telemetry dataclass                           |
| `BatteryData`         | Battery telemetry dataclass                            |
| `FlightStateData`     | Armed/in_air/mode dataclass                            |
| `wait_for_altitude()` | Helper to wait for target altitude                     |
| `wait_for_landed()`   | Helper to wait for landing                             |

**Why TelemetryManager?**

When using `async for` on MAVSDK telemetry streams with delays (e.g., `asyncio.sleep(0.5)`),
the event loop gives too much priority to the telemetry task, causing commands (arm, takeoff)
to not execute properly. TelemetryManager uses `asyncio.sleep(0)` internally to prevent this.

```python
from examples.common import TelemetryManager

telemetry = TelemetryManager(drone)
await telemetry.start()

# Commands work while telemetry updates in background
await drone.action.arm()
await drone.action.takeoff()

# Access latest telemetry
print(f"Altitude: {telemetry.position.altitude_m:.2f}m")

await telemetry.stop()
```

### Classes

| Class               | Description                                 |
| ------------------- | ------------------------------------------- |
| `DroneConnection`   | Async context manager for drone connections |
| `TelemetrySnapshot` | Dataclass for telemetry data                |

### Usage Example

```python
from examples.common.drone_helpers import (
    DroneConnection,
    create_argument_parser,
    get_connection_string_from_args,
    preflight_check,
    arm_and_takeoff,
    land_and_disarm,
    setup_logging,
)

async def main():
    setup_logging()
    parser = create_argument_parser("My Example")
    args = parser.parse_args()
    connection_string = get_connection_string_from_args(args)

    async with DroneConnection(connection_string) as drone:
        if not await preflight_check(drone):
            return False
        await arm_and_takeoff(drone, altitude=10.0)
        # ... do something ...
        await land_and_disarm(drone)
    return True
```

## Available Examples

### Basic Operations

#### `simple_takeoff_land.py`
Minimal example demonstrating the core MAVSDK workflow:
- Connect to drone
- Wait for GPS lock
- Arm and takeoff
- Hover briefly
- Land safely

```bash
python3 simple_takeoff_land.py --altitude 10
```

#### `hover_rotate.py`
Demonstrates autonomous flight with offboard control:
- Takeoff to specified altitude
- Rotate 360 degrees (yaw)
- Land safely

```bash
python3 hover_rotate.py --altitude 5 --rotation 360 --speed 30
```

### Mission Planning

#### `mission_upload.py`
Shows how to create and execute waypoint missions:
- Create mission items
- Upload mission to drone
- Start and monitor mission progress
- Land after completion

```bash
python3 mission_upload.py --altitude 20
```

### Offboard Control

#### `offboard_velocity.py`
Demonstrates velocity-based offboard control:
- Enter offboard mode
- Execute velocity commands (fly a square pattern)
- Exit offboard mode and land

```bash
python3 offboard_velocity.py --altitude 10 --speed 2.0
```

### Telemetry

#### `telemetry_monitor.py`
Real-time telemetry monitoring:
- Position (GPS)
- Attitude (orientation)
- Battery status
- Flight mode
- Armed state

```bash
python3 telemetry_monitor.py --duration 60 --simple
```

### Safety

#### `geofence_setup.py`
Configure geofence boundaries:
- Create circular geofence around current position
- Upload geofence to drone
- Clear existing geofence

```bash
# Create geofence
python3 geofence_setup.py --radius 100 --max-altitude 50

# Clear geofence
python3 geofence_setup.py --clear
```

### Raspberry Pi

#### `pi_connection_test.py`
Comprehensive connection diagnostics for Raspberry Pi:
- Tests both UART and WiFi connections
- Verifies MAVLink heartbeat reception
- Displays telemetry and system health
- Provides connection troubleshooting

```bash
# UDP mode (testing with SITL - WiFi)
python3 pi_connection_test.py -c udp --udp-host 192.168.1.100 --udp-port 14540

# UART mode (production with Cube+ Orange)
python3 pi_connection_test.py -c uart

# Full diagnostic mode
python3 pi_connection_test.py -c uart --full-diagnostic
```

#### `pi_simple_control.py`
Minimal control example for Raspberry Pi:
- Connect via UART or WiFi
- Monitor telemetry
- Execute simple takeoff and land

```bash
# Monitor only (no flight)
python3 pi_simple_control.py -c udp --udp-host 192.168.1.100 --udp-port 14540 --monitor-only

# Simple flight
python3 pi_simple_control.py -c uart --altitude 5
```

### Manual Control

#### `manual_control/manual_control_app.py`
Keyboard-based manual drone control:
- WASD + Arrow keys for flight control (Mode 2 layout)
- Works over SSH (uses pynput)
- Position Control mode for stability
- Integrates with mode_manager for tracking override

**Control Scheme:**
| Key              | Function               |
| ---------------- | ---------------------- |
| W/S              | Throttle Up/Down       |
| A/D              | Yaw Left/Right         |
| Arrow Up/Down    | Pitch Forward/Back     |
| Arrow Left/Right | Roll Left/Right        |
| Space            | Emergency Stop (hover) |
| T                | Toggle Tracking Mode   |
| Q                | Quit                   |

```bash
# Connect to SITL
python3 -m examples.manual_control.manual_control_app -c tcp --tcp-host localhost

# With custom sensitivity
python3 -m examples.manual_control.manual_control_app --sensitivity 0.5

# Low throttle sensitivity for gentle altitude changes
python3 -m examples.manual_control.manual_control_app --throttle-sensitivity 0.2
```

**Dependencies:**
```bash
pip install pynput
```

### Person Tracking

#### `person_tracker/tracker_app.py`
AI-based person following using Hailo detection:
- Uses Hailo AI accelerator for person detection
- PID controller for smooth tracking
- Enable/disable via HTTP API or RC channel
- Manual control override support

See [person_tracker/README.md](person_tracker/README.md) for detailed documentation.

```bash
# Start with camera (connects via TCP by default)
python3 -m examples.person_tracker.tracker_app --input /dev/video0

# Connect to SITL with explicit TCP host
python3 -m examples.person_tracker.tracker_app --input /dev/video0 --tcp-host localhost

# Control via HTTP
curl -X POST http://localhost:8080/enable   # Start tracking
curl -X POST http://localhost:8080/disable  # Stop tracking
curl http://localhost:8080/status           # Check status
```

**Control Precedence:**
1. RC Remote (physical) - Hardware safety override
2. Manual Keyboard Control - Software override (via `manual_control_app.py`)
3. Autonomous Tracking - Lowest priority

When manual control is active (keyboard input detected), tracking is automatically inhibited.

## Common Options

All examples support these connection options:

| Option                    | Description                              | Default                                |
| ------------------------- | ---------------------------------------- | -------------------------------------- |
| `-c`, `--connection-type` | Connection type: `tcp`, `udp`, or `uart` | `tcp` or `PI_CONNECTION_TYPE` env      |
| `--tcp-host`              | TCP host IP address                      | `localhost` or `PI_TCP_HOST` env       |
| `--tcp-port`              | TCP port                                 | `5760` or `PI_TCP_PORT` env            |
| `--udp-host`              | UDP host IP address (WiFi mode)          | `0.0.0.0` or `PI_UDP_HOST` env         |
| `--udp-port`              | UDP port (WiFi mode)                     | `14540` or `PI_UDP_PORT` env           |
| `--uart-device`           | UART serial device path                  | `/dev/ttyAMA0` or `PI_UART_DEVICE` env |
| `--uart-baud`             | UART baud rate                           | `57600` or `PI_UART_BAUD` env          |
| `--verbose` / `-v`        | Enable verbose output                    | `False`                                |

### TCP vs UDP (WiFi)

| Method                | Protocol | Best For                                           |
| --------------------- | -------- | -------------------------------------------------- |
| **TCP** (recommended) | TCP      | Remote connections, reliability, works through NAT |
| **UDP** (WiFi)        | UDP      | Same network, minimum latency                      |
| **UART**              | Serial   | Production with Cube+ Orange                       |

**Note**: UDP is sometimes called "WiFi mode" but the command-line argument is `udp`.

### Connection Examples

```bash
# TCP connection to SITL (recommended for Raspberry Pi)
python3 simple_takeoff_land.py -c tcp --tcp-host 192.168.1.100 --altitude 5

# UDP connection to SITL (WiFi mode - low latency)
python3 simple_takeoff_land.py -c udp --udp-host 192.168.1.100 --udp-port 14540 --altitude 5

# UART connection to Cube+ Orange
python3 simple_takeoff_land.py -c uart --altitude 5

# Using environment variables
export PI_CONNECTION_TYPE=tcp
export PI_TCP_HOST=192.168.1.100
python3 simple_takeoff_land.py --altitude 5
```

## Running with Docker

Use the control script to run examples in the Docker environment:

```bash
# Start the environment
./scripts/px4ctl.sh start

# Run an example
./scripts/px4ctl.sh run examples/simple_takeoff_land.py --altitude 10

# Or enter the shell and run manually
./scripts/px4ctl.sh shell
python3 examples/simple_takeoff_land.py
```

## Creating New Examples

When creating new examples, follow these patterns:

1. **Use the common module** - Import helpers from `examples.common.drone_helpers`
2. **Use async/await** - MAVSDK-Python is async-first
3. **Handle connections properly** - Use `DroneConnection` context manager
4. **Check health status** - Call `preflight_check()` before flight
5. **Implement error handling** - Use try/except with `safe_land()` fallback
6. **Support all connection types** - Use `create_argument_parser()`
7. **Include docstrings** - Document usage and options

### Template

```python
#!/usr/bin/env python3
"""
example_name.py - Brief Description

Detailed description of what this example does.

Usage:
    python3 example_name.py [options]
"""

import asyncio
import sys

from examples.common.drone_helpers import (
    DroneConnection,
    arm_and_takeoff,
    create_argument_parser,
    get_connection_string_from_args,
    land_and_disarm,
    preflight_check,
    safe_land,
    setup_logging,
    setup_signal_handlers,
)


async def run(connection_string: str, altitude: float = 5.0) -> bool:
    """Execute the example."""
    setup_signal_handlers()

    async with DroneConnection(connection_string) as drone:
        if drone is None:
            return False

        # Preflight checks
        if not await preflight_check(drone):
            return False

        # Takeoff
        if not await arm_and_takeoff(drone, altitude=altitude):
            await safe_land(drone)
            return False

        try:
            # Your code here
            pass

        finally:
            # Always land
            await land_and_disarm(drone)

    return True


def main():
    setup_logging()
    parser = create_argument_parser("Example description")
    # Add custom arguments here if needed
    args = parser.parse_args()
    connection_string = get_connection_string_from_args(args)

    success = asyncio.run(run(connection_string, altitude=args.altitude))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

## References

- [MAVSDK-Python Documentation](https://mavsdk.mavlink.io/main/en/python/)
- [MAVSDK-Python Examples (Official)](https://github.com/mavlink/MAVSDK-Python/tree/main/examples)
- [PX4 Offboard Control](https://docs.px4.io/main/en/flight_modes/offboard.html)
- [PX4 Mission Mode](https://docs.px4.io/main/en/flight_modes/mission.html)

