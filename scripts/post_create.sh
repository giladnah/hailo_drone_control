#!/bin/bash
# Post-create script for PX4 development container
# This script runs after the container is created to set up the development environment
#
# Features:
# - Clones PX4-Autopilot if not present
# - Initializes git submodules
# - Sets up PX4 build environment
# - Configures shell environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Configuration
PX4_DIR="${PX4_HOME:-/workspace/PX4-Autopilot}"
PX4_REPO="https://github.com/PX4/PX4-Autopilot.git"
PX4_BRANCH="${PX4_BRANCH:-main}"

echo ""
echo "=========================================="
echo "  PX4 Development Environment Setup"
echo "=========================================="
echo ""

# Step 1: Clone PX4-Autopilot if not present
log_step "Step 1: Checking PX4 source code..."

if [ ! -f "$PX4_DIR/Makefile" ]; then
    log_info "PX4-Autopilot not found, cloning repository..."

    # Remove empty directory if it exists
    if [ -d "$PX4_DIR" ]; then
        rm -rf "$PX4_DIR"
    fi

    git clone --recursive --branch "$PX4_BRANCH" "$PX4_REPO" "$PX4_DIR"
    log_info "PX4-Autopilot cloned successfully"
else
    log_info "PX4-Autopilot already present at $PX4_DIR"

    # Update submodules if needed
    log_info "Updating git submodules..."
    cd "$PX4_DIR"
    git submodule update --init --recursive
fi

# Step 2: Install PX4 dependencies
log_step "Step 2: Installing PX4 dependencies..."

cd "$PX4_DIR"

# Run PX4 setup script if available
if [ -f "Tools/setup/ubuntu.sh" ]; then
    log_info "Running PX4 Ubuntu setup script..."
    # Run in non-interactive mode, skip prompts
    yes | bash Tools/setup/ubuntu.sh --no-sim-tools 2>/dev/null || true
else
    log_warn "PX4 setup script not found, skipping..."
fi

# Step 3: Set up Gazebo models path
log_step "Step 3: Configuring Gazebo environment..."

# Add Gazebo model paths to bashrc
BASHRC_FILE="$HOME/.bashrc"

if ! grep -q "PX4_GZ_MODELS" "$BASHRC_FILE" 2>/dev/null; then
    log_info "Adding Gazebo paths to .bashrc..."

    cat >> "$BASHRC_FILE" << 'EOF'

# PX4 Gazebo Environment
export GZ_SIM_RESOURCE_PATH="$PX4_HOME/Tools/simulation/gz/models:$PX4_HOME/Tools/simulation/gz/worlds:$GZ_SIM_RESOURCE_PATH"
export PX4_GZ_MODELS="$PX4_HOME/Tools/simulation/gz/models"
export PX4_GZ_WORLDS="$PX4_HOME/Tools/simulation/gz/worlds"
EOF
fi

# Step 4: Create helpful aliases
log_step "Step 4: Setting up shell aliases..."

if ! grep -q "# PX4 Aliases" "$BASHRC_FILE" 2>/dev/null; then
    log_info "Adding PX4 aliases to .bashrc..."

    cat >> "$BASHRC_FILE" << 'EOF'

# PX4 Aliases
alias px4-build="cd $PX4_HOME && make px4_sitl_default"
alias px4-sitl="cd $PX4_HOME && make px4_sitl gz_x500"
alias px4-cube="cd $PX4_HOME && make px4_fmu-v6x_default"
alias px4-clean="cd $PX4_HOME && make clean"
alias px4-distclean="cd $PX4_HOME && make distclean"

# Quick navigation
alias cdpx4="cd $PX4_HOME"
alias cdws="cd /workspace"

# Gazebo shortcuts
alias gz-kill="pkill -f gz"
alias px4-kill="pkill -f px4"
EOF
fi

# Step 5: Pre-build check
log_step "Step 5: Verifying build environment..."

cd "$PX4_DIR"

# Check if ARM GCC is available
if command -v arm-none-eabi-gcc &> /dev/null; then
    ARM_GCC_VERSION=$(arm-none-eabi-gcc --version | head -n1)
    log_info "ARM GCC: $ARM_GCC_VERSION"
else
    log_warn "ARM GCC not found - firmware builds may not work"
fi

# Check if required Python packages are available
log_info "Checking Python dependencies..."
python3 -c "import empy; print(f'empy version: {empy.__version__}')" 2>/dev/null || log_warn "empy not found"
python3 -c "import jinja2; print(f'jinja2 version: {jinja2.__version__}')" 2>/dev/null || log_warn "jinja2 not found"

# Step 6: Build SITL (optional, can be skipped for faster setup)
log_step "Step 6: Building PX4 SITL (this may take a while)..."

if [ "${SKIP_BUILD:-false}" = "true" ]; then
    log_warn "Skipping initial build (SKIP_BUILD=true)"
else
    log_info "Building PX4 SITL target..."
    cd "$PX4_DIR"
    make px4_sitl_default 2>&1 || {
        log_warn "Initial build failed - this is sometimes expected on first run"
        log_info "Try running 'make px4_sitl_default' manually after setup completes"
    }
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Quick Start Commands:"
echo "  px4-sitl      - Run SITL with Gazebo x500"
echo "  px4-cube      - Build firmware for Cube+ Orange"
echo "  px4-clean     - Clean build artifacts"
echo ""
echo "Useful Paths:"
echo "  PX4 Source:   $PX4_DIR"
echo "  Config:       /workspace/config"
echo "  Logs:         /workspace/logs"
echo ""
echo "To start SITL simulation manually:"
echo "  cd $PX4_DIR"
echo "  make px4_sitl gz_x500"
echo ""

