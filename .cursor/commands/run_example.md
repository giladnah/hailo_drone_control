/run_example = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh run examples/hover_rotate.py" to run the hover and rotate example flight pattern.

## Context
This command runs a Python example script that demonstrates drone control using MAVSDK. The hover_rotate.py example:
1. Connects to the drone
2. Arms and takes off
3. Hovers at altitude
4. Rotates in place
5. Lands safely

Other available examples:
- `./scripts/px4ctl.sh run examples/simple_takeoff_land.py` - Basic takeoff and land
- `./scripts/px4ctl.sh run examples/mission_upload.py` - Waypoint mission
- `./scripts/px4ctl.sh run examples/offboard_velocity.py` - Velocity control
- `./scripts/px4ctl.sh run examples/telemetry_monitor.py` - Real-time telemetry

The simulator must be running first. Use `/start_simulator` if needed.

