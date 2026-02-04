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
│   ├── wait_for_mavlink.py # Health check utility
│   ├── setup_udev.sh       # Device rules (HITL)
│   └── post_create.sh      # Dev container setup
├── examples/
│   └── hover_rotate.py     # Demo flight script
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

Connect a Raspberry Pi to control the drone via UART (production) or WiFi (testing with SITL).

### Quick Start (WiFi - Testing)

1. **Start SITL on host:**
   ```bash
   ./scripts/px4ctl.sh start
   ```

2. **Get host IP address:**
   ```bash
   hostname -I  # Note the IP (e.g., 192.168.1.100)
   ```

3. **On Raspberry Pi:**
   ```bash
   # Install MAVSDK
   pip3 install mavsdk

   # Clone repository
   git clone <repository-url>
   cd hailo_drone_control

   # Test connection
   python3 examples/pi_connection_test.py -c wifi --wifi-host 192.168.1.100

   # Run a flight example
   python3 examples/simple_takeoff_land.py -c wifi --wifi-host 192.168.1.100 --altitude 5
   ```

### Quick Start (UART - Production)

1. **Wire TELEM2 to Raspberry Pi GPIO:**
   ```
   Cube+ Orange TELEM2     Raspberry Pi
   TX  ───────────────────  RX (GPIO 15, Pin 10)
   RX  ───────────────────  TX (GPIO 14, Pin 8)
   GND ───────────────────  GND (Pin 6)
   ```

2. **Setup Raspberry Pi:**
   ```bash
   # Run setup script (installs MAVSDK, enables UART)
   ./scripts/setup_pi.sh
   ```

3. **Test connection:**
   ```bash
   python3 examples/pi_connection_test.py -c uart
   ```

### Connection Types

All example scripts support both connection modes:

```bash
# WiFi mode (default - SITL testing)
python3 examples/hover_rotate.py -c wifi --wifi-host 192.168.1.100

# UART mode (production - Cube+ Orange)
python3 examples/hover_rotate.py -c uart --uart-device /dev/ttyAMA0
```

| Script | Description |
|--------|-------------|
| `pi_connection_test.py` | Comprehensive connection diagnostics |
| `pi_simple_control.py` | Minimal control example |

See [docs/PI_SETUP.md](docs/PI_SETUP.md) for complete setup instructions.

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

The `examples/` directory contains ready-to-use MAVSDK-Python scripts:

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

**Running Examples**:

```bash
# Start SITL first
./scripts/px4ctl.sh start

# Run an example
./scripts/px4ctl.sh run examples/simple_takeoff_land.py --altitude 10

# Monitor telemetry
./scripts/px4ctl.sh run examples/telemetry_monitor.py --duration 60
```

## Documentation

- [Raspberry Pi Setup Guide](docs/PI_SETUP.md) - Complete guide for Pi connection via UART or WiFi
- [Open Source Solutions Reference](docs/OPEN_SOURCE_SOLUTIONS.md) - Catalog of reusable open-source components
- [Research Notes](RESEARCH.md) - Technical architecture and design decisions

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
