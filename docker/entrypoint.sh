#!/bin/bash
# Entrypoint script for PX4 development container
# Handles SITL/HITL mode detection and service startup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Default values
SIM_MODE=${SIM_MODE:-"sitl"}
VEHICLE_ID=${VEHICLE_ID:-1}
AIRFRAME=${AIRFRAME:-"x500"}
MAV_SYS_ID=${MAV_SYS_ID:-1}

# MAVLink ports
QGC_PORT=${QGC_PORT:-14550}
MAVSDK_PORT=${MAVSDK_PORT:-14540}
SITL_PORT=${SITL_PORT:-14580}

# Serial device for HITL
SERIAL_DEVICE=${SERIAL_DEVICE:-"/dev/ttyACM0"}
SERIAL_BAUD=${SERIAL_BAUD:-921600}

# PX4 directory
PX4_DIR=${PX4_HOME:-"/workspace/PX4-Autopilot"}

# Function to check if PX4 source is present
check_px4_source() {
    if [ ! -f "$PX4_DIR/Makefile" ]; then
        log_warn "PX4 source not found at $PX4_DIR"
        log_info "Clone PX4 with: git clone https://github.com/PX4/PX4-Autopilot.git --recursive"
        return 1
    fi
    return 0
}

# Function to start MAVLink-Router
start_mavlink_router() {
    local config_file="/workspace/config/mavlink-router.conf"

    if [ -f "$config_file" ]; then
        log_info "Starting MAVLink-Router with config: $config_file"
        mavlink-routerd -c "$config_file" &
    else
        log_warn "MAVLink-Router config not found, using default routing"

        if [ "$SIM_MODE" = "hitl" ]; then
            # HITL: route from serial device
            mavlink-routerd -e "127.0.0.1:$QGC_PORT" -e "127.0.0.1:$MAVSDK_PORT" "$SERIAL_DEVICE:$SERIAL_BAUD" &
        else
            # SITL: route from UDP
            mavlink-routerd -e "127.0.0.1:$QGC_PORT" -e "127.0.0.1:$MAVSDK_PORT" "0.0.0.0:$SITL_PORT" &
        fi
    fi

    # Give router time to start
    sleep 1
}

# Function to start SITL simulation
start_sitl() {
    log_info "Starting PX4 SITL simulation..."
    log_info "  Vehicle: $AIRFRAME"
    log_info "  System ID: $MAV_SYS_ID"

    if ! check_px4_source; then
        log_error "Cannot start SITL without PX4 source"
        return 1
    fi

    cd "$PX4_DIR"

    # Build if necessary
    if [ ! -d "build/px4_sitl_default" ]; then
        log_info "Building PX4 SITL..."
        make px4_sitl_default
    fi

    # Start SITL with Gazebo
    log_info "Launching PX4 SITL with Gazebo..."
    PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL=$AIRFRAME make px4_sitl gz_$AIRFRAME
}

# Function to wait for HITL connection
start_hitl() {
    log_info "Starting HITL mode..."
    log_info "  Serial Device: $SERIAL_DEVICE"
    log_info "  Baud Rate: $SERIAL_BAUD"

    # Check if serial device exists
    if [ ! -e "$SERIAL_DEVICE" ]; then
        log_error "Serial device $SERIAL_DEVICE not found"
        log_info "Make sure the Cube+ Orange is connected and the device is passed through"
        return 1
    fi

    # Start MAVLink router for HITL
    start_mavlink_router

    log_info "HITL mode ready. MAVLink router forwarding from $SERIAL_DEVICE"
    log_info "Connect QGroundControl to UDP port $QGC_PORT"

    # Keep container running
    tail -f /dev/null
}

# Function for development mode
start_dev() {
    log_info "Starting development mode..."
    log_info "Available commands:"
    log_info "  make px4_sitl_default gz_x500  - Build and run SITL"
    log_info "  make px4_fmu-v6x_default       - Build firmware for Cube+ Orange"

    # Execute the provided command or start bash
    if [ $# -gt 0 ]; then
        exec "$@"
    else
        exec /bin/bash
    fi
}

# Trap for graceful shutdown
cleanup() {
    log_info "Shutting down..."

    # Kill MAVLink-Router if running
    pkill -f mavlink-routerd 2>/dev/null || true

    # Kill PX4 SITL if running
    pkill -f px4 2>/dev/null || true

    # Kill Gazebo if running
    pkill -f gz 2>/dev/null || true

    exit 0
}

trap cleanup SIGTERM SIGINT

# Main entry point
main() {
    log_info "PX4 Development Container Starting..."
    log_info "Mode: $SIM_MODE"

    case "$SIM_MODE" in
        sitl)
            start_mavlink_router
            start_sitl
            ;;
        hitl)
            start_hitl
            ;;
        dev|*)
            start_dev "$@"
            ;;
    esac
}

main "$@"

