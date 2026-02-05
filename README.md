# PX4 Cube+ Orange Development Environment

A fully containerized development environment for PX4 autopilot development targeting the Cube+ Orange flight controller. All tools run in Docker - no host installation required.

## Features

- **All-in-Docker Stack**: PX4 SITL, Gazebo, QGroundControl, and MAVSDK all containerized
- **One-Command Startup**: `./scripts/px4ctl.sh start` launches everything
- **Switchable Profiles**: SITL, HITL, headless, and development modes
- **Example Scripts**: Ready-to-run autonomous flight demonstrations
- **Integration Tests**: Automated testing of the complete stack

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Network: px4-net                       │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐  │
│  │ PX4 SITL  │───►│  MAVLink  │───►│    QGC    │    │Control │  │
│  │ + Gazebo  │    │  Router   │───►│  (GUI)    │    │Scripts │  │
│  └───────────┘    └───────────┘    └───────────┘    └────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation.

## Prerequisites

- **Docker Engine** 20.10+
- **Docker Compose** v2.0+
- **X11 Display** (for GUI applications)
- **Ubuntu 22.04** recommended

### Quick Docker Install

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

## Quick Start

### 1. Clone and Setup

```bash
cd ~/projects/hailo_drone_control

# Copy environment configuration
cp env.example .env

# Make scripts executable
chmod +x scripts/*.sh

# Setup Python virtual environment (for running scripts locally)
python3 -m venv venv_mavlink
source venv_mavlink/bin/activate
pip install -r requirements.txt
```

### 2. Start the Full Stack

```bash
# Allow X11 forwarding
xhost +local:docker

# Start everything (builds images on first run)
./scripts/px4ctl.sh start
```

This launches:
- **PX4 SITL** with Gazebo simulator
- **MAVLink Router** for telemetry distribution
- **QGroundControl** GUI
- **Control container** for running scripts

### 3. Run the Demo Flight

Once QGroundControl shows the drone connected:

```bash
# Execute the hover & rotate demo
./scripts/px4ctl.sh run examples/hover_rotate.py
```

The drone will:
1. Arm and take off to 5m
2. Hover and rotate 360°
3. Land safely

### 4. Stop Everything

```bash
./scripts/px4ctl.sh stop
```

## px4ctl.sh - Command Reference

The main control script for managing the environment:

```bash
./scripts/px4ctl.sh <command> [options]
```

| Command             | Description                       |
| ------------------- | --------------------------------- |
| `start [profile]`   | Start environment (default: full) |
| `stop`              | Stop all services                 |
| `restart [profile]` | Restart the environment           |
| `status`            | Show service status               |
| `logs [service]`    | Tail logs (all or specific)       |
| `shell`             | Open development shell            |
| `run <script>`      | Run Python script in container    |
| `test`              | Run integration tests             |
| `build`             | Rebuild Docker images             |
| `clean`             | Remove containers and volumes     |

### Examples

```bash
# Start headless (no GUI - for CI/testing)
./scripts/px4ctl.sh start headless

# View specific service logs
./scripts/px4ctl.sh logs px4-sitl

# Open interactive shell
./scripts/px4ctl.sh shell

# Run custom script
./scripts/px4ctl.sh run examples/hover_rotate.py --altitude 10
```

## Profiles

| Profile    | Services                      | Use Case                 |
| ---------- | ----------------------------- | ------------------------ |
| `full`     | SITL + Gazebo + QGC + Control | Development with GUI     |
| `headless` | SITL + Control                | CI/CD, automated testing |
| `sitl`     | SITL + Gazebo only            | Simulation only          |
| `dev`      | Development shell             | Interactive development  |
| `hitl`     | Hardware-in-the-loop          | Physical Cube+ Orange    |

## Example: Hover & Rotate

The included demo script demonstrates autonomous flight:

```bash
./scripts/px4ctl.sh run examples/hover_rotate.py [options]
```

Options:
- `--altitude METERS` - Takeoff altitude (default: 5.0)
- `--rotation DEGREES` - Rotation amount (default: 360)
- `--speed DEG/SEC` - Rotation speed (default: 30)

```bash
# Higher altitude, double rotation
./scripts/px4ctl.sh run examples/hover_rotate.py --altitude 10 --rotation 720

# Slow rotation
./scripts/px4ctl.sh run examples/hover_rotate.py --speed 15
```

## Example: Person Tracking

The person tracker uses Hailo AI detection to follow a person:

