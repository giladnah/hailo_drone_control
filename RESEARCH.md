# Research: Architecture and Implementation of a Containerized Development Environment

> **Note**: This document provides an academic/theoretical analysis of the architecture. For practical implementation details and operational documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

The technical landscape of unmanned aerial vehicle (UAV) engineering has undergone a significant paradigm shift toward containerized ecosystems to mitigate the inherent complexities of robotics software stacks. The Cube+ Orange, a high-performance flight controller based on the dual-core STM32H7 processor architecture, requires an intricate constellation of dependencies, including specific Real-Time Operating System (RTOS) toolchains, middleware such as Robot Operating System 2 (ROS2), and high-fidelity physics simulators like Gazebo. Establishing a robust development environment necessitates the isolation of these components from the host operating system to prevent dependency drift and ensure reproducibility across heterogeneous Ubuntu-based workstations. By adopting an architecture inspired by the Frigate NVR system—characterized by modular configuration mapping and environment-based service activation—developers can achieve a highly flexible and switchable environment for both Software-in-the-Loop (SITL) and Hardware-in-the-Loop (HITL) simulations. This report provides an exhaustive technical analysis of the design, implementation, and operational nuances of such an environment, specifically tailored for the Cube+ Orange ecosystem while deliberately excluding Hailo-based AI acceleration research to focus on core flight control and simulation integrity.

## Hardware Foundations of the Cube+ Orange Flight Controller

The Cube+ Orange, often identified as the successor to the Pixhawk 2.1 (Cube Black), represents a pinnacle in open-source autopilot hardware intended for commercial and industrial applications. The transition to the "Orange+" variant introduced the STM32H757ZI microcontroller, a significant upgrade over the STM32F4 series found in previous generations. This processor utilizes a dual-core architecture, featuring an ARM Cortex-M7 running at 400 MHz for primary flight algorithms and an ARM Cortex-M4 running at 200 MHz, providing substantial computational overhead for complex navigation and control tasks.

### Computational Architecture and Processor Characteristics

The dual-core nature of the STM32H757ZI is critical for high-reliability systems. The Cortex-M7 core handles time-critical flight calculations, while the Cortex-M4 can be leveraged for auxiliary tasks, reducing the risk of processing bottlenecks. In addition to the primary H7 processor, the Cube+ Orange maintains an STM32F103 failsafe co-processor, which operates as a redundant 32-bit ARM Cortex-M3 at 24 MHz. This co-processor ensures that manual override and basic stabilization remain available even if the primary FMU (Flight Management Unit) experiences a software failure.

| Processor Component    | Specification | Architecture  | Clock Speed      |
| ---------------------- | ------------- | ------------- | ---------------- |
| Main FMU (Core 1)      | STM32H757ZI   | ARM Cortex-M7 | 400 MHz          |
| Main FMU (Core 2)      | STM32H757ZI   | ARM Cortex-M4 | 200 MHz          |
| Failsafe Processor     | STM32F103     | ARM Cortex-M3 | 24 MHz           |
| Internal RAM           | 1 MB          | SRAM          | -                |
| Unified Internal Flash | 2 MB          | Dual-Bank     | Fully Accessible |

### Sensor Redundancy and Environmental Robustness

To maintain flight stability in adverse conditions, the Cube+ Orange integrates a triple-redundant Inertial Measurement Unit (IMU) system. This architecture consists of three sets of accelerometers and gyroscopes, two of which are mechanically isolated and temperature-controlled via a dedicated internal heating module. This internal heating ensures that the sensors operate within a stable thermal window, mitigating the effects of bias drift commonly encountered in cold-weather operations. The sensors are interfaced primarily through high-speed Serial Peripheral Interface (SPI) buses to ensure low-latency data acquisition.

| Sensor Type      | Specific Component   | Configuration            | Connectivity |
| ---------------- | -------------------- | ------------------------ | ------------ |
| IMU 1 (Isolated) | ICM42688p / ICM20948 | Redundant Accel/Gyro     | SPI          |
| IMU 2 (Isolated) | ICM20948 / ICM42688  | Redundant Accel/Gyro     | SPI          |
| IMU 3 (Fixed)    | ICM20649 / ICM45686  | Fixed Reference IMU      | SPI          |
| Barometers       | 2x MS5611            | High-Resolution Altitude | SPI          |
| Compass          | ICM20948             | Integrated Magnetometer  | SPI          |

