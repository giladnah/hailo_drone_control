/restart = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh stop && ./scripts/px4ctl.sh start" to restart the entire simulator environment.

## Context
This command performs a full restart of the PX4 development environment. Useful when:
- The simulator becomes unresponsive
- Configuration changes need to be applied
- After pulling new code or updating Docker images

It stops all containers cleanly and then starts them again.

