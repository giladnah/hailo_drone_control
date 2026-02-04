/clean = Use the run_terminal_cmd tool to execute "docker compose down --volumes --remove-orphans && docker system prune -f" to clean up Docker resources.

## Context
This command performs a thorough cleanup of the Docker environment:
- Stops and removes all containers
- Removes associated volumes
- Removes orphan containers
- Prunes unused Docker resources

Use this when:
- Disk space is running low
- You want a completely fresh start
- There are container conflicts or issues

Note: This will remove PX4 build caches, so the next build may take longer.