```bash
# Start SITL first
./scripts/px4ctl.sh start

# Run person tracker with camera
source venv_mavlink/bin/activate
python examples/person_tracker/tracker_app.py --input /dev/video0

# Control tracking via HTTP
curl -X POST http://localhost:8080/enable   # Start tracking
curl -X POST http://localhost:8080/disable  # Stop tracking
curl http://localhost:8080/status           # Check status
```

See [examples/person_tracker/README.md](examples/person_tracker/README.md) for detailed documentation.

## Example: Manual Control

Keyboard-based manual flight control using WASD + Arrow keys:

```bash
# Start SITL first
./scripts/px4ctl.sh start

# Run manual control (pynput is in requirements.txt)
source venv_mavlink/bin/activate
python -m examples.manual_control.manual_control_app -c tcp --tcp-host localhost
```

**Control Keys:**
- `W/S` - Throttle Up/Down
- `A/D` - Yaw Left/Right
- `Arrow Up/Down` - Pitch Forward/Back
- `Arrow Left/Right` - Roll Left/Right
- `T` - Arm & Takeoff (5m)
- `L` - Land
- `Space` - Emergency Stop (hover)
- `G` - Toggle person tracking
- `Q` - Quit

Manual control automatically overrides person tracking when active.

## Project Structure

```
hailo_drone_control/
├── docker/
│   ├── Dockerfile          # PX4 + Gazebo image
│   ├── Dockerfile.qgc      # QGroundControl image
│   └── entrypoint.sh       # Container startup
├── config/
│   ├── drone_config.yml    # Vehicle configuration
│   ├── mavlink-router.conf # MAVLink routing
│   └── params/             # PX4 parameters
├── scripts/
│   ├── px4ctl.sh           # Main CLI tool
│   ├── mavlink_connection.py # Connection config utilities
│   ├── wait_for_mavlink.py # Health check utility
│   ├── setup_udev.sh       # Device rules (HITL)
│   └── post_create.sh      # Dev container setup
├── examples/
│   ├── common/             # Shared helper functions
│   │   └── drone_helpers.py # Connection, takeoff, landing utils
│   ├── manual_control/     # Keyboard-based manual control
│   │   ├── keyboard_controller.py # Non-blocking keyboard input
│   │   └── manual_control_app.py  # Main manual control app
│   ├── person_tracker/     # Person-following drone controller
│   │   ├── tracker_app.py  # Main tracking application
│   │   ├── tracking_controller.py # PID controller
│   │   ├── mode_manager.py # Enable/disable control
│   │   └── README.md       # Tracking documentation
│   ├── hover_rotate.py     # Demo flight script
│   ├── simple_takeoff_land.py # Basic takeoff/land
│   ├── offboard_velocity.py   # Velocity-based control
│   ├── telemetry_monitor.py   # Real-time telemetry
│   ├── pi_connection_test.py  # Pi connection diagnostics
│   └── pi_simple_control.py   # Minimal Pi control
├── tests/
│   ├── test_environment.py # Unit tests
│   └── test_integration.py # Integration tests
├── docker-compose.yml      # Service definitions
├── ARCHITECTURE.md         # Technical documentation
└── README.md               # This file
```

## Configuration

### Environment Variables

Edit `.env` to customize:

| Variable      | Default | Description        |
| ------------- | ------- | ------------------ |
| `VEHICLE_ID`  | `1`     | Vehicle identifier |
| `AIRFRAME`    | `x500`  | Airframe model     |
| `MAV_SYS_ID`  | `1`     | MAVLink system ID  |
| `QGC_PORT`    | `14550` | QGC MAVLink port   |
| `MAVSDK_PORT` | `14540` | MAVSDK API port    |
| `DISPLAY`     | `:0`    | X11 display        |

### Vehicle Configuration

`config/drone_config.yml` contains vehicle-specific settings:
- Frame configuration
- MAVLink endpoints
- Safety parameters (geofence, RTL, failsafe)

## Running Tests

### Integration Tests

```bash
# Start the stack first
./scripts/px4ctl.sh start headless

# Run tests
./scripts/px4ctl.sh test
```

### Environment Tests

```bash
./scripts/px4ctl.sh shell
python3 tests/test_environment.py
```

## Network Ports

| Port  | Protocol | Service               |
| ----- | -------- | --------------------- |
| 14580 | UDP      | PX4 SITL MAVLink      |
| 14550 | UDP      | QGroundControl        |
| 14540 | UDP      | MAVSDK / Offboard API |
| 5760  | TCP      | Mission Planner       |

