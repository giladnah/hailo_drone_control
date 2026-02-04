#!/bin/bash
#
# setup_pi.sh - Raspberry Pi Setup Script for MAVLink Connection
#
# This script configures a Raspberry Pi for connecting to a PX4 autopilot
# via UART (TELEM2) or WiFi. It installs required software and configures
# the serial port for communication.
#
# Hardware Connection (UART to TELEM2):
#   Cube+ Orange TELEM2  -->  Raspberry Pi GPIO
#   TX  ─────────────────────  RX (GPIO 15, Pin 10)
#   RX  ─────────────────────  TX (GPIO 14, Pin 8)
#   GND ─────────────────────  GND (Any ground pin)
#
# Usage:
#   curl -sSL <url>/setup_pi.sh | bash
#   # or
#   ./setup_pi.sh
#
# Options:
#   --skip-uart     Skip UART configuration (WiFi only)
#   --skip-reboot   Don't prompt for reboot
#   --help          Show this help message
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PYTHON_MIN_VERSION="3.8"
MAVSDK_VERSION=""  # Empty = latest
UART_BAUD=57600

# Flags
SKIP_UART=false
SKIP_REBOOT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-uart)
            SKIP_UART=true
            shift
            ;;
        --skip-reboot)
            SKIP_REBOOT=true
            shift
            ;;
        --help|-h)
            head -40 "$0" | grep '^#' | cut -c3-
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
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
    echo -e "\n${BLUE}==>${NC} $1"
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    log_step "Checking system..."
    
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(cat /proc/device-tree/model)
        log_info "Detected: $MODEL"
    else
        log_warn "Could not detect Raspberry Pi model"
        log_warn "This script is designed for Raspberry Pi"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Check Python version
check_python() {
    log_step "Checking Python..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        log_info "Python version: $PYTHON_VERSION"
        
        # Compare versions
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"; then
            log_info "Python version OK (>= $PYTHON_MIN_VERSION)"
        else
            log_error "Python $PYTHON_MIN_VERSION or higher required"
            log_info "Installing Python 3..."
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv
        fi
    else
        log_error "Python 3 not found"
        log_info "Installing Python 3..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    fi
}

# Update system packages
update_system() {
    log_step "Updating system packages..."
    
    sudo apt-get update
    sudo apt-get upgrade -y
}

# Install required packages
install_packages() {
    log_step "Installing required packages..."
    
    # System packages
    PACKAGES=(
        python3-pip
        python3-venv
        python3-dev
        libffi-dev
        libssl-dev
        git
    )
    
    sudo apt-get install -y "${PACKAGES[@]}"
    
    log_info "System packages installed"
}

# Install Python packages
install_python_packages() {
    log_step "Installing Python packages..."
    
    # Upgrade pip
    python3 -m pip install --upgrade pip
    
    # Install MAVSDK
    if [ -n "$MAVSDK_VERSION" ]; then
        log_info "Installing MAVSDK version $MAVSDK_VERSION..."
        python3 -m pip install "mavsdk==$MAVSDK_VERSION"
    else
        log_info "Installing latest MAVSDK..."
        python3 -m pip install mavsdk
    fi
    
    # Install pyserial (for serial port utilities)
    python3 -m pip install pyserial
    
    # Verify installation
    log_info "Verifying MAVSDK installation..."
    if python3 -c "import mavsdk; print(f'MAVSDK version: {mavsdk.__version__}')" 2>/dev/null; then
        log_info "MAVSDK installed successfully"
    else
        log_error "MAVSDK installation failed"
        exit 1
    fi
}

# Configure serial port permissions
configure_permissions() {
    log_step "Configuring serial port permissions..."
    
    # Add user to dialout group
    if groups "$USER" | grep -q dialout; then
        log_info "User already in dialout group"
    else
        log_info "Adding user to dialout group..."
        sudo usermod -aG dialout "$USER"
        log_warn "You need to log out and back in for group changes to take effect"
    fi
}

