/build = Use the run_terminal_cmd tool to execute "./scripts/px4ctl.sh build" to rebuild the Docker images.

## Context
This command rebuilds the PX4 development Docker images. Use this when:
- Dockerfile has been modified
- Dependencies have changed
- You need a fresh build

The build process may take several minutes as it compiles PX4 and installs all dependencies.

