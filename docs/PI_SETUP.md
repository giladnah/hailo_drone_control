# Raspberry Pi MAVLink Connection Guide

Complete guide for connecting a Raspberry Pi to PX4 autopilots (Cube+ Orange) via UART, TCP, or WiFi.

## Table of Contents

- [Overview](#overview)
- [Connection Types Explained](#connection-types-explained)
- [Hardware Requirements](#hardware-requirements)
- [Hardware Connection (UART)](#hardware-connection-uart)
- [Software Installation](#software-installation)
- [UART Configuration](#uart-configuration)
- [Network Configuration (TCP/WiFi)](#network-configuration-tcpwifi)
- [Testing the Connection](#testing-the-connection)
- [Running Example Scripts](#running-example-scripts)
- [Troubleshooting](#troubleshooting)

## Overview

This guide covers three connection methods:

| Method | Use Case | Connection String |
|--------|----------|-------------------|
| **UART** | Production - Direct serial to Cube+ Orange TELEM2 | `serial:///dev/ttyAMA0:57600` |
| **TCP** | Testing - Reliable network connection to SITL (recommended) | `tcp://192.168.1.100:5760` |
| **WiFi (UDP)** | Testing - Low-latency UDP connection to SITL | `udp://192.168.1.100:14540` |

All methods use the same Python code - only the connection string changes.

## Connection Types Explained

### TCP vs WiFi (UDP) - When to Use Each

| Aspect | TCP (Recommended for Pi) | WiFi (UDP) |
|--------|--------------------------|------------|
| **Protocol** | TCP - Connection-oriented | UDP - Connectionless |
| **Reliability** | Guaranteed delivery, ordered packets | May lose packets, no ordering |
| **Connection** | Pi connects TO SITL server | SITL pushes TO Pi's IP |
| **NAT/Firewall** | Works easily (client initiates) | Harder (needs bidirectional) |
| **Setup** | Just need SITL host IP | Need to configure SITL to push to Pi |
| **Latency** | Slightly higher | Lower |
| **Best For** | Remote connections, reliability | Same-network, real-time control |

**Recommendation**: Use **TCP** for Raspberry Pi connections because:
1. **Simpler setup** - Pi connects to SITL, no need to configure SITL with Pi's IP
2. **Works through routers** - NAT/firewall friendly
3. **Reliable** - Guaranteed packet delivery
4. **No packet loss** - Important for command/control

Use **UDP (WiFi)** when:
- You need absolute minimum latency
- Pi and SITL are on the same local network
- You've configured SITL to push to Pi's specific IP

### UART - Production Connection

UART (serial) is used for the actual drone deployment:
- Direct wired connection to Cube+ Orange TELEM2 port
- No network required
- Most reliable for flight operations
- Same code works for both testing (TCP/UDP) and production (UART)

## Hardware Requirements

### For UART Connection (Production)

- Raspberry Pi 3B+, 4, or 5
- Cube+ Orange flight controller
- Jumper wires (female-to-female or appropriate connectors)
- TELEM2 cable or JST-GH connector

### For WiFi Connection (Testing)

- Raspberry Pi with WiFi capability
- Host computer running PX4 SITL
- Same WiFi network for both devices

## Hardware Connection (UART)

### TELEM2 Pinout (Cube+ Orange)

The TELEM2 port uses a JST-GH 6-pin connector:

| Pin | Signal | Description |
|-----|--------|-------------|
| 1 | VCC | +5V (usually not used) |
| 2 | TX | Transmit (Cube → Pi) |
| 3 | RX | Receive (Pi → Cube) |
| 4 | CTS | Clear to Send (not used) |
| 5 | RTS | Request to Send (not used) |
| 6 | GND | Ground |

### Raspberry Pi GPIO Pinout

| GPIO | Physical Pin | Function |
|------|--------------|----------|
| GPIO 14 (TXD) | Pin 8 | UART Transmit |
| GPIO 15 (RXD) | Pin 10 | UART Receive |
| GND | Pins 6, 9, 14, 20, 25, 30, 34, 39 | Ground |

### Wiring Diagram

```
Cube+ Orange TELEM2              Raspberry Pi GPIO
┌─────────────────┐              ┌─────────────────┐
│                 │              │                 │
│  TX (Pin 2) ────┼──────────────┼──► RX (GPIO 15) │
│                 │              │     Pin 10      │
│  RX (Pin 3) ◄───┼──────────────┼──── TX (GPIO 14)│
│                 │              │     Pin 8       │
│  GND (Pin 6) ───┼──────────────┼──── GND         │
│                 │              │     Pin 6       │
└─────────────────┘              └─────────────────┘

Note: TX → RX (crossed connection)
```

### Important Notes

1. **Do NOT connect VCC** - The Pi and Cube have different power requirements
2. **Cross TX/RX** - TX from one device connects to RX on the other
3. **Common ground** - Both devices must share a common ground
4. **Voltage levels** - Both use 3.3V logic, so no level shifter needed

## Software Installation

### Automated Setup

Run the setup script on your Raspberry Pi:

```bash
# Download and run setup script
curl -sSL https://raw.githubusercontent.com/<repo>/main/scripts/setup_pi.sh | bash

# Or clone the repository and run locally
git clone <repository-url>
cd hailo_drone_control
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```

### Manual Installation

If you prefer manual installation:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python and dependencies
sudo apt-get install -y python3 python3-pip python3-venv python3-dev

# Install MAVSDK
pip3 install mavsdk pyserial

# Add user to dialout group (for serial port access)
sudo usermod -aG dialout $USER

# Log out and back in for group changes to take effect
```

## UART Configuration

### Enable UART on Raspberry Pi

The UART must be enabled and the serial console disabled.

#### Using raspi-config (Recommended)

```bash
sudo raspi-config
```

1. Select **Interface Options**
2. Select **Serial Port**
3. "Would you like a login shell to be accessible over serial?" → **No**
4. "Would you like the serial port hardware to be enabled?" → **Yes**
5. Finish and reboot

#### Manual Configuration

Edit `/boot/config.txt` (or `/boot/firmware/config.txt` on newer Pi OS):

```bash
sudo nano /boot/config.txt
```

Add these lines:

```
# Enable UART
enable_uart=1

# Use mini-UART for Bluetooth (frees /dev/ttyAMA0)
dtoverlay=miniuart-bt
```

Remove serial console from `/boot/cmdline.txt`:

```bash
sudo nano /boot/cmdline.txt
```

Remove `console=serial0,115200` or `console=ttyAMA0,115200` if present.

Reboot:

```bash
sudo reboot
```

### Verify UART Configuration

After reboot, check that the UART device exists:

```bash
# List serial devices
ls -la /dev/ttyAMA0 /dev/serial0

# Check permissions
groups $USER  # Should include 'dialout'

# Test serial port (should not show errors)
python3 -c "import serial; s = serial.Serial('/dev/ttyAMA0', 57600); print('OK'); s.close()"
```

## Network Configuration (TCP/WiFi)

### Host Machine Setup (SITL)

On the host machine running SITL, the following ports are exposed by default:

| Port | Protocol | Purpose |
|------|----------|---------|
| 5760 | TCP | MAVLink TCP server (recommended for Pi) |
| 14540 | UDP | MAVLink UDP for MAVSDK |
| 14551 | UDP | MAVLink UDP for QGC |

These are configured in `docker-compose.yml`:

```yaml
px4-sitl:
  ports:
    - "5760:5760/tcp"      # TCP server (recommended)
    - "14540:14540/udp"    # UDP for MAVSDK
    - "14551:14550/udp"    # UDP for QGC
```

**Find your host IP address:**

```bash
# On Linux
ip addr show | grep "inet " | grep -v 127.0.0.1

# Or simply
hostname -I
```

**Verify firewall allows connections:**

```bash
# For TCP (recommended)
sudo ufw allow 5760/tcp

# For UDP (if using WiFi mode)
sudo ufw allow 14540/udp
```

### Raspberry Pi Network Setup

1. **Connect to WiFi:**

   ```bash
   # Check WiFi connection
   iwconfig wlan0

   # Get Pi's IP address
   ip addr show wlan0
   ```

2. **Test network connectivity:**

   ```bash
   # Ping host machine
   ping 192.168.1.100  # Replace with your host IP

   # Test TCP port is reachable
   nc -zv 192.168.1.100 5760
   ```

### Choosing TCP vs UDP

**Use TCP (recommended):**
```bash
python3 examples/pi_connection_test.py -c tcp --tcp-host 192.168.1.100
```

**Use UDP (WiFi) only if:**
- You need minimum latency
- You're on the same local network
- TCP has issues in your environment

```bash
python3 examples/pi_connection_test.py -c wifi --wifi-host 192.168.1.100
```

## Testing the Connection

### Test Script

Use the test scripts to verify connectivity:

```bash
# TCP connection test (recommended)
python3 examples/pi_connection_test.py -c tcp --tcp-host 192.168.1.100

# WiFi (UDP) connection test
python3 examples/pi_connection_test.py -c wifi --wifi-host 192.168.1.100

# UART connection test
python3 examples/pi_connection_test.py -c uart

# Full diagnostic mode
python3 examples/pi_connection_test.py -c tcp --tcp-host 192.168.1.100 --full-diagnostic
```

Or use the simple test script installed by `setup_pi.sh`:

```bash
# TCP connection
python3 ~/mavlink_test/test_connection.py --tcp-host 192.168.1.100

# UART connection
python3 ~/mavlink_test/test_connection.py --uart
```

### Expected Output

Successful TCP connection:

```
==================================================
MAVLink Connection Configuration
==================================================
  Type: TCP
  Host: 192.168.1.100
  Port: 5760

  Connection String: tcp://192.168.1.100:5760
==================================================

Connecting to: tcp://192.168.1.100:5760
Timeout: 30.0s
--------------------------------------------------
Waiting for heartbeat...
  Heartbeat received after 0.8s

Gathering telemetry...
  Armed: False
  In Air: False
  Position: 47.397743, 8.545595
  Altitude: 0.1m (relative)
  Battery: 100% (16.2V)
  Flight Mode: HOLD
  GPS: 10 satellites, FIX_3D

==================================================
  CONNECTION TEST: PASSED
==================================================
```

### Using mavlink_connection.py Utility

You can also use the connection helper utility:

```bash
cd hailo_drone_control

# Detect serial ports
python3 scripts/mavlink_connection.py --detect-ports

# Validate UART configuration
python3 scripts/mavlink_connection.py -c uart --validate

# Validate WiFi configuration
python3 scripts/mavlink_connection.py -c wifi --wifi-host 192.168.1.100 --validate
```

## Running Example Scripts

### Copy Scripts to Pi

```bash
# Clone repository on Pi
git clone <repository-url>
cd hailo_drone_control
```

### Run Examples

```bash
# WiFi mode (testing with SITL)
python3 examples/simple_takeoff_land.py -c wifi --wifi-host 192.168.1.100 --altitude 5

# UART mode (production with Cube+ Orange)
python3 examples/simple_takeoff_land.py -c uart --altitude 5

# Hover and rotate
python3 examples/hover_rotate.py -c uart --altitude 10 --rotation 360

# Mission upload
python3 examples/mission_upload.py -c wifi --wifi-host 192.168.1.100 --altitude 20
```

### Environment Variables

Instead of command-line arguments, you can use environment variables:

```bash
# For WiFi
export PI_CONNECTION_TYPE=wifi
export PI_WIFI_HOST=192.168.1.100
export PI_WIFI_PORT=14540

# For UART
export PI_CONNECTION_TYPE=uart
export PI_UART_DEVICE=/dev/ttyAMA0
export PI_UART_BAUD=57600

# Then run without arguments
python3 examples/simple_takeoff_land.py --altitude 5
```

## Troubleshooting

### UART Issues

#### Device Not Found

```
Error: Serial device /dev/ttyAMA0 not found
```

**Solutions:**
1. Verify UART is enabled: `ls -la /dev/ttyAMA0`
2. Check if serial console is disabled: `cat /boot/cmdline.txt`
3. Reboot after configuration changes

#### Permission Denied

```
Error: Permission denied: /dev/ttyAMA0
```

**Solutions:**
1. Add user to dialout group: `sudo usermod -aG dialout $USER`
2. Log out and back in
3. Or run with sudo (not recommended): `sudo python3 ...`

#### No Heartbeat Received

```
Error: Connection timeout - no heartbeat received
```

**Solutions:**
1. Check wiring (TX→RX, RX→TX, GND→GND)
2. Verify baud rate matches (57600 for TELEM2)
3. Check Cube+ Orange is powered and running
4. Verify TELEM2 is enabled in QGroundControl parameters

### WiFi Issues

#### Cannot Connect to Host

```
Error: Connection refused
```

**Solutions:**
1. Verify SITL is running: `docker ps`
2. Check port is exposed: `netstat -uln | grep 14540`
3. Verify firewall allows UDP 14540
4. Ping host machine from Pi

#### Network Unreachable

**Solutions:**
1. Check WiFi connection: `iwconfig wlan0`
2. Verify same network: Compare IP subnets
3. Check router settings (AP isolation)

### MAVSDK Issues

#### Import Error

```
ModuleNotFoundError: No module named 'mavsdk'
```

**Solution:**
```bash
pip3 install mavsdk
```

#### Connection String Error

```
Error: Invalid connection string
```

**Valid formats:**
- UART: `serial:///dev/ttyAMA0:57600`
- WiFi: `udp://192.168.1.100:14540`

### Debug Mode

Enable verbose output for debugging:

```bash
# Using test script
python3 ~/mavlink_test/test_connection.py --uart --timeout 60

# Using example scripts
python3 examples/simple_takeoff_land.py -c uart -v
```

## Cube+ Orange TELEM2 Configuration

### PX4 Parameters

Ensure these parameters are set in QGroundControl:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAV_1_CONFIG` | TELEM2 | MAVLink on TELEM2 |
| `MAV_1_MODE` | Normal | Standard MAVLink mode |
| `SER_TEL2_BAUD` | 57600 | Baud rate (must match Pi) |

### To Change Parameters:

1. Connect to Cube+ Orange with QGroundControl
2. Go to Vehicle Setup → Parameters
3. Search for and set each parameter
4. Reboot the flight controller

## Quick Reference

### Connection Strings

| Mode | Connection String | When to Use |
|------|-------------------|-------------|
| **TCP (recommended)** | `tcp://192.168.1.100:5760` | Remote connections, reliability needed |
| **WiFi (UDP)** | `udp://192.168.1.100:14540` | Same network, low latency needed |
| **UART** | `serial:///dev/ttyAMA0:57600` | Production with Cube+ Orange |

### Command Line Examples

```bash
# TCP connection (recommended for Pi)
python3 examples/simple_takeoff_land.py -c tcp --tcp-host 192.168.1.100

# WiFi (UDP) connection
python3 examples/simple_takeoff_land.py -c wifi --wifi-host 192.168.1.100

# UART connection (production)
python3 examples/simple_takeoff_land.py -c uart
```

### Common Commands

```bash
# Check serial ports
ls -la /dev/tty*

# Check user groups
groups $USER

# Test serial port
python3 -c "import serial; print(serial.Serial('/dev/ttyAMA0', 57600))"

# Check network
ip addr show
ping <host_ip>

# Run with verbose output
python3 scripts/mavlink_connection.py --detect-ports --validate
```

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [README.md](../README.md) - Project overview
- [PX4 Documentation](https://docs.px4.io/)
- [MAVSDK Python Guide](https://mavsdk.mavlink.io/main/en/python/)
- [ArduPilot RPi via MAVLink](https://ardupilot.org/dev/docs/raspberry-pi-via-mavlink.html)