Beyond standard flight sensors, the ADS-B carrier board included with the standard set incorporates a customized 1090 MHz receiver from uAvionix. This allows the autopilot to receive real-time location and attitude data from manned aircraft, facilitating automated collision avoidance and enhancing overall airspace safety.

## Docker-Based Environment Isolation and Toolchain Configuration

The primary objective of a Docker-based environment is to provide a standardized, immutable container that houses the entire flight control development stack. This approach prevents "dependency hell," where different projects require conflicting versions of Python libraries or compiler toolchains. For a Cube+ Orange environment, the container must encapsulate the PX4 or ArduPilot source code, the ARM GCC cross-compiler, and the simulation middleware.

### Base Image Selection and Middleware Integration

The architectural foundation typically utilizes the `osrf/ros:humble-desktop-full` image, which provides ROS2 Humble on Ubuntu 22.04 (Jammy Jellyfish). This choice is strategic, as ROS2 Humble is the current Long-Term Support (LTS) release favored for professional drone development. The "desktop-full" variant includes essential visualization tools like Rviz2 and Rqt, which are vital for debugging flight algorithms and sensor streams.

Specific Python dependency pinning is required within the Dockerfile to ensure compatibility with the autopilot's build system. A notable example is the empy package used for template-based code generation in PX4. While newer versions exist, version 3.3.4 is specifically required, as later versions introduced API changes that break the code generation process.

```dockerfile
RUN pip3 install empy==3.3.4 pyyaml jinja2 pyserial
```

### The Micro-XRCE-DDS Bridge

A critical component for modern PX4 development is the Micro-XRCE-DDS Agent. This agent serves as the communication bridge between the uORB messaging system used within the flight controller and the ROS2 Data Distribution Service (DDS) ecosystem. In the containerized environment, the agent must be built from source to match the client version running on the Cube+ Orange firmware. This enables real-time, bidirectional communication between the drone and off-board control applications.

## Architectural Patterns for Switchable Configurations

To fulfill the requirement for a "Frigate-like" switchable architecture, the environment must decouple the software stack from the specific vehicle configuration. Frigate achieves this through a centralized YAML configuration file that defines detector types, camera roles, and hardware acceleration presets. Applying this to drone development involves mapping vehicle-specific parameter files and environment variables into the container at runtime.

### Centralized Configuration Management

The drone development environment utilizes a `drone_config.yml` which, much like Frigate's `config.yml`, dictates the behavior of the system. This file defines parameters such as the vehicle frame type (e.g., x500 quadcopter vs. standard plane), the simulation mode (SITL or HITL), and the MAVLink routing endpoints. Environment variable substitution allows the same base configuration to be deployed across different physical drones by simply changing a `.env` file.

| Configuration Feature | Frigate NVR Implementation              | Drone Environment Implementation                |
| --------------------- | --------------------------------------- | ----------------------------------------------- |
| profiles              | Activates debug or production services. | Toggles SITL vs. HITL vs. Offboard modes.       |
| volumes               | Maps /config and /media paths.          | Maps /params, /logs, and /firmware paths.       |
| environment_vars      | Injects RTSP credentials and API keys.  | Injects VEHICLE_ID, AIRFRAME_ID, and SYSID.     |
| detectors             | Configures Coral TPU or OpenVINO.       | Configures Gazebo Garden or jMAVSim simulators. |

### Docker Compose Profiles for Operational Flexibility

Docker Compose Profiles enable the developer to adjust the application model for different workflows without maintaining separate compose files. In this environment, profiles are used to gate specific simulation services.

- **Profile sitl**: Launches the PX4/ArduPilot SITL binary and the Gazebo simulator for virtual testing.
- **Profile hitl**: Configures the USB serial bridge and starts the MAVLink-router to connect the container to the physical Cube+ Orange.
- **Profile dev**: Provides an interactive development shell with all build tools and VS Code extensions pre-loaded.

By running `docker compose --profile hitl up`, only the services required for hardware testing are activated, preserving host resources.

## Simulation Frameworks: SITL and HITL on Ubuntu

