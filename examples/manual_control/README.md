# Manual Control Module

Keyboard-based manual drone control using MAVSDK's `manual_control` plugin. Works in both SITL and HITL environments.

## Features

- **Keyboard Control**: WASD + Arrow keys (Mode 2 layout)
- **SSH Compatible**: Uses `pynput` for non-blocking input over SSH
- **Position Control Mode**: GPS-stabilized for smooth, safe control
- **Tracking Integration**: Automatically overrides person tracking when active
- **Safety Features**: Emergency stop, automatic hover on timeout

## Installation

```bash
pip install pynput
```

## Usage

```bash
# Connect to SITL
python -m examples.manual_control.manual_control_app -c tcp --tcp-host localhost

# Connect via UDP
python -m examples.manual_control.manual_control_app -c udp --udp-port 14540

# Custom sensitivity
python -m examples.manual_control.manual_control_app --sensitivity 0.5 --throttle-sensitivity 0.2

# With custom HTTP port for mode manager
python -m examples.manual_control.manual_control_app --http-port 8081
```

## Control Scheme (Mode 2)

| Key              | Function               |
| ---------------- | ---------------------- |
| W/S              | Throttle Up/Down       |
| A/D              | Yaw Left/Right         |
| Arrow Up/Down    | Pitch Forward/Back     |
| Arrow Left/Right | Roll Left/Right        |
| T                | Arm & Takeoff          |
| L                | Land                   |
| G                | Toggle Tracking Mode   |
| Space            | Emergency Stop (hover) |
| Q                | Quit                   |

## Control Precedence

When using manual control alongside person tracking:

1. **RC Remote** (physical) - Highest priority (hardware safety)
2. **Manual Keyboard** - Overrides tracking
3. **Autonomous Tracking** - Lowest priority

Manual control automatically inhibits tracking when active. Tracking resumes after 3 seconds of no manual input (configurable via `--manual-timeout`).

## Options

| Option                   | Default     | Description                     |
| ------------------------ | ----------- | ------------------------------- |
| `-c, --connection-type`  | `tcp`       | Connection type: tcp, udp, uart |
| `--tcp-host`             | `localhost` | TCP host for drone connection   |
| `--tcp-port`             | `5760`      | TCP port for drone connection   |
| `--sensitivity`          | `0.7`       | Control sensitivity (0.1-1.0)   |
| `--throttle-sensitivity` | `0.3`       | Throttle sensitivity (0.1-1.0)  |
| `--http-port`            | `8080`      | HTTP API port for mode manager  |
| `--manual-timeout`       | `3.0`       | Manual mode timeout in seconds  |
| `-v, --verbose`          | `False`     | Enable verbose logging          |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Keyboard      │────▶│ KeyboardController│────▶│ ManualControlApp│
│   (pynput)      │     │ (normalize input) │     │ (MAVSDK control)│
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌──────────────────┐              │
                        │   ModeManager    │◀─────────────┘
                        │ (precedence ctrl)│
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │   PX4 Autopilot  │
                        │ (Position Control)│
                        └──────────────────┘
```

## HTTP API

When running, the mode manager HTTP API is available:

```bash
# Check status
curl http://localhost:8080/status

# Enable tracking (if not in manual mode)
curl -X POST http://localhost:8080/enable

# Disable tracking
curl -X POST http://localhost:8080/disable

# Clear manual mode override
curl -X POST http://localhost:8080/clear_manual
```

## Programmatic Usage

```python
from examples.manual_control.keyboard_controller import KeyboardController, ControlInput

# Create controller
controller = KeyboardController(sensitivity=0.7)
controller.start()

# Get current input
control_input = controller.get_input()
print(f"x={control_input.x}, y={control_input.y}, z={control_input.z}, r={control_input.r}")

# Register callbacks
controller.on_quit(lambda: print("Quit requested"))
controller.on_emergency_stop(lambda: print("EMERGENCY STOP"))

# Stop when done
controller.stop()
```

## Safety Notes

1. **GPS Required**: Position Control mode requires GPS lock
2. **Emergency Stop**: Press Space to immediately stop movement
3. **Timeout**: Manual control auto-expires after inactivity
4. **RC Override**: Physical RC always has highest priority

## Technical Notes

### Telemetry Handling

This module uses the `TelemetryManager` from `examples.common` for background telemetry
reading. This is important because MAVSDK telemetry streams can "starve" command execution
if not handled properly.

**Key Points:**
- Telemetry runs in background tasks using `asyncio.sleep(0)` to yield control
- Commands (arm, takeoff, land) work properly even with continuous telemetry
- If you extend this module, always use `asyncio.sleep(0)` in telemetry loops

See the main [README.md](../../README.md) Troubleshooting section for details.