## Troubleshooting

### QGroundControl Not Displaying

```bash
# Allow Docker X11 access
xhost +local:docker

# Verify DISPLAY is set
echo $DISPLAY

# Check X11 socket
ls -la /tmp/.X11-unix/
```

### Gazebo Rendering Issues (Intel GPU)

```bash
# Check OpenGL info
./scripts/px4ctl.sh shell
glxinfo | grep "OpenGL renderer"

# Force software rendering if needed
export LIBGL_ALWAYS_SOFTWARE=1
```

### Services Not Starting

```bash
# Check service status
./scripts/px4ctl.sh status

# View logs
./scripts/px4ctl.sh logs

# Rebuild images
./scripts/px4ctl.sh build
```

### MAVLink Connection Issues

```bash
# Test MAVLink connectivity
./scripts/px4ctl.sh shell
python3 scripts/wait_for_mavlink.py --verbose

# Check network
docker network inspect px4-net
```

### Clean Restart

```bash
# Stop and remove everything
./scripts/px4ctl.sh clean

# Rebuild and start fresh
./scripts/px4ctl.sh build
./scripts/px4ctl.sh start
```

## HITL Mode (Hardware-in-the-Loop)

To use with a physical Cube+ Orange:

```bash
# Install udev rules (one-time)
sudo ./scripts/setup_udev.sh

# Connect Cube+ Orange via USB
# Verify device
ls -la /dev/cube_orange

# Start HITL mode
./scripts/px4ctl.sh start hitl
```

## Raspberry Pi Connection

Connect a Raspberry Pi to control the drone via UART (production) or TCP/UDP (testing with SITL).

**Quick Start:**

```bash
# On Raspberry Pi - TCP connection (recommended)
python3 examples/pi_connection_test.py -c tcp --tcp-host 192.168.1.100

# UDP connection (WiFi - lower latency)
python3 examples/pi_connection_test.py -c udp --udp-host 192.168.1.100 --udp-port 14540

# UART connection (production - Cube+ Orange)
python3 examples/pi_connection_test.py -c uart
```

**Connection Types:**

| Method                | Use Case                                                   | Command-Line                             |
| --------------------- | ---------------------------------------------------------- | ---------------------------------------- |
| **TCP** (recommended) | Reliable, works through NAT/firewalls, Pi connects to SITL | `-c tcp --tcp-host HOST`                 |
| **UDP** (WiFi)        | Lower latency, requires same network                       | `-c udp --udp-host HOST --udp-port PORT` |
| **UART**              | Production - Direct serial to Cube+ Orange TELEM2          | `-c uart`                                |

**Note**: UDP is sometimes called "WiFi mode" but the command-line argument is `udp`.

For complete setup instructions, hardware wiring diagrams, troubleshooting, and detailed examples, see **[docs/PI_SETUP.md](docs/PI_SETUP.md)**.

## Development

### Interactive Shell

```bash
./scripts/px4ctl.sh shell

# Inside container:
cd /workspace/PX4-Autopilot
make px4_sitl_default          # Build SITL
make px4_fmu-v6x_default       # Build Cube+ Orange firmware
```

### VS Code Dev Containers

1. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open folder in VS Code
3. Click "Reopen in Container"

### Adding Custom Scripts

Place scripts in `examples/` and run with:

```bash
./scripts/px4ctl.sh run examples/your_script.py
```

## Example Scripts

The `examples/` directory contains ready-to-use MAVSDK-Python scripts. All examples share common functionality from the `examples/common/` package:

**drone_helpers.py**:
- Connection management (TCP, UDP, UART)
- Preflight checks (GPS, battery, position)
- Takeoff/landing helpers
- Signal handling for graceful shutdown

**telemetry_manager.py** (NEW):
- Thread-safe background telemetry reading
- Solves the MAVSDK "telemetry starvation" issue (see Troubleshooting)
- Provides `TelemetryManager` class for concurrent telemetry + commands

