#!/usr/bin/env python3
"""
mavlink_connection.py - MAVLink Connection Helper Utility

Provides a unified interface for connecting to MAVLink via TCP, UDP, or UART.
Supports both production (UART to TELEM2) and testing (TCP/UDP to SITL) modes.

Connection Types:
    - tcp: TCP connection (DEFAULT - recommended for most use cases)
    - udp: UDP connection (advanced - lower latency, requires network config)
    - uart: Serial connection (production - Cube+ Orange TELEM2)

TCP vs UDP:
    TCP is the default and recommended for most connections because:
    - Reliable: Guaranteed packet delivery (no lost commands)
    - NAT-friendly: Client connects TO server, works through routers
    - Simple: No need to configure SITL with client's IP address

    UDP may be preferred when:
    - Minimum latency is critical (no TCP handshake overhead)
    - Direct network connection (same subnet, no NAT)
    - Specific MAVLink router configurations require it

Usage:
    from scripts.mavlink_connection import get_connection_string, ConnectionConfig

    # TCP mode (default - recommended for SITL and remote connections)
    conn_str = get_connection_string("tcp", host="192.168.1.100", port=5760)

    # UDP mode (advanced - low latency, requires proper network setup)
    conn_str = get_connection_string("udp", host="0.0.0.0", port=14540)

    # UART mode (production - Cube+ Orange TELEM2)
    conn_str = get_connection_string("uart", device="/dev/ttyAMA0", baud=57600)

    # Using config object
    config = ConnectionConfig.from_env()
    conn_str = config.get_connection_string()

Environment Variables:
    PI_CONNECTION_TYPE  - Connection type: "tcp", "udp", or "uart" (default: tcp)
    PI_TCP_HOST         - TCP host IP (default: localhost)
    PI_TCP_PORT         - TCP port (default: 5760)
    PI_UDP_HOST         - UDP listen address (default: 0.0.0.0)
    PI_UDP_PORT         - UDP port (default: 14540)
    PI_UART_DEVICE      - Serial device path (default: /dev/ttyAMA0)
    PI_UART_BAUD        - Serial baud rate (default: 57600)
"""

import argparse
import glob
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ConnectionType(Enum):
    """MAVLink connection types."""
    UART = "uart"
    UDP = "udp"
    TCP = "tcp"


# Default configuration values
DEFAULTS = {
    "connection_type": "tcp",  # TCP is default - most reliable for SITL
    "uart_device": "/dev/ttyAMA0",
    "uart_baud": 57600,  # Standard for TELEM2
    "udp_host": "0.0.0.0",  # Listen on all interfaces
    "udp_port": 14540,
    "tcp_host": "localhost",
    "tcp_port": 5760,
}

# Common serial port patterns on Raspberry Pi
PI_SERIAL_PATTERNS = [
    "/dev/ttyAMA0",     # Primary UART (Pi 3+/4)
    "/dev/serial0",     # Symlink to primary UART
    "/dev/ttyS0",       # Mini UART
    "/dev/ttyUSB*",     # USB-to-serial adapters
    "/dev/ttyACM*",     # USB CDC ACM devices
]


