# PX4 Development Environment for Cube+ Orange
# Base: Ubuntu 22.04 (Jammy) with Gazebo Garden and Intel GPU support

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Set locale
RUN apt-get update && apt-get install -y locales \
    && locale-gen en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# Install base dependencies
RUN apt-get update && apt-get install -y \
    # Build essentials
    build-essential \
    cmake \
    git \
    wget \
    curl \
    ninja-build \
    pkg-config \
    # Python
    python3 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    # Serial and USB
    libusb-1.0-0-dev \
    libudev-dev \
    # Networking
    net-tools \
    iproute2 \
    iputils-ping \
    # X11 forwarding for Gazebo GUI
    libx11-dev \
    libxext-dev \
    libxrender-dev \
    libxrandr-dev \
    x11-apps \
    mesa-utils \
    # Intel GPU support (Mesa drivers)
    libgl1-mesa-dev \
    libgl1-mesa-dri \
    libglx-mesa0 \
    libegl-mesa0 \
    libegl1-mesa-dev \
    libglu1-mesa-dev \
    # System utilities
    lsb-release \
    gnupg2 \
    software-properties-common \
    # Miscellaneous
    sudo \
    vim \
    nano \
    htop \
    tmux \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install ARM GCC cross-compiler for Cube+ Orange firmware builds
RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    libnewlib-arm-none-eabi \
    && rm -rf /var/lib/apt/lists/*

# Add Gazebo Garden repository
RUN wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null

# Install Gazebo Garden
RUN apt-get update && apt-get install -y \
    gz-garden \
    && rm -rf /var/lib/apt/lists/*

# Install PX4 Python dependencies
# Note: empy==3.3.4 is specifically required - newer versions break PX4 code generation
RUN pip3 install --no-cache-dir \
    empy==3.3.4 \
    pyros-genmsg \
    packaging \
    toml \
    numpy \
    pyyaml \
    jinja2 \
    pyserial \
    cerberus \
    pillow \
    jsonschema \
    kconfiglib \
    future \
    pymavlink

# Install MAVSDK-Python for MAVLink communication
RUN pip3 install --no-cache-dir mavsdk

# Install meson for mavlink-router build
RUN pip3 install --no-cache-dir meson

# Build and install MAVLink-Router from source
WORKDIR /tmp
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    libtool \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/mavlink-router/mavlink-router.git \
    && cd mavlink-router \
    && git submodule update --init --recursive \
    && meson setup build . \
    && ninja -C build \
    && ninja -C build install \
    && cd / \
    && rm -rf /tmp/mavlink-router

# Create non-root user for development
ARG USERNAME=px4dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Add user to dialout group for serial port access
RUN usermod -aG dialout $USERNAME

# Set up working directory
WORKDIR /workspace

# Create directories for PX4 source and configuration
RUN mkdir -p /workspace/PX4-Autopilot \
    && mkdir -p /workspace/config \
    && mkdir -p /workspace/logs \
    && chown -R $USERNAME:$USERNAME /workspace

# Environment variables for PX4
ENV PX4_HOME=/workspace/PX4-Autopilot
ENV PATH="${PX4_HOME}/Tools:${PATH}"

# Gazebo environment variables
ENV GZ_SIM_RESOURCE_PATH=/workspace/PX4-Autopilot/Tools/simulation/gz/models:/workspace/PX4-Autopilot/Tools/simulation/gz/worlds
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/workspace/PX4-Autopilot/build/px4_sitl_default/build_gazebo-classic

# Intel GPU / Mesa environment variables
ENV LIBGL_ALWAYS_SOFTWARE=0
ENV MESA_GL_VERSION_OVERRIDE=3.3

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER $USERNAME

# Set the entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]

