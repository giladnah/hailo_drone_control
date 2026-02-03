#!/bin/bash
# Setup udev rules for persistent Cube+ Orange device naming
#
# This script creates udev rules that:
# 1. Create a persistent symlink /dev/cube_orange for the Cube+ Orange
# 2. Set appropriate permissions for non-root access
#
# Usage: sudo ./setup_udev.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (sudo)"
    exit 1
fi

# Define the udev rules file location
UDEV_RULES_FILE="/etc/udev/rules.d/99-cube-orange.rules"

log_info "Creating udev rules for Cube+ Orange..."

# Create the udev rules file
cat > "$UDEV_RULES_FILE" << 'EOF'
# Cube+ Orange Flight Controller udev rules
# This file creates persistent device names and sets permissions

# ==============================================
# Cube+ Orange (CubePilot) - Main FMU port
# ==============================================
# Vendor ID: 0x2dae (CubePilot)
# Product ID: 0x1016 (Cube Orange+)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", ATTRS{idProduct}=="1016", SYMLINK+="cube_orange", MODE="0666", GROUP="dialout"

# Alternative: Match by manufacturer string (fallback)
SUBSYSTEM=="tty", ATTRS{manufacturer}=="CubePilot", SYMLINK+="cube_orange_alt", MODE="0666", GROUP="dialout"

# ==============================================
# Cube Orange (older model)
# ==============================================
# Product ID: 0x1011 (Cube Orange, not Orange+)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", ATTRS{idProduct}=="1011", SYMLINK+="cube_orange_v1", MODE="0666", GROUP="dialout"

# ==============================================
# Cube Black (legacy support)
# ==============================================
# Product ID: 0x1001 (Cube Black / Pixhawk 2.1)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", ATTRS{idProduct}=="1001", SYMLINK+="cube_black", MODE="0666", GROUP="dialout"

# ==============================================
# Generic Pixhawk / PX4 devices
# ==============================================
# 3DR / Pixhawk vendor
SUBSYSTEM=="tty", ATTRS{idVendor}=="26ac", SYMLINK+="pixhawk_%n", MODE="0666", GROUP="dialout"

# Holybro vendor
SUBSYSTEM=="tty", ATTRS{idVendor}=="3162", SYMLINK+="holybro_%n", MODE="0666", GROUP="dialout"

# ==============================================
# USB Serial Converters (telemetry radios, etc.)
# ==============================================
# FTDI
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666", GROUP="dialout"

# Silicon Labs CP210x
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", MODE="0666", GROUP="dialout"

# Prolific PL2303
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", MODE="0666", GROUP="dialout"

# ==============================================
# Set permissions for /dev/ttyACM* and /dev/ttyUSB*
# ==============================================
KERNEL=="ttyACM[0-9]*", MODE="0666", GROUP="dialout"
KERNEL=="ttyUSB[0-9]*", MODE="0666", GROUP="dialout"
EOF

log_info "udev rules written to $UDEV_RULES_FILE"

# Reload udev rules
log_info "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

log_info "udev rules installed successfully!"

# Check if current user is in dialout group
CURRENT_USER="${SUDO_USER:-$USER}"
if ! groups "$CURRENT_USER" | grep -q dialout; then
    log_warn "User '$CURRENT_USER' is not in the 'dialout' group"
    log_info "Adding user to dialout group..."
    usermod -aG dialout "$CURRENT_USER"
    log_warn "You need to log out and log back in for group changes to take effect"
fi

echo ""
log_info "Setup complete!"
echo ""
echo "Device symlinks created:"
echo "  /dev/cube_orange     -> Cube Orange+ (primary)"
echo "  /dev/cube_orange_v1  -> Cube Orange (older model)"
echo "  /dev/cube_black      -> Cube Black / Pixhawk 2.1"
echo ""
echo "To verify, connect the Cube+ Orange and run:"
echo "  ls -la /dev/cube_orange"
echo ""
echo "To view connected USB devices:"
echo "  lsusb | grep -i cube"
echo "  dmesg | tail -20"