@dataclass
class ConnectionConfig:
    """
    MAVLink connection configuration.

    Attributes:
        connection_type: Type of connection (uart, udp, or tcp).
        uart_device: Serial device path for UART mode.
        uart_baud: Baud rate for UART mode.
        udp_host: Listen address for UDP mode (use 0.0.0.0 for all interfaces).
        udp_port: UDP port for UDP mode.
        tcp_host: Host IP/hostname for TCP mode.
        tcp_port: TCP port for TCP mode.
    """
    connection_type: ConnectionType
    uart_device: str = DEFAULTS["uart_device"]
    uart_baud: int = DEFAULTS["uart_baud"]
    udp_host: str = DEFAULTS["udp_host"]
    udp_port: int = DEFAULTS["udp_port"]
    tcp_host: str = DEFAULTS["tcp_host"]
    tcp_port: int = DEFAULTS["tcp_port"]

    @classmethod
    def from_env(cls) -> "ConnectionConfig":
        """
        Create configuration from environment variables.

        Returns:
            ConnectionConfig: Configuration populated from environment.
        """
        conn_type_str = os.environ.get(
            "PI_CONNECTION_TYPE",
            DEFAULTS["connection_type"]
        ).lower()

        try:
            conn_type = ConnectionType(conn_type_str)
        except ValueError:
            print(f"Warning: Unknown connection type '{conn_type_str}', using tcp")
            conn_type = ConnectionType.TCP

        return cls(
            connection_type=conn_type,
            uart_device=os.environ.get(
                "PI_UART_DEVICE",
                DEFAULTS["uart_device"]
            ),
            uart_baud=int(os.environ.get(
                "PI_UART_BAUD",
                DEFAULTS["uart_baud"]
            )),
            udp_host=os.environ.get(
                "PI_UDP_HOST",
                DEFAULTS["udp_host"]
            ),
            udp_port=int(os.environ.get(
                "PI_UDP_PORT",
                DEFAULTS["udp_port"]
            )),
            tcp_host=os.environ.get(
                "PI_TCP_HOST",
                DEFAULTS["tcp_host"]
            ),
            tcp_port=int(os.environ.get(
                "PI_TCP_PORT",
                DEFAULTS["tcp_port"]
            )),
        )

    @classmethod
    def from_args(
        cls,
        connection_type: str = None,
        uart_device: str = None,
        uart_baud: int = None,
        udp_host: str = None,
        udp_port: int = None,
        tcp_host: str = None,
        tcp_port: int = None,
    ) -> "ConnectionConfig":
        """
        Create configuration from arguments with environment fallback.

        Args:
            connection_type: Connection type string ("uart", "udp", or "tcp").
            uart_device: Serial device path.
            uart_baud: Serial baud rate.
            udp_host: UDP listen address.
            udp_port: UDP port.
            tcp_host: TCP host IP.
            tcp_port: TCP port.

        Returns:
            ConnectionConfig: Configuration with argument overrides.
        """
        # Start with environment config
        config = cls.from_env()

        # Override with provided arguments
        if connection_type is not None:
            try:
                config.connection_type = ConnectionType(connection_type.lower())
            except ValueError:
                print(f"Warning: Unknown connection type '{connection_type}'")

        if uart_device is not None:
            config.uart_device = uart_device
        if uart_baud is not None:
            config.uart_baud = uart_baud
        if udp_host is not None:
            config.udp_host = udp_host
        if udp_port is not None:
            config.udp_port = udp_port
        if tcp_host is not None:
            config.tcp_host = tcp_host
        if tcp_port is not None:
            config.tcp_port = tcp_port

        return config

    def get_connection_string(self) -> str:
        """
        Generate MAVSDK connection string based on configuration.

        Returns:
            str: MAVSDK-compatible connection string.
        """
        if self.connection_type == ConnectionType.UART:
            return f"serial://{self.uart_device}:{self.uart_baud}"
        elif self.connection_type == ConnectionType.TCP:
            return f"tcp://{self.tcp_host}:{self.tcp_port}"
        else:
            # Use udpin:// to listen for incoming UDP packets
            # (udp:// is deprecated in MAVSDK)
            return f"udpin://{self.udp_host}:{self.udp_port}"

    def __str__(self) -> str:
        """String representation showing current settings."""
        if self.connection_type == ConnectionType.UART:
            return f"UART: {self.uart_device} @ {self.uart_baud} baud"
        elif self.connection_type == ConnectionType.TCP:
            return f"TCP: {self.tcp_host}:{self.tcp_port}"
        else:
            return f"UDP: {self.udp_host}:{self.udp_port}"


def get_connection_string(
    connection_type: str = "tcp",
    device: str = None,
    baud: int = None,
    host: str = None,
    port: int = None,
) -> str:
    """
    Generate MAVSDK connection string for the specified connection type.

    This is a convenience function for simple use cases.

    Args:
        connection_type: "uart", "udp", or "tcp" (default: tcp).
        device: Serial device path for UART (default: /dev/ttyAMA0).
        baud: Baud rate for UART (default: 57600).
        host: Host IP/address for UDP/TCP (default varies by type).
        port: Port for UDP (14540) or TCP (5760).

    Returns:
        str: MAVSDK-compatible connection string.

    Examples:
        >>> get_connection_string("uart")
        'serial:///dev/ttyAMA0:57600'

        >>> get_connection_string("uart", device="/dev/ttyUSB0", baud=921600)
        'serial:///dev/ttyUSB0:921600'

        >>> get_connection_string("udp", host="0.0.0.0")
        'udpin://0.0.0.0:14540'

        >>> get_connection_string("tcp", host="192.168.1.100")
        'tcp://192.168.1.100:5760'
    """
    conn_type = connection_type.lower()

    if conn_type == "uart" or conn_type == "serial":
        device = device or DEFAULTS["uart_device"]
        baud = baud or DEFAULTS["uart_baud"]
        return f"serial://{device}:{baud}"

    elif conn_type == "udp":
        host = host or DEFAULTS["udp_host"]
        port = port or DEFAULTS["udp_port"]
        # Use udpin:// to listen for incoming packets (udp:// is deprecated)
        return f"udpin://{host}:{port}"

    elif conn_type == "tcp":
        host = host or DEFAULTS["tcp_host"]
        port = port or DEFAULTS["tcp_port"]
        return f"tcp://{host}:{port}"

    else:
        raise ValueError(
            f"Unknown connection type: {connection_type}. "
            "Use 'uart', 'udp', or 'tcp'."
        )


