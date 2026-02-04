#!/bin/bash
# px4ctl.sh - PX4 Development Environment Control Script
#
# Main CLI tool for managing the containerized PX4 development stack.
#
# Usage:
#   ./scripts/px4ctl.sh <command> [options]
#
# Commands:
#   start [profile]   Start the environment (default: full)
#   stop              Stop all running services
#   restart [profile] Restart the environment
#   status            Show status of all services
#   logs [service]    Tail logs (all services or specific one)
#   shell             Open interactive development shell
#   run <script>      Run a Python script in the control container
#   test              Run integration tests
#   build             Build/rebuild Docker images
#   clean             Remove containers and volumes

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Default profile
DEFAULT_PROFILE="full"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║         PX4 Cube+ Orange Development Environment          ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start [profile]   Start environment (profiles: full, headless, sitl, dev)"
    echo "  stop              Stop all running services"
    echo "  restart [profile] Restart the environment"
    echo "  status            Show status of all services"
    echo "  logs [service]    Tail logs (px4-sitl, qgroundcontrol, mavlink-router, control)"
    echo "  shell             Open interactive development shell"
    echo "  run <script>      Run a Python script in the control container"
    echo "  test              Run integration tests"
    echo "  build             Build/rebuild Docker images"
    echo "  clean             Remove containers, networks, and optionally volumes"
    echo ""
    echo "Examples:"
    echo "  $0 start              # Start full stack with GUI"
    echo "  $0 start headless     # Start without GUI (for CI)"
    echo "  $0 run examples/hover_rotate.py"
    echo "  $0 logs px4-sitl"
    echo ""
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running or you don't have permission."
        exit 1
    fi
}

check_x11() {
    if [ -z "$DISPLAY" ]; then
        log_warn "DISPLAY not set. GUI applications may not work."
        return 1
    fi

    # Allow local Docker connections to X11
    xhost +local:docker &> /dev/null || true
    return 0
}

wait_for_service() {
    local service=$1
    local max_wait=${2:-60}
    local count=0

    log_info "Waiting for $service to be ready..."

    while [ $count -lt $max_wait ]; do
        if docker compose -f "$PROJECT_DIR/docker-compose.yml" ps "$service" 2>/dev/null | grep -q "running"; then
            log_info "$service is running"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done

    log_error "$service did not start within ${max_wait}s"
    return 1
}

cmd_start() {
    local profile=${1:-$DEFAULT_PROFILE}

    print_banner
    log_step "Starting PX4 environment with profile: $profile"

    check_docker

    # Check X11 for GUI profiles
    if [[ "$profile" == "full" || "$profile" == "sitl" || "$profile" == "qgc" ]]; then
        if check_x11; then
            log_info "X11 display available: $DISPLAY"
        else
            log_warn "X11 not available. Consider using 'headless' profile."
        fi
    fi

    cd "$PROJECT_DIR"

    # Build images if needed
    log_step "Building Docker images (if needed)..."
    docker compose --profile "$profile" build

    # Start services
    log_step "Starting services..."
    docker compose --profile "$profile" up -d

    # Wait for key services
    sleep 3

    log_info "Services started. Use '$0 status' to check status."
    log_info "Use '$0 logs' to view logs."

    if [[ "$profile" == "full" ]]; then
        echo ""
        log_info "QGroundControl should open automatically."
        log_info "Run '$0 run examples/hover_rotate.py' to test the drone."
    fi
}

cmd_stop() {
    print_banner
    log_step "Stopping all services..."

    cd "$PROJECT_DIR"

    # Stop all profiles
    docker compose --profile full --profile headless --profile sitl --profile dev --profile hitl --profile test down

    log_info "All services stopped."
}

cmd_restart() {
    local profile=${1:-$DEFAULT_PROFILE}

    cmd_stop
    sleep 2
    cmd_start "$profile"
}

