/stop_simulator = Use the run_terminal_cmd tool to execute "docker compose --profile full down" to stop all PX4 simulator containers.

## Context
This command stops all running Docker containers for the PX4 development environment:
- px4-sitl (SITL simulator + Gazebo)
- px4-control (Python control scripts)
- px4-test-runner (Test execution)
- qgroundcontrol (Ground control station)

It also removes the Docker network. Use `/start_simulator` to start everything again.