| Script                   | Description                          |
| ------------------------ | ------------------------------------ |
| `simple_takeoff_land.py` | Basic takeoff and land sequence      |
| `hover_rotate.py`        | Takeoff, rotate 360°, and land       |
| `mission_upload.py`      | Create and execute waypoint missions |
| `offboard_velocity.py`   | Velocity-based offboard control      |
| `telemetry_monitor.py`   | Real-time telemetry monitoring       |
| `geofence_setup.py`      | Configure geofence boundaries        |
| `pi_connection_test.py`  | Raspberry Pi connection diagnostics  |
| `pi_simple_control.py`   | Minimal control example for Pi       |
| `manual_control/`        | Keyboard-based manual flight control |
| `person_tracker/`        | AI-based person following            |

**Running Examples**:

```bash
# Start SITL first
./scripts/px4ctl.sh start

# Run an example
./scripts/px4ctl.sh run examples/simple_takeoff_land.py --altitude 10

# Monitor telemetry
./scripts/px4ctl.sh run examples/telemetry_monitor.py --duration 60
```

## Troubleshooting

### MAVSDK Telemetry Starvation (Commands Not Executing)

**Problem**: When using `async for` on MAVSDK telemetry streams with delays, commands (arm, takeoff) don't execute properly. The telemetry shows 0.0m altitude even though the drone should be flying.

**Cause**: Using `await asyncio.sleep(0.5)` inside telemetry loops gives too much priority to the telemetry task, starving command execution.

**Solution**: Use `await asyncio.sleep(0)` to immediately yield control:

```python
# ❌ BAD - causes telemetry starvation
async for pos in drone.telemetry.position():
    print(f"Alt: {pos.relative_altitude_m}")
    await asyncio.sleep(0.5)  # This starves other tasks!

# ✓ GOOD - proper async yielding
async for pos in drone.telemetry.position():
    print(f"Alt: {pos.relative_altitude_m}")
    await asyncio.sleep(0)  # Immediately yield control
```

**Better Solution**: Use the `TelemetryManager` from `examples/common/telemetry_manager.py`:

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

### Diagnostic Tool

Use the diagnostic tool to test your connection:

```bash
# Test TCP connection
python scripts/diagnose_connection.py -c tcp --tcp-host localhost

# Test with full action test (arm/takeoff/land)
python scripts/diagnose_connection.py --test-action
```

### Connection Issues

| Issue                                         | Solution                                                        |
| --------------------------------------------- | --------------------------------------------------------------- |
| "Waiting for mavsdk_server to be ready" hangs | Kill existing MAVSDK processes: `pkill -f mavsdk`               |
| Telemetry shows 0m but drone is flying        | Use `TelemetryManager` or `asyncio.sleep(0)` in loops           |
| Commands don't execute                        | Ensure proper async yielding in telemetry loops                 |
| TCP connection timeout                        | Check Docker container is running: `./scripts/px4ctl.sh status` |

## Documentation

| Document                                                               | Purpose                                                             |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)                                     | System architecture and technical implementation details            |
| [RESEARCH.md](RESEARCH.md)                                             | Academic analysis of design decisions and theoretical foundations   |
| [docs/PI_SETUP.md](docs/PI_SETUP.md)                                   | Complete guide for Raspberry Pi connection via UART, TCP, or UDP    |
| [docs/OPEN_SOURCE_SOLUTIONS.md](docs/OPEN_SOURCE_SOLUTIONS.md)         | Catalog of reusable open-source components and integration patterns |
| [examples/README.md](examples/README.md)                               | Documentation for all example scripts and usage patterns            |
| [examples/person_tracker/README.md](examples/person_tracker/README.md) | Person tracking system documentation                                |
| [examples/manual_control/README.md](examples/manual_control/README.md) | Keyboard-based manual control documentation                         |

## Resources

### Official Documentation

- [PX4 User Guide](https://docs.px4.io/)
- [PX4 Parameter Reference](https://docs.px4.io/main/en/advanced_config/parameter_reference.html)
- [MAVSDK Python Guide](https://mavsdk.mavlink.io/main/en/python/)
- [MAVLink Protocol](https://mavlink.io/)
- [Gazebo Garden](https://gazebosim.org/docs/garden/)
- [QGroundControl](https://docs.qgroundcontrol.com/)

### Hardware Documentation

- [Cube+ Orange Manual](https://docs.cubepilot.org/)
- [PX4 Airframe Reference](https://docs.px4.io/main/en/airframes/airframe_reference.html)

### Community Resources

- [PX4 Discuss Forum](https://discuss.px4.io/)
- [PX4 Discord](https://discord.gg/dronecode)
- [MAVSDK-Python Examples](https://github.com/mavlink/MAVSDK-Python/tree/main/examples)

## License

This project is provided for development and research purposes.
