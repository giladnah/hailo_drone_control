/start_simulator = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh start" to start the PX4 SITL simulator with all services.

## Context
This command starts the full PX4 development environment including:
- PX4 SITL (Software-in-the-Loop) simulation
- Gazebo physics simulator
- MAVLink router for telemetry distribution
- QGroundControl (if X11 is available)
- Control and test-runner containers

The simulator runs in detached mode. Use `/status` to check if everything is running.

