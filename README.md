# PX4 Cube+ Orange Development Environment

A containerized development environment for PX4 autopilot development targeting the Cube+ Orange flight controller. Features switchable profiles for SITL (Software-in-the-Loop) and HITL (Hardware-in-the-Loop) simulation modes.

## Features

- **Docker-based isolation** - Reproducible development environment with all dependencies
- **Switchable profiles** - Easily switch between SITL, HITL, and development modes
- **PX4 + Gazebo Garden** - Modern simulation stack with physics-accurate modeling
- **MAVLink routing** - Seamless communication with QGroundControl and MAVSDK
- **Intel GPU support** - Mesa drivers for laptops with integrated graphics
- **VS Code Dev Containers** - Full IDE integration with debugging support

## Prerequisites

- Ubuntu 22.04 LTS (recommended)
- Docker Engine 20.10+
- Docker Compose v2.0+
- QGroundControl (for ground station)
- X11 display server (for Gazebo GUI)

### Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Log out and back in for group changes
```

## Quick Start

### 1. Clone and Setup

```bash
cd ~/projects/hailo_drone_control

# Copy environment configuration
cp env.example .env

# Allow X11 forwarding (run each session)
xhost +local:docker
```

### 2. Build the Docker Image

```bash
docker compose build
```

### 3. Run SITL Simulation

```bash
# Start SITL with Gazebo
docker compose --profile sitl up

# Or run in background
docker compose --profile sitl up -d
```

### 4. Connect QGroundControl

1. Open QGroundControl
2. Go to **Application Settings > Comm Links**
3. Add a new UDP connection:
   - Name: `PX4 SITL`
   - Type: `UDP`
   - Port: `14550`
4. Connect to the link

## Usage

### Simulation Modes

| Profile | Command | Description |
|---------|---------|-------------|
| `sitl` | `docker compose --profile sitl up` | Software simulation with Gazebo |
| `hitl` | `docker compose --profile hitl up` | Hardware-in-the-loop with Cube+ Orange |
| `dev` | `docker compose --profile dev run --rm dev bash` | Interactive development shell |

### Development Shell

The dev profile provides an interactive environment with all tools pre-installed:

```bash
# Start development shell
docker compose --profile dev run --rm dev bash

# Inside container - useful commands:
px4-sitl      # Run SITL with Gazebo x500
px4-cube      # Build firmware for Cube+ Orange
px4-clean     # Clean build artifacts
cdpx4         # Navigate to PX4 source
```

### Building Firmware for Cube+ Orange

```bash
# Enter development shell
docker compose --profile dev run --rm dev bash

# Build firmware
cd /workspace/PX4-Autopilot
make px4_fmu-v6x_default

# Firmware will be at:
# build/px4_fmu-v6x_default/px4_fmu-v6x_default.px4
```

### HITL Mode (Hardware-in-the-Loop)

HITL requires a physical Cube+ Orange connected via USB:

```bash
# Install udev rules (one-time setup)
sudo ./scripts/setup_udev.sh

# Verify device is detected
ls -la /dev/cube_orange

# Start HITL
docker compose --profile hitl up
```

## Configuration

### Environment Variables

Edit `.env` to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `VEHICLE_ID` | `1` | Vehicle identifier (1-255) |
| `AIRFRAME` | `x500` | Airframe model |
| `MAV_SYS_ID` | `1` | MAVLink system ID |
| `QGC_PORT` | `14550` | QGroundControl UDP port |
| `MAVSDK_PORT` | `14540` | MAVSDK API port |
| `SIM_MODE` | `sitl` | Simulation mode |

### Vehicle Configuration

The `config/drone_config.yml` file contains vehicle-specific settings:

- Vehicle frame and motor configuration
- MAVLink settings
- Communication endpoints
- Safety parameters (geofence, RTL, battery failsafe)

### MAVLink Routing

The `config/mavlink-router.conf` file defines telemetry routing:

- SITL/HITL input endpoints
- QGroundControl forwarding
- MAVSDK API endpoint
- Optional TCP for Mission Planner

## Project Structure

```
hailo_drone_control/
├── docker/
│   ├── Dockerfile          # Container image definition
│   └── entrypoint.sh       # Container startup script
├── config/
│   ├── drone_config.yml    # Vehicle configuration
│   ├── mavlink-router.conf # MAVLink routing
│   └── params/
│       └── x500_quad.params # PX4 parameters
├── scripts/
│   ├── setup_udev.sh       # udev rules installer
│   └── post_create.sh      # Dev container setup
├── .devcontainer/
│   └── devcontainer.json   # VS Code integration
├── docker-compose.yml      # Docker services
├── env.example             # Environment template
└── README.md
```

## VS Code Dev Containers

For the best development experience, use VS Code with the Dev Containers extension:

1. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open the project folder in VS Code
3. Click **Reopen in Container** when prompted
4. Wait for the container to build and PX4 to initialize

### Included Extensions

- C/C++ and CMake tools
- Python with Black formatter
- YAML support
- Git integration (GitLens, Git Graph)
- Docker support

## Troubleshooting

### Gazebo GUI Not Displaying

```bash
# Allow X11 connections from Docker
xhost +local:docker

# Verify DISPLAY is set
echo $DISPLAY

# Test with a simple X11 app
docker compose --profile dev run --rm dev xclock
```

### Intel GPU Rendering Issues

If Gazebo shows software rendering warnings:

```bash
# Check OpenGL support
docker compose --profile dev run --rm dev glxinfo | grep "OpenGL renderer"

# Force software rendering if needed (in .env)
LIBGL_ALWAYS_SOFTWARE=1
```

### Serial Device Not Found (HITL)

```bash
# Check USB device
lsusb | grep -i cube

# View kernel messages
dmesg | tail -20

# Reinstall udev rules
sudo ./scripts/setup_udev.sh
```

### Container Build Fails

```bash
# Clean Docker cache and rebuild
docker compose build --no-cache

# Remove old volumes
docker volume rm px4-autopilot-source
```

## Ports Reference

| Port | Protocol | Service |
|------|----------|---------|
| 14550 | UDP | QGroundControl MAVLink |
| 14540 | UDP | MAVSDK / Offboard API |
| 14580 | UDP | SITL MAVLink input |
| 5760 | TCP | Mission Planner |
| 8080 | TCP | Gazebo web interface |

## Future Enhancements

- [ ] ROS2 integration with Micro-XRCE-DDS bridge
- [ ] Multi-vehicle simulation support
- [ ] Automated CI/CD pipeline
- [ ] Custom Gazebo worlds and models

## Resources

- [PX4 Documentation](https://docs.px4.io/)
- [Cube+ Orange Manual](https://docs.cubepilot.org/)
- [QGroundControl](https://docs.qgroundcontrol.com/)
- [MAVSDK Python](https://mavsdk.mavlink.io/main/en/python/)
- [Gazebo Garden](https://gazebosim.org/docs/garden/)

## License

This project is provided as-is for development and research purposes.

