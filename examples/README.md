# MAVSDK-Python Examples

This directory contains example scripts demonstrating common drone control operations using MAVSDK-Python.

## Prerequisites

- PX4 SITL running (use `./scripts/px4ctl.sh start`)
- MAVLink router configured
- MAVSDK-Python installed (`pip install mavsdk`)

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
# WiFi mode (testing with SITL)
python3 pi_connection_test.py -c wifi --wifi-host 192.168.1.100

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
python3 pi_simple_control.py -c wifi --wifi-host 192.168.1.100 --monitor-only

# Simple flight
python3 pi_simple_control.py -c uart --altitude 5
```

## Common Options

All examples support these connection options:

| Option | Description | Default |
|--------|-------------|---------|
| `-c`, `--connection-type` | Connection type: `tcp`, `wifi`, or `uart` | `wifi` or `PI_CONNECTION_TYPE` env |
| `--tcp-host` | TCP host IP address | `localhost` or `PI_TCP_HOST` env |
| `--tcp-port` | TCP port | `5760` or `PI_TCP_PORT` env |
| `--wifi-host` | WiFi (UDP) host IP address | `localhost` or `PI_WIFI_HOST` env |
| `--wifi-port` | WiFi (UDP) port | `14540` or `PI_WIFI_PORT` env |
| `--uart-device` | UART serial device path | `/dev/ttyAMA0` or `PI_UART_DEVICE` env |
| `--uart-baud` | UART baud rate | `57600` or `PI_UART_BAUD` env |
| `--verbose` / `-v` | Enable verbose output | `False` |

### TCP vs WiFi (UDP)

| Method | Protocol | Best For |
|--------|----------|----------|
| **TCP** (recommended) | TCP | Remote connections, reliability, works through NAT |
| **WiFi** | UDP | Same network, minimum latency |
| **UART** | Serial | Production with Cube+ Orange |

### Connection Examples

```bash
# TCP connection to SITL (recommended for Raspberry Pi)
python3 simple_takeoff_land.py -c tcp --tcp-host 192.168.1.100 --altitude 5

# WiFi (UDP) connection to SITL
python3 simple_takeoff_land.py -c wifi --wifi-host 192.168.1.100 --altitude 5

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

1. **Use async/await** - MAVSDK-Python is async-first
2. **Handle connections properly** - Wait for connection state
3. **Check health status** - Verify GPS and other sensors
4. **Implement error handling** - Catch and handle exceptions
5. **Support environment variables** - Use `MAVLINK_HOST` and `MAVLINK_PORT`
6. **Add command-line arguments** - Use argparse for flexibility
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

import argparse
import asyncio
import os
import sys

from mavsdk import System


async def run(host: str = "localhost", port: int = 14540):
    """Execute the example."""
    drone = System()
    await drone.connect(system_address=f"udp://{host}:{port}")

    # Wait for connection
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected!")
            break

    # Your code here

    return True


def main():
    parser = argparse.ArgumentParser(description="Example description")
    parser.add_argument("--host", default=os.environ.get("MAVLINK_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MAVLINK_PORT", "14540")))
    args = parser.parse_args()

    success = asyncio.get_event_loop().run_until_complete(
        run(host=args.host, port=args.port)
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

## References

- [MAVSDK-Python Documentation](https://mavsdk.mavlink.io/main/en/python/)
- [MAVSDK-Python Examples (Official)](https://github.com/mavlink/MAVSDK-Python/tree/main/examples)
- [PX4 Offboard Control](https://docs.px4.io/main/en/flight_modes/offboard.html)
- [PX4 Mission Mode](https://docs.px4.io/main/en/flight_modes/mission.html)

