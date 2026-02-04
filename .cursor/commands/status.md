/status = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh status" to check the status of all Docker containers.

## Context
This command shows the current state of all PX4 development containers:
- px4-sitl: The SITL simulator
- px4-control: Python script runner
- px4-test-runner: Test execution container
- qgroundcontrol: Ground control station (if running)

It also shows resource usage and any error states.