# Configure UART
configure_uart() {
    if [ "$SKIP_UART" = true ]; then
        log_info "Skipping UART configuration (--skip-uart)"
        return
    fi
    
    log_step "Configuring UART..."
    
    # Check if running on Raspberry Pi with raspi-config
    if ! command -v raspi-config &> /dev/null; then
        log_warn "raspi-config not found - skipping UART configuration"
        log_warn "Please configure UART manually if needed"
        return
    fi
    
    # Enable UART in config.txt
    CONFIG_FILE="/boot/config.txt"
    if [ -f "/boot/firmware/config.txt" ]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    fi
    
    log_info "Configuring $CONFIG_FILE..."
    
    # Enable UART
    if grep -q "^enable_uart=1" "$CONFIG_FILE"; then
        log_info "UART already enabled"
    else
        log_info "Enabling UART..."
        echo "enable_uart=1" | sudo tee -a "$CONFIG_FILE" > /dev/null
    fi
    
    # Disable Bluetooth to free up primary UART (Pi 3/4)
    # This makes /dev/ttyAMA0 available for our use
    if grep -q "^dtoverlay=disable-bt" "$CONFIG_FILE" || grep -q "^dtoverlay=miniuart-bt" "$CONFIG_FILE"; then
        log_info "Bluetooth UART overlay already configured"
    else
        log_info "Configuring Bluetooth to use mini-UART (freeing /dev/ttyAMA0)..."
        echo "dtoverlay=miniuart-bt" | sudo tee -a "$CONFIG_FILE" > /dev/null
    fi
    
    # Disable serial console
    log_info "Disabling serial console (to free UART for MAVLink)..."
    sudo raspi-config nonint do_serial 1  # Disable shell over serial
    
    # Check cmdline.txt
    CMDLINE_FILE="/boot/cmdline.txt"
    if [ -f "/boot/firmware/cmdline.txt" ]; then
        CMDLINE_FILE="/boot/firmware/cmdline.txt"
    fi
    
    if grep -q "console=serial0" "$CMDLINE_FILE" || grep -q "console=ttyAMA0" "$CMDLINE_FILE"; then
        log_info "Removing serial console from cmdline.txt..."
        sudo sed -i 's/console=serial0,[0-9]* //g' "$CMDLINE_FILE"
        sudo sed -i 's/console=ttyAMA0,[0-9]* //g' "$CMDLINE_FILE"
    fi
    
    log_info "UART configuration complete"
    log_warn "A reboot is required for UART changes to take effect"
}