The development environment supports two distinct simulation paradigms: Software-in-the-Loop (SITL) and Hardware-in-the-Loop (HITL). Both are optimized for Ubuntu laptops, which are the recommended platform for PX4 and ArduPilot development due to their superior driver support and performance.

### Software-in-the-Loop (SITL) Implementation

SITL executes the autopilot code as a native Linux process. This allows for high-speed simulation, often faster than real-time, and enables testing of complex autonomous missions without the risk of hardware damage. The simulation stack typically comprises the autopilot process, a physics engine (Gazebo), and a Ground Control Station (QGroundControl).

For modern workflows, Gazebo Garden (part of the OSRF Ignition/Gazebo Sim lineage) is the preferred simulator. It provides superior physics accuracy, modern sensor plugins, and native uORB/DDS integration compared to the legacy Gazebo Classic. The communication between the autopilot and Gazebo occurs over a local network bridge using UDP or XRCE-DDS.

### Hardware-in-the-Loop (HITL) Implementation

HITL simulation involves running the actual firmware on the Cube+ Orange hardware while the physics and environment are simulated on the Ubuntu laptop. This is essential for testing the real-time performance of the H7 processor and validating that the firmware behaves correctly when running on physical hardware.

The HITL workflow requires several configuration steps:

- **Firmware Modification**: The PX4 firmware for the Cube+ Orange must be built with the `CONFIG_MODULE_SIMULATION_PWM_OUT_SIM=y` flag to allow the simulator to override motor outputs.
- **QGroundControl Configuration**: HITL must be enabled in the safety settings, and a "HIL" airframe (e.g., HIL Quadcopter x) must be selected.
- **Serial Bridge**: The simulator (jMAVSim or Gazebo) connects to the Cube+ Orange via a USB serial port (e.g., `/dev/ttyACM0`) at a high baud rate, typically 921600.

A primary nuance of the Cube+ Orange in HITL mode is its dual USB serial port behavior. On Linux, the board may appear as two separate `/dev/ttyACM*` devices. The development environment must be configured to correctly identify the primary FMU port for telemetry and the secondary port if serial passthrough or SLCAN functionality is required.

## Connectivity and Hardware Passthrough in Docker

Passing physical USB devices from the host Ubuntu system into a Docker container requires careful management of device paths and permissions. A major challenge is that USB device names (like `/dev/ttyACM0`) are not persistent and may change if the device is replugged or if other serial devices are connected.

### udev Rules for Persistent Device Naming

To ensure the development environment consistently finds the Cube+ Orange, udev rules are implemented on the host system to create predictable symlinks. By matching the vendor and product IDs—and uniquely, the hardware serial number—of the Cube+ Orange, a stable path such as `/dev/cube_orange` can be established.

```bash
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", ATTRS{idProduct}=="1016", SYMLINK+="cube_orange"
```

After applying these rules, the Docker container can map this persistent symlink:

```bash
docker run --device=/dev/cube_orange:/dev/ttyACM0 ...
```

### X11 Forwarding and GPU Acceleration

The Gazebo GUI must be forwarded from the container to the host's display server. This is achieved by mounting the X11 socket and passing the `DISPLAY` environment variable. To prevent lag and ensure smooth rendering of 3D models, GPU acceleration is mandatory. For laptops with NVIDIA GPUs, the `--gpus all` flag must be used in the Docker run command to allow the container to access the host's graphics drivers. If the driver fails to load, Gazebo may revert to software rendering, resulting in the "swrast" error and unplayable frame rates.

## MAVLink Routing and Network Topology

In a containerized environment, MAVLink telemetry must be routed between the autopilot (SITL or physical), the simulator, and the ground control station (QGC). MAVLink-Router is the preferred tool for this task due to its high performance and low overhead.

### Specialized Routing with MAVLink-Router

MAVLink-Router is written in C and designed specifically to route MAVLink packets from endpoint to endpoint. It acts as a central hub in the development environment, listening to the Cube+ Orange's serial stream and forwarding it to multiple UDP/TCP endpoints.

