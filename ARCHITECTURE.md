# PX4 Development Environment Architecture

This document describes the architecture of the containerized PX4 development environment for the Cube+ Orange flight controller.

## System Overview

The development environment runs entirely in Docker containers, providing a reproducible and isolated setup for PX4 drone development. The architecture follows a microservices pattern inspired by projects like Frigate NVR, enabling flexible configuration and easy switching between simulation modes.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Host System (Ubuntu)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Docker Network: px4-net                       │    │
│  │                      (172.28.0.0/16)                            │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────┐ │    │
│  │  │  px4-sitl   │  │  mavlink-   │  │ qground-    │  │control │ │    │
│  │  │             │  │  router     │  │ control     │  │        │ │    │
│  │  │ ┌─────────┐ │  │             │  │             │  │ MAVSDK │ │    │
│  │  │ │   PX4   │ │  │  Routes     │  │   Ground    │  │ Python │ │    │
│  │  │ │  SITL   │◄┼──┼─ MAVLink ──►│◄─┼─  Control ──┼──┼─Scripts│ │    │
│  │  │ └─────────┘ │  │  telemetry  │  │   Station   │  │        │ │    │
│  │  │ ┌─────────┐ │  │             │  │             │  └────────┘ │    │
│  │  │ │ Gazebo  │ │  └─────────────┘  └─────────────┘              │    │
│  │  │ │ Garden  │ │                                                 │    │
│  │  │ └─────────┘ │       UDP 14580        UDP 14550    UDP 14540  │    │
│  │  │ 172.28.0.10 │       172.28.0.11      172.28.0.20  172.28.0.30│    │
│  │  └─────────────┘                                                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐                                     │
│  │ X11 Display  │  │    User      │                                     │
│  │   Server     │  │  Terminal    │                                     │
│  └──────────────┘  └──────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Container Architecture

### 1. PX4 SITL Container (`px4-sitl`)

**Image:** `px4-cube-orange:latest`
**IP Address:** `172.28.0.10`

The core simulation container running:
- **PX4 Autopilot SITL**: Software-in-the-loop simulation of the flight controller
- **Gazebo Garden**: High-fidelity physics simulation and 3D visualization
- **MAVLink Interface**: UDP telemetry output on port 14580

Key features:
- PX4 v1.14.x with full module support
- ARM GCC cross-compiler for firmware builds
- Persistent PX4 source in Docker volume

### 2. MAVLink Router Container (`mavlink-router`)

**Image:** `px4-cube-orange:latest`
**IP Address:** `172.28.0.11`

Central telemetry routing hub that:
- Receives MAVLink from PX4 SITL (UDP 14580)
- Forwards to QGroundControl (UDP 14550)
- Forwards to control applications (UDP 14540)
- Enables multiple clients to connect simultaneously

### 3. QGroundControl Container (`qgroundcontrol`)

**Image:** `qgroundcontrol:latest`
**IP Address:** `172.28.0.20`

Ground control station providing:
- Real-time telemetry visualization
- Mission planning interface
- Parameter configuration
- Flight log analysis

Uses X11 forwarding for GUI display on host.

### 4. Control Container (`control`)

**Image:** `px4-cube-orange:latest`
**IP Address:** `172.28.0.30`

Python application environment for:
- Running autonomous flight scripts
- MAVSDK-based vehicle control
- Custom mission execution
- Integration testing

## Network Architecture

### Docker Network: `px4-net`

All containers communicate over a dedicated bridge network:

| Container      | IP Address   | Ports                                  |
| -------------- | ------------ | -------------------------------------- |
| px4-sitl       | 172.28.0.10  | 14580/udp (MAVLink out)                |
| mavlink-router | 172.28.0.11  | 14580/udp (in), routes to 14550, 14540 |
| qgroundcontrol | 172.28.0.20  | 14550/udp (MAVLink in)                 |
| control        | 172.28.0.30  | 14540/udp (MAVLink in)                 |
| dev            | 172.28.0.50  | (interactive)                          |
| test-runner    | 172.28.0.100 | (tests)                                |

### MAVLink Message Flow

```
PX4 SITL ──UDP:14580──► MAVLink Router ──UDP:14550──► QGroundControl
                              │
                              └──UDP:14540──► Control Scripts
```

## Data Flow

### Telemetry Flow (SITL → GCS)

