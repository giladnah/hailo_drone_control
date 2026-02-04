/view_logs = Use the run_terminal_cmd tool to execute "docker compose logs -f px4-sitl" to view real-time PX4 SITL logs.

## Context
This command shows the live logs from the PX4 SITL simulator. Useful for debugging flight issues and seeing MAVLink messages.

Other log commands:
- `docker compose logs -f px4-sitl` - SITL logs
- `docker compose logs -f px4-control` - Control container logs
- `docker compose logs --tail 50 px4-sitl` - Last 50 lines only
- `docker compose logs` - All container logs