def detect_serial_ports() -> List[str]:
    """
    Detect available serial ports on the system.

    Returns:
        List[str]: List of available serial port paths.
    """
    ports = []

    for pattern in PI_SERIAL_PATTERNS:
        if "*" in pattern:
            # Glob pattern
            ports.extend(glob.glob(pattern))
        elif os.path.exists(pattern):
            ports.append(pattern)

    return sorted(set(ports))


def check_serial_port(device: str) -> dict:
    """
    Check if a serial port exists and is accessible.

    Args:
        device: Serial device path to check.

    Returns:
        dict: Status information about the port.
    """
    result = {
        "device": device,
        "exists": False,
        "readable": False,
        "writable": False,
        "error": None,
    }

    if not os.path.exists(device):
        result["error"] = "Device does not exist"
        return result

    result["exists"] = True

    # Check read permission
    if os.access(device, os.R_OK):
        result["readable"] = True

    # Check write permission
    if os.access(device, os.W_OK):
        result["writable"] = True

    if not result["readable"] or not result["writable"]:
        result["error"] = (
            "Permission denied. Add user to dialout group: "
            "sudo usermod -aG dialout $USER"
        )

    return result


def validate_config(config: ConnectionConfig) -> dict:
    """
    Validate connection configuration.

    Args:
        config: ConnectionConfig to validate.

    Returns:
        dict: Validation result with 'valid' bool and 'errors' list.
    """
    result = {"valid": True, "errors": [], "warnings": []}

    if config.connection_type == ConnectionType.UART:
        # Validate UART settings
        port_status = check_serial_port(config.uart_device)

        if not port_status["exists"]:
            result["valid"] = False
            result["errors"].append(
                f"Serial device not found: {config.uart_device}"
            )
        elif not port_status["readable"] or not port_status["writable"]:
            result["valid"] = False
            result["errors"].append(port_status["error"])

        # Check baud rate
        valid_bauds = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        if config.uart_baud not in valid_bauds:
            result["warnings"].append(
                f"Non-standard baud rate: {config.uart_baud}. "
                f"Common rates: {valid_bauds}"
            )

        # TELEM2 typically uses 57600
        if config.uart_baud != 57600:
            result["warnings"].append(
                f"Baud rate {config.uart_baud} differs from TELEM2 default (57600)"
            )

    elif config.connection_type == ConnectionType.TCP:
        # Validate TCP settings
        if not config.tcp_host:
            result["valid"] = False
            result["errors"].append("TCP host not specified")

        if config.tcp_port < 1 or config.tcp_port > 65535:
            result["valid"] = False
            result["errors"].append(
                f"Invalid TCP port number: {config.tcp_port}"
            )

    else:
        # Validate UDP settings
        if not config.udp_host:
            result["valid"] = False
            result["errors"].append("UDP host not specified")

        if config.udp_port < 1 or config.udp_port > 65535:
            result["valid"] = False
            result["errors"].append(
                f"Invalid UDP port number: {config.udp_port}"
            )

    return result


