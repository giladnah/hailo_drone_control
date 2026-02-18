# Open Source Solutions Reference

This document catalogs well-documented, tested open-source solutions that can be reused or integrated into the PX4 Cube+ Orange development environment.

## Table of Contents

- [Complete Environment Solutions](#complete-environment-solutions)
- [MAVLink Communication Libraries](#mavlink-communication-libraries)
- [MAVLink Routing](#mavlink-routing)
- [Simulation Frameworks](#simulation-frameworks)
- [Docker & Containerization](#docker--containerization)
- [ROS2 Integration](#ros2-integration)
- [Testing Frameworks](#testing-frameworks)
- [Community Projects](#community-projects)
- [Official Documentation](#official-documentation)

---

## Complete Environment Solutions

### PX4-Containers (Official)

| Attribute | Value |
|-----------|-------|
| Repository | [PX4/PX4-containers](https://github.com/PX4/PX4-containers) |
| License | BSD-3-Clause |
| Stars | 95+ |
| Status | Official, actively maintained |

**Description**: Official PX4 project providing build scripts for Docker containers running various PX4 setups, including SITL with ROS/ROS2.

**Reusable Components**:
- Pre-built Docker images (`px4io/px4-dev-*`)
- Dockerfile patterns for simulation environments
- CI/CD integration examples

**Integration Notes**:
- Can replace custom Dockerfile with official base images
- Reduces maintenance burden
- Ensures compatibility with PX4 updates

### PX4-Autopilot (Official)

| Attribute | Value |
|-----------|-------|
| Repository | [PX4/PX4-Autopilot](https://github.com/PX4/PX4-Autopilot) |
| License | BSD-3-Clause |
| Stars | 8,000+ |
| Status | Official, actively maintained |

**Description**: The official PX4 autopilot firmware repository, containing all flight control code, simulation tools, and configuration files.

**Reusable Components**:
- Official airframe configurations (`ROMFS/px4fmu_common/init.d/airframes/`)
- SITL simulation scripts
- Parameter reference files

---

## MAVLink Communication Libraries

### MAVSDK-Python (Currently Used)

| Attribute | Value |
|-----------|-------|
| Repository | [mavlink/MAVSDK-Python](https://github.com/mavlink/MAVSDK-Python) |
| License | BSD-3-Clause |
| Documentation | [mavsdk.mavlink.io](https://mavsdk.mavlink.io/main/en/python/) |
| Status | Official, actively maintained |

**Description**: Official Python bindings for MAVSDK, providing a high-level API for MAVLink communication.

**Key Features**:
- Async/await support
- Type hints
- Comprehensive telemetry access
- Mission planning
- Offboard control
- Geofence management

**Example Scripts** (from official repository):
- `takeoff_and_land.py` - Basic flight operations
- `mission.py` - Waypoint mission upload and execution
- `offboard_velocity_ned.py` - Velocity control
- `telemetry.py` - Telemetry subscription
- `geofence.py` - Geofence configuration

### pymavlink (Currently Used)

| Attribute | Value |
|-----------|-------|
| Repository | [ArduPilot/pymavlink](https://github.com/ArduPilot/pymavlink) |
| License | LGPL-3.0 |
| Status | Official, actively maintained |

**Description**: Low-level MAVLink Python library for direct protocol access.

**Use Cases**:
- Custom MAVLink message handling
- Protocol debugging
- Low-level sensor access

### DroneKit-Python (Alternative)

| Attribute | Value |
|-----------|-------|
| Repository | [dronekit/dronekit-python](https://github.com/dronekit/dronekit-python) |
| License | Apache-2.0 |
| Status | Mature, community maintained |

**Description**: Alternative to MAVSDK with different API design.

**When to Consider**:
- Legacy project compatibility
- Specific feature requirements not in MAVSDK
- Synchronous programming preference

---

## MAVLink Routing

### mavlink-router (Currently Used)

| Attribute | Value |
|-----------|-------|
| Repository | [mavlink-router/mavlink-router](https://github.com/mavlink-router/mavlink-router) |
| License | Apache-2.0 |
| Status | Official, actively maintained |

**Description**: High-performance MAVLink routing daemon written in C.

**Features**:
- UDP/TCP/Serial endpoint support
- Multiple simultaneous connections
- Low latency
- Minimal resource usage

**Configuration Example**:
```ini
[General]
TcpServerPort = 5760

[UdpEndpoint sitl]
Mode = Normal
Address = 127.0.0.1
Port = 14580

[UdpEndpoint qgc]
Mode = Normal
Address = 127.0.0.1
Port = 14550
```

### MAVProxy (Alternative)

| Attribute | Value |
|-----------|-------|
| Repository | [ArduPilot/MAVProxy](https://github.com/ArduPilot/MAVProxy) |
| License | GPL-3.0 |
| Status | Official, actively maintained |

**Description**: Python-based MAVLink proxy with advanced features.

**When to Consider**:
- Interactive debugging
- Custom message filtering
- Plugin architecture needs

---

## Simulation Frameworks

### Gazebo Garden (Currently Used)

| Attribute | Value |
|-----------|-------|
| Repository | [gazebosim/gz-sim](https://github.com/gazebosim/gz-sim) |
| Documentation | [gazebosim.org](https://gazebosim.org/docs/garden/) |
| License | Apache-2.0 |
| Status | Official, actively maintained |

**Description**: Modern physics simulator for robotics, successor to Gazebo Classic.

**Features**:
- High-fidelity physics
- Sensor simulation
- ROS2 integration
- Web-based visualization

### jMAVSim (Alternative)

| Attribute | Value |
|-----------|-------|
| Repository | [PX4/jMAVSim](https://github.com/PX4/jMAVSim) |
| License | BSD-3-Clause |
| Status | Official, maintenance mode |

**Description**: Lightweight Java-based simulator for quick testing.

**When to Consider**:
- Fast iteration during development
- Limited system resources
- Basic flight testing

---

## Docker & Containerization

### Official PX4 Docker Images

Available on Docker Hub under `px4io/`:

| Image | Purpose |
|-------|---------|
| `px4io/px4-dev-base` | Base development environment |
| `px4io/px4-dev-simulation` | SITL without GUI |
| `px4io/px4-dev-simulation-gazebo` | Full Gazebo simulation |
| `px4io/px4-dev-ros2-humble` | ROS2 Humble integration |

**Usage Example**:
```dockerfile
FROM px4io/px4-dev-simulation-gazebo:latest

# Add custom configuration
COPY config/ /workspace/config/
```

### Docker Compose Patterns

**Multi-service architecture** (as implemented in this project):
- `px4-sitl` - PX4 SITL + Gazebo
- `mavlink-router` - Telemetry routing
- `qgroundcontrol` - Ground control station
- `control` - Python control scripts

**Profile-based activation**:
```bash
docker compose --profile sitl up    # Simulation only
docker compose --profile full up    # Complete stack
docker compose --profile dev run dev bash  # Development shell
```

---

## ROS2 Integration

### Micro-XRCE-DDS Agent

| Attribute | Value |
|-----------|-------|
| Repository | [eProsima/Micro-XRCE-DDS-Agent](https://github.com/eProsima/Micro-XRCE-DDS-Agent) |
| Documentation | [micro-xrce-dds.readthedocs.io](https://micro-xrce-dds.readthedocs.io/) |
| License | Apache-2.0 |
| Status | Official, actively maintained |

**Description**: Bridge between PX4's uORB messaging and ROS2 DDS.

**Integration Steps**:
1. Build agent from source or use Docker image
2. Configure PX4 with XRCE-DDS client
3. Launch agent alongside PX4 SITL
4. Access PX4 topics via ROS2

### PX4 ROS2 Packages

| Package | Purpose |
|---------|---------|
| `px4_msgs` | ROS2 message definitions |
| `px4_ros_com` | Communication examples |

---

## Testing Frameworks

### pytest (Currently Used)

**Best Practices for PX4 Testing**:
- Use async fixtures for MAVSDK connections
- Implement proper timeout handling
- Separate unit tests from integration tests
- Mock MAVLink connections for unit tests

**Example Test Structure**:
```python
@pytest.mark.asyncio
async def test_heartbeat_received():
    drone = System()
    await drone.connect(system_address="udp://localhost:14540")

    async for state in drone.core.connection_state():
        if state.is_connected:
            assert True
            return

    pytest.fail("No heartbeat received")
```

---

## Community Projects

### AntonSHBK/dron_px4_ros2_docker

| Attribute | Value |
|-----------|-------|
| Repository | [AntonSHBK/dron_px4_ros2_docker](https://github.com/AntonSHBK/dron_px4_ros2_docker) |
| License | Apache-2.0 |
| Status | Community maintained |

**Reusable Patterns**:
- Docker + ROS2 Humble + PX4 integration
- Launch file organization
- RViz visualization setup

### OSRF Drone Demo

| Attribute | Value |
|-----------|-------|
| Repository | [osrf/drone_demo](https://github.com/osrf/drone_demo) |
| License | Apache-2.0 |
| Status | Reference implementation |

**Reusable Patterns**:
- Complete system architecture
- SITL launcher implementation
- QGroundControl integration
- System test examples

### drone_toolbox_ext_control_template

| Attribute | Value |
|-----------|-------|
| Repository | [cor-drone-dev/drone_toolbox_ext_control_template](https://github.com/cor-drone-dev/drone_toolbox_ext_control_template) |
| License | MIT |
| Status | Template/reference |

**Reusable Patterns**:
- External controller interface
- PX4 control integration
- Configuration management

---

## Official Documentation

### Primary Resources

| Resource | URL |
|----------|-----|
| PX4 User Guide | https://docs.px4.io/ |
| PX4 Developer Guide | https://dev.px4.io/ |
| MAVSDK Python | https://mavsdk.mavlink.io/main/en/python/ |
| MAVLink Protocol | https://mavlink.io/ |
| Gazebo Garden | https://gazebosim.org/docs/garden/ |
| QGroundControl | https://docs.qgroundcontrol.com/ |

### Parameter References

| Reference | URL |
|-----------|-----|
| Full Parameter List | https://docs.px4.io/main/en/advanced_config/parameter_reference.html |
| Airframe Reference | https://docs.px4.io/main/en/airframes/airframe_reference.html |
| Multicopter Tuning | https://docs.px4.io/main/en/config_mc/pid_tuning_guide_multicopter.html |

### Community Resources

| Resource | URL |
|----------|-----|
| PX4 Discuss Forum | https://discuss.px4.io/ |
| PX4 Discord | https://discord.gg/dronecode |
| GitHub Issues | https://github.com/PX4/PX4-Autopilot/issues |

---

## Integration Recommendations

### High Priority (Immediate Value)

1. **Use Official PX4 Docker Base Images**
   - Reduces maintenance burden
   - Ensures compatibility with PX4 updates
   - Access to pre-configured environments

2. **Leverage MAVSDK-Python Examples**
   - Official patterns for common operations
   - Well-tested code
   - Active community support

3. **Validate Parameters Against Official Sets**
   - Use official parameter reference
   - Test with default values first
   - Document any custom tuning

### Medium Priority (Near-term)

1. **Standardize Configuration Format**
   - Consider PX4 native parameter format
   - Document YAML extensions
   - Ensure tool compatibility

2. **Expand Test Coverage**
   - Adopt PX4 test patterns
   - Add integration tests
   - Implement CI/CD pipeline

### Low Priority (Future)

1. **ROS2 Integration**
   - Plan Micro-XRCE-DDS integration
   - Use official ROS2 packages
   - Follow PX4 ROS2 documentation

2. **Multi-vehicle Support**
   - Reference community implementations
   - Plan network architecture
   - Test with multiple SITL instances

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-03 | 1.0 | Initial documentation |

---

## Contributing

When adding new open-source solutions to this document:

1. Verify the project is actively maintained
2. Confirm license compatibility
3. Test integration with current stack
4. Document specific reusable components
5. Include usage examples where applicable