# Create test script
create_test_script() {
    log_step "Creating test scripts..."
    
    # Create directory if it doesn't exist
    mkdir -p ~/mavlink_test
    
    # Create a simple test script
    cat > ~/mavlink_test/test_connection.py << 'EOF'
#!/usr/bin/env python3
"""
test_connection.py - Simple MAVLink connection test

Tests connection to autopilot via UART or WiFi and displays basic telemetry.

Usage:
    # WiFi mode
    python3 test_connection.py --wifi-host 192.168.1.100

    # UART mode
    python3 test_connection.py --uart
"""

import argparse
import asyncio
import sys


async def test_connection(connection_string: str, timeout: float = 30.0):
    """Test MAVLink connection and display basic info."""
    try:
        from mavsdk import System
    except ImportError:
        print("ERROR: MAVSDK not installed. Run: pip install mavsdk")
        return False

    print(f"Connecting to: {connection_string}")
    print("Waiting for connection...")

    drone = System()

    try:
        await drone.connect(system_address=connection_string)

        # Wait for connection with timeout
        connected = False
        for _ in range(int(timeout * 2)):
            async for state in drone.core.connection_state():
                if state.is_connected:
                    connected = True
                    break
                break
            if connected:
                break
            await asyncio.sleep(0.5)

        if not connected:
            print(f"ERROR: Connection timeout after {timeout}s")
            return False

        print("\n" + "=" * 50)
        print("CONNECTION SUCCESSFUL!")
        print("=" * 50)

        # Get telemetry
        print("\nTelemetry:")

        # Armed status
        async for armed in drone.telemetry.armed():
            print(f"  Armed: {armed}")
            break

        # In air status
        async for in_air in drone.telemetry.in_air():
            print(f"  In Air: {in_air}")
            break

        # Position
        async for position in drone.telemetry.position():
            print(f"  Position: {position.latitude_deg:.6f}, {position.longitude_deg:.6f}")
            print(f"  Altitude: {position.relative_altitude_m:.1f}m")
            break

        # Battery
        async for battery in drone.telemetry.battery():
            print(f"  Battery: {battery.remaining_percent * 100:.0f}% ({battery.voltage_v:.1f}V)")
            break

        # Flight mode
        async for mode in drone.telemetry.flight_mode():
            print(f"  Flight Mode: {mode}")
            break

        print("\n" + "=" * 50)
        print("Test completed successfully!")
        print("=" * 50)

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test MAVLink connection")

    parser.add_argument(
        "--uart",
        action="store_true",
        help="Use UART connection (default: /dev/ttyAMA0:57600)"
    )
    parser.add_argument(
        "--uart-device",
        default="/dev/ttyAMA0",
        help="UART device (default: /dev/ttyAMA0)"
    )
    parser.add_argument(
        "--uart-baud",
        type=int,
        default=57600,
        help="UART baud rate (default: 57600)"
    )
    parser.add_argument(
        "--wifi-host",
        default="localhost",
        help="WiFi host IP (default: localhost)"
    )
    parser.add_argument(
        "--wifi-port",
        type=int,
        default=14540,
        help="WiFi UDP port (default: 14540)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Connection timeout in seconds (default: 30)"
    )

    args = parser.parse_args()

    # Build connection string
    if args.uart:
        connection_string = f"serial://{args.uart_device}:{args.uart_baud}"
    else:
        connection_string = f"udp://{args.wifi_host}:{args.wifi_port}"

    # Run test
    success = asyncio.get_event_loop().run_until_complete(
        test_connection(connection_string, args.timeout)
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
EOF
    
    chmod +x ~/mavlink_test/test_connection.py
    
    log_info "Test script created at ~/mavlink_test/test_connection.py"
}

# Print summary
print_summary() {
    log_step "Setup Complete!"
    
    echo ""
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}  Raspberry Pi MAVLink Setup Complete ${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo ""
    echo "Installed software:"
    echo "  - Python 3 with pip"
    echo "  - MAVSDK-Python"
    echo "  - pyserial"
    echo ""
    
    if [ "$SKIP_UART" = false ]; then
        echo "UART Configuration:"
        echo "  - UART enabled on GPIO 14/15"
        echo "  - Serial console disabled"
        echo "  - Device: /dev/ttyAMA0 or /dev/serial0"
        echo "  - Baud rate: $UART_BAUD"
        echo ""
    fi
    
    echo "Hardware Connection (UART to Cube+ Orange TELEM2):"
    echo ""
    echo "  Cube+ Orange TELEM2      Raspberry Pi GPIO"
    echo "  ─────────────────────────────────────────────"
    echo "  TX  ─────────────────────  RX (GPIO 15, Pin 10)"
    echo "  RX  ─────────────────────  TX (GPIO 14, Pin 8)"
    echo "  GND ─────────────────────  GND (Pin 6, 9, 14, 20, 25, 30, 34, 39)"
    echo ""
    echo "Test scripts:"
    echo "  ~/mavlink_test/test_connection.py"
    echo ""
    echo "Example usage:"
    echo ""
    echo "  # Test WiFi connection to SITL"
    echo "  python3 ~/mavlink_test/test_connection.py --wifi-host <SITL_IP>"
    echo ""
    echo "  # Test UART connection to Cube+ Orange"
    echo "  python3 ~/mavlink_test/test_connection.py --uart"
    echo ""
    
    if [ "$SKIP_UART" = false ]; then
        echo -e "${YELLOW}IMPORTANT: A reboot is required for UART changes to take effect.${NC}"
        echo ""
    fi
}

# Prompt for reboot
prompt_reboot() {
    if [ "$SKIP_UART" = true ] || [ "$SKIP_REBOOT" = true ]; then
        return
    fi
    
    read -p "Reboot now? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rebooting..."
        sudo reboot
    else
        log_warn "Remember to reboot for UART changes to take effect"
    fi
}

# Main function
main() {
    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}  Raspberry Pi MAVLink Setup Script  ${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
    
    check_raspberry_pi
    check_python
    update_system
    install_packages
    install_python_packages
    configure_permissions
    configure_uart
    create_test_script
    print_summary
    prompt_reboot
}

# Run main
main