def add_connection_arguments(parser) -> None:
    """
    Add standard connection arguments to an argparse parser.

    Args:
        parser: argparse.ArgumentParser to add arguments to.

    Example:
        parser = argparse.ArgumentParser()
        add_connection_arguments(parser)
        args = parser.parse_args()
        config = ConnectionConfig.from_args(
            connection_type=args.connection_type,
            uart_device=args.uart_device,
            ...
        )
    """
    conn_group = parser.add_argument_group("Connection Options")

    conn_group.add_argument(
        "--connection-type", "-c",
        choices=["uart", "udp", "tcp"],
        default=None,
        help="Connection type: uart (serial), udp (advanced), or tcp (default). "
             "Default: PI_CONNECTION_TYPE env or 'tcp'"
    )

    conn_group.add_argument(
        "--uart-device",
        default=None,
        help=f"Serial device for UART mode. "
             f"Default: PI_UART_DEVICE env or '{DEFAULTS['uart_device']}'"
    )

    conn_group.add_argument(
        "--uart-baud",
        type=int,
        default=None,
        help=f"Baud rate for UART mode. "
             f"Default: PI_UART_BAUD env or {DEFAULTS['uart_baud']}"
    )

    conn_group.add_argument(
        "--udp-host",
        default=None,
        help=f"Listen address for UDP mode (use 0.0.0.0 for all interfaces). "
             f"Default: PI_UDP_HOST env or '{DEFAULTS['udp_host']}'"
    )

    conn_group.add_argument(
        "--udp-port",
        type=int,
        default=None,
        help=f"UDP port for UDP mode. "
             f"Default: PI_UDP_PORT env or {DEFAULTS['udp_port']}"
    )

    conn_group.add_argument(
        "--tcp-host",
        default=None,
        help=f"Host IP for TCP mode. "
             f"Default: PI_TCP_HOST env or '{DEFAULTS['tcp_host']}'"
    )

    conn_group.add_argument(
        "--tcp-port",
        type=int,
        default=None,
        help=f"TCP port for TCP mode. "
             f"Default: PI_TCP_PORT env or {DEFAULTS['tcp_port']}"
    )


def print_connection_info(config: ConnectionConfig) -> None:
    """
    Print connection information for debugging.

    Args:
        config: ConnectionConfig to display.
    """
    print("=" * 50)
    print("MAVLink Connection Configuration")
    print("=" * 50)
    print(f"  Type: {config.connection_type.value.upper()}")

    if config.connection_type == ConnectionType.UART:
        print(f"  Device: {config.uart_device}")
        print(f"  Baud Rate: {config.uart_baud}")

        # Check port status
        status = check_serial_port(config.uart_device)
        if status["exists"]:
            access = []
            if status["readable"]:
                access.append("read")
            if status["writable"]:
                access.append("write")
            print(f"  Port Status: OK ({', '.join(access)})")
        else:
            print(f"  Port Status: NOT FOUND")
    elif config.connection_type == ConnectionType.TCP:
        print(f"  Host: {config.tcp_host}")
        print(f"  Port: {config.tcp_port}")
    else:
        print(f"  Listen Address: {config.udp_host}")
        print(f"  Port: {config.udp_port}")

    print(f"\n  Connection String: {config.get_connection_string()}")
    print("=" * 50)


def main():
    """CLI for testing connection configuration."""
    parser = argparse.ArgumentParser(
        description="MAVLink Connection Helper - Test and validate connection settings"
    )

    add_connection_arguments(parser)

    parser.add_argument(
        "--detect-ports",
        action="store_true",
        help="Detect available serial ports"
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate connection configuration"
    )

    args = parser.parse_args()

    # Detect serial ports
    if args.detect_ports:
        print("Detecting serial ports...")
        ports = detect_serial_ports()
        if ports:
            print(f"Found {len(ports)} serial port(s):")
            for port in ports:
                status = check_serial_port(port)
                access = "OK" if status["readable"] and status["writable"] else "NO ACCESS"
                print(f"  {port}: {access}")
        else:
            print("No serial ports found")
        print()

    # Create config from arguments
    config = ConnectionConfig.from_args(
        connection_type=args.connection_type,
        uart_device=args.uart_device,
        uart_baud=args.uart_baud,
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
    )

    # Print configuration
    print_connection_info(config)

    # Validate if requested
    if args.validate:
        print("\nValidating configuration...")
        result = validate_config(config)

        if result["errors"]:
            print("Errors:")
            for error in result["errors"]:
                print(f"  ✗ {error}")

        if result["warnings"]:
            print("Warnings:")
            for warning in result["warnings"]:
                print(f"  ⚠ {warning}")

        if result["valid"]:
            print("\n✓ Configuration is valid")
            sys.exit(0)
        else:
            print("\n✗ Configuration has errors")
            sys.exit(1)


if __name__ == "__main__":
    main()