1. PX4 SITL generates telemetry (position, attitude, battery, etc.)
2. Telemetry encoded as MAVLink messages
3. Sent via UDP to MAVLink Router (port 14580)
4. Router forwards to QGC (14550) and control apps (14540)
5. QGC displays real-time data
6. Control scripts process data for autonomous operations

### Command Flow (GCS → SITL)

1. User issues command in QGC (arm, takeoff, waypoint)
2. Command encoded as MAVLink message
3. Sent to MAVLink Router
4. Router forwards to PX4 SITL
5. SITL executes command
6. Acknowledgment sent back through the same path

## Docker Compose Profiles

The environment supports multiple operational profiles:

| Profile    | Services Started                                  | Use Case                                    |
| ---------- | ------------------------------------------------- | ------------------------------------------- |
| `full`     | px4-sitl, mavlink-router, qgroundcontrol, control | Complete development with GUI               |
| `headless` | px4-sitl, mavlink-router, control                 | CI/CD, automated testing                    |
| `sitl`     | px4-sitl                                          | Simulation only                             |
| `dev`      | dev                                               | Interactive development shell               |
| `hitl`     | hitl                                              | Hardware-in-the-loop with real Cube+ Orange |
| `test`     | test-runner                                       | Run integration tests                       |

## Volume Management

### Persistent Volumes

| Volume                 | Mount Point                            | Purpose                             |
| ---------------------- | -------------------------------------- | ----------------------------------- |
| `px4-autopilot-source` | `/workspace/PX4-Autopilot`             | PX4 source code (survives rebuilds) |
| `qgc-config`           | `/home/qgc/.config/QGroundControl.org` | QGC settings                        |

### Bind Mounts

| Host Path        | Container Path        | Purpose             |
| ---------------- | --------------------- | ------------------- |
| `./config`       | `/workspace/config`   | Configuration files |
| `./logs`         | `/workspace/logs`     | Log files           |
| `./examples`     | `/workspace/examples` | Flight scripts      |
| `./scripts`      | `/workspace/scripts`  | Utility scripts     |
| `/tmp/.X11-unix` | `/tmp/.X11-unix`      | X11 display socket  |

## X11 Display Forwarding

GUI applications (Gazebo, QGroundControl) render on the host display:

1. Host X11 socket mounted into containers
2. `DISPLAY` environment variable passed through
3. `xhost +local:docker` allows container access
4. Applications render via host GPU (Intel Mesa drivers)

## Security Considerations

- Containers run as non-root users (`px4dev`, `qgc`)
- No `--privileged` flag except for HITL mode
- Network isolated to `px4-net` bridge
- Host filesystem access limited to specific bind mounts

## Scaling and Multi-Vehicle

The architecture supports multi-vehicle simulation by:

1. Running multiple `px4-sitl` instances with different `VEHICLE_ID`
2. Configuring MAVLink Router for multiple endpoints
3. Each vehicle gets unique MAV_SYS_ID

Example multi-vehicle setup:
```yaml
px4-sitl-1:
  environment:
    VEHICLE_ID: 1
    MAV_SYS_ID: 1

px4-sitl-2:
  environment:
    VEHICLE_ID: 2
    MAV_SYS_ID: 2
```

## Future Extensions

### ROS2 Integration

When ROS2 support is needed:
1. Add Micro-XRCE-DDS Agent to px4-sitl container
2. Configure DDS domain for ROS2 communication
3. Add ROS2 nodes as additional containers

### AI/ML Integration

For computer vision or ML workloads:
1. Mount GPU into containers (NVIDIA Docker)
2. Add inference containers
3. Connect to MAVLink for autonomous control

## File Structure Reference

```
hailo_drone_control/
├── docker/
│   ├── Dockerfile              # PX4 + Gazebo image
│   ├── Dockerfile.qgc          # QGroundControl image
│   └── entrypoint.sh           # Container startup logic
├── config/
│   ├── drone_config.yml        # Vehicle configuration
│   ├── mavlink-router.conf     # Routing rules
│   └── params/                 # PX4 parameter files
├── scripts/
│   ├── px4ctl.sh               # Main CLI tool
│   ├── wait_for_mavlink.py     # Health check
│   ├── setup_udev.sh           # Device rules
│   └── post_create.sh          # Dev container init
├── examples/
│   └── hover_rotate.py         # Demo flight script
├── tests/
│   ├── test_environment.py     # Unit tests
│   └── test_integration.py     # E2E tests
├── docker-compose.yml          # Service definitions
└── README.md                   # User documentation
```