| Routing Configuration | Implementation Detail                                |
| --------------------- | ---------------------------------------------------- |
| Serial Input          | /dev/ttyACM0 (Physical Cube+ Orange).                |
| UDP Endpoint 1        | 127.0.0.1:14550 (Local QGroundControl).              |
| UDP Endpoint 2        | 172.17.0.1:14540 (Offboard API / MAVSDK).            |
| TCP Endpoint          | 0.0.0.0:5760 (MAVLink-over-TCP for Mission Planner). |

This setup mimics the Frigate architecture where a central service handles data distribution, allowing multiple "clients" (GCS, simulators, vision scripts) to subscribe to the drone's telemetry simultaneously.

### Network Isolation and Port Mapping

Docker's bridge network can sometimes interfere with MAVLink's reliance on UDP broadcasting. To mitigate this, explicit port mappings are defined in the `docker-compose.yml`. QGroundControl running on the host typically expects MAVLink data on UDP port 14550. By exposing this port and manually creating a "Comm Link" in QGC directed at the container's IP (e.g., 172.17.0.1), a stable telemetry link is maintained.

## VS Code Dev Containers and Collaborative Workflow

The use of VS Code Dev Containers transforms the development environment into a portable, code-defined workspace. The `.devcontainer` directory contains the configuration files necessary to rebuild the entire environment, ensuring that all developers on a team are using identical versions of compilers, libraries, and simulation models.

### The devcontainer.json Configuration

The `devcontainer.json` file orchestrates the container's interaction with the host system. It handles the automatic installation of VS Code extensions, such as the C/C++ tools and CMake integration, which are essential for navigating the massive PX4 and ArduPilot source bases.

```json
{
  "runArgs": ["--gpus", "all", "--privileged"],
  "forwardPorts": [...]
}
```

### Automation via Post-Create Scripts

A `postCreateCommand` is used to automate final workspace preparation. This script typically clones the autopilot source code (if not already present), initializes submodules, and builds the Micro-XRCE-DDS Agent. This "zero-touch" setup allows a developer to go from a fresh git clone to running a simulation in approximately 15 minutes, a task that traditionally took days of manual configuration.

## Parameter Management and Airframe Selection

Effective configuration management requires the ability to switch between different vehicle parameters and airframe definitions. This is achieved by utilizing version-controlled parameter files mapped into the container, similar to how Frigate maps camera-specific configurations.

### ArduPilot Parameter Logic

ArduPilot's SITL environment utilizes the `sim_vehicle.py` script, which supports an `--add-param-file` flag. This allows developers to load a specific set of parameters (e.g., PID gains for a 5-inch racer vs. a heavy-lift quadcopter) during the simulation's boot process.

- **-w Flag**: Wipes the virtual EEPROM (`eeprom.bin`) to ensure the simulation starts from a clean, known state.
- **-v Flag**: Selects the vehicle type (copter, plane, rover).
- **-f Flag**: Selects the specific frame configuration (e.g., hexa, octa, quad+).

### PX4 Parameter Loading Nuances

In PX4, the `param` tool within the shell allows for importing and exporting configuration sets. A critical insight for developers is that many parameters in PX4 are contingent on others being enabled. For example, a driver must be enabled before its specific configuration parameters are exposed in the system console. This often requires a two-step upload process in QGroundControl: uploading the initial parameters, rebooting the controller, and then uploading the remaining dependent values.

## Conclusion: A Unified Architecture for Autonomous Systems

The development of a containerized ecosystem for the Cube+ Orange flight controller represents a significant advancement in robotics engineering practices. By isolating the system environment within Docker, developers achieve a level of reproducibility and stability that is unattainable through traditional local installations. The adoption of a Frigate-inspired modular configuration pattern, facilitated by Docker Compose Profiles and YAML-based parameter mapping, allows for the effortless switching between multiple drone configurations and simulation modes.

This architecture provides a seamless bridge between the virtual world of SITL and the physical reality of HITL on Ubuntu laptops, ensuring that flight algorithms are validated against real hardware constraints. Furthermore, by strictly prioritizing core flight control and excluding Hailo-based AI research in this specific iteration, the environment maintains a focus on mission-critical stability and low-latency performance. As unmanned systems continue to scale in complexity, the integration of code-defined development environments, persistent hardware naming, and high-performance MAVLink routing will remain the cornerstone of professional UAV development.