cmd_status() {
    print_banner
    log_step "Service Status"
    echo ""

    cd "$PROJECT_DIR"

    # Show running containers
    docker compose ps -a 2>/dev/null || echo "No services running"

    echo ""
    log_step "Network Status"
    docker network inspect px4-net --format '{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{println}}{{end}}' 2>/dev/null || echo "Network not created"
}

cmd_logs() {
    local service=$1

    cd "$PROJECT_DIR"

    if [ -z "$service" ]; then
        log_info "Tailing logs for all services (Ctrl+C to exit)..."
        docker compose logs -f
    else
        log_info "Tailing logs for $service (Ctrl+C to exit)..."
        docker compose logs -f "$service"
    fi
}

cmd_shell() {
    print_banner
    log_step "Opening development shell..."

    cd "$PROJECT_DIR"

    # Check if dev container is running
    if docker compose ps dev 2>/dev/null | grep -qE "(running|Up)"; then
        docker compose exec dev bash
    else
        # Start dev container
        docker compose --profile dev run --rm dev bash
    fi
}

cmd_run() {
    local script=$1
    shift || true
    local extra_args="$@"

    if [ -z "$script" ]; then
        log_error "Please specify a script to run."
        echo "Usage: $0 run <script> [args]"
        echo "Example: $0 run examples/hover_rotate.py --altitude 10"
        exit 1
    fi

    print_banner
    log_step "Running script: $script $extra_args"

    cd "$PROJECT_DIR"

    # Check if control container is running (part of full/headless profile)
    if docker compose ps control 2>/dev/null | grep -qE "(running|Up)"; then
        docker compose exec control python3 "/workspace/$script" $extra_args
    else
        # Check if px4-sitl is running (platform is up)
        if docker compose ps px4-sitl 2>/dev/null | grep -qE "(running|Up)"; then
            # Platform is running, start control container attached to same network
            log_info "Starting control container..."
            docker compose --profile full up -d control
            sleep 2
            docker compose exec control python3 "/workspace/$script" $extra_args
        else
            log_error "PX4 SITL is not running. Please start the platform first:"
            log_error "  $0 start"
            exit 1
        fi
    fi
}

cmd_test() {
    local test_path=${1:-"tests/"}

    print_banner
    log_step "Running tests: $test_path"

    cd "$PROJECT_DIR"

    # Check if platform is running
    if ! docker compose ps px4-sitl 2>/dev/null | grep -qE "(running|Up)"; then
        log_error "PX4 SITL is not running. Please start the platform first:"
        log_error "  $0 start"
        exit 1
    fi

    # Check if test-runner container is running
    if docker compose ps test-runner 2>/dev/null | grep -qE "(running|Up)"; then
        docker compose exec test-runner python3 -m pytest "$test_path" -v --tb=short
    else
        # Start test-runner and run tests
        log_info "Starting test-runner container..."
        docker compose --profile full up -d test-runner
        sleep 2
        docker compose exec test-runner python3 -m pytest "$test_path" -v --tb=short
    fi
}

cmd_build() {
    print_banner
    log_step "Building Docker images..."

    cd "$PROJECT_DIR"

    docker compose --profile full build --no-cache

    log_info "Build complete."
}

cmd_clean() {
    print_banner
    log_warn "This will remove all containers and networks."

    read -p "Also remove volumes (PX4 source, QGC config)? [y/N] " -n 1 -r
    echo

    cd "$PROJECT_DIR"

    # Stop and remove containers
    docker compose --profile full --profile headless --profile sitl --profile dev --profile hitl --profile test down --remove-orphans

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_step "Removing volumes..."
        docker volume rm px4-autopilot-source qgc-config 2>/dev/null || true
    fi

    log_info "Cleanup complete."
}

# Main entry point
main() {
    local command=${1:-help}
    shift || true

    case "$command" in
        start)
            cmd_start "$@"
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart "$@"
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs "$@"
            ;;
        shell)
            cmd_shell
            ;;
        run)
            cmd_run "$@"
            ;;
        test)
            cmd_test
            ;;
        build)
            cmd_build
            ;;
        clean)
            cmd_clean
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"

