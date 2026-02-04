/open_qgc = Use the run_terminal_cmd tool to execute "xhost +local:docker && docker compose --profile full up -d qgroundcontrol && docker compose logs -f qgroundcontrol" to open QGroundControl GUI.

## Context
This command opens QGroundControl (QGC) which is the ground control station for monitoring and controlling the drone. It:
1. Enables X11 forwarding for Docker containers
2. Starts the QGC container if not running
3. Shows the QGC logs

Prerequisites:
- X11 display server must be running
- DISPLAY environment variable should be set (usually :0 or :1)

If QGC doesn't appear, try running `export DISPLAY=:0` first, or install QGC directly on your host machine from https://docs.qgroundcontrol.com/

