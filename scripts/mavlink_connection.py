#!/usr/bin/env python3
"""
mavlink_connection.py - MAVLink Connection Helper Utility

Provides a unified interface for connecting to MAVLink via UART or WiFi.
Supports both production (UART to TELEM2) and testing (WiFi to SITL) modes.

Usage:
    from scripts.mavlink_connection import get_connection_string, ConnectionConfig

    # UART mode (production - Cube+ Orange TELEM2)
    conn_str = get_connection_string("uart", device="/dev/ttyAMA0", baud=57600)

    # WiFi mode (testing - SITL)
    conn_str = get_connection_string("wifi", host="192.168.1.100", port=14540)

    # Using config object
    config = ConnectionConfig.from_env()
    conn_str = config.get_connection_string()

Environment Variables:
    PI_CONNECTION_TYPE  - Connection type: "uart" or "wifi" (default: wifi)
    PI_UART_DEVICE      - Serial device path (default: /dev/ttyAMA0)
    PI_UART_BAUD        - Serial baud rate (default: 57600)
    PI_WIFI_HOST        - WiFi host IP (default: localhost)
    PI_WIFI_PORT        - WiFi UDP port (default: 14540)
"""

import glob
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ConnectionType(Enum):
    """MAVLink connection types."""
    UART = "uart"
    WIFI = "wifi"


# Default configuration values
DEFAULTS = {
    "connection_type": "wifi",
    "uart_device": "/dev/ttyAMA0",
    "uart_baud": 57600,  # Standard for TELEM2
    "wifi_host": "localhost",
    "wifi_port": 14540,
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
        connection_type: Type of connection (uart or wifi).
        uart_device: Serial device path for UART mode.
        uart_baud: Baud rate for UART mode.
        wifi_host: Host IP/hostname for WiFi mode.
        wifi_port: UDP port for WiFi mode.
    """
    connection_type: ConnectionType
    uart_device: str = DEFAULTS["uart_device"]
    uart_baud: int = DEFAULTS["uart_baud"]
    wifi_host: str = DEFAULTS["wifi_host"]
    wifi_port: int = DEFAULTS["wifi_port"]

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
            print(f"Warning: Unknown connection type '{conn_type_str}', using wifi")
            conn_type = ConnectionType.WIFI

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
            wifi_host=os.environ.get(
                "PI_WIFI_HOST",
                DEFAULTS["wifi_host"]
            ),
            wifi_port=int(os.environ.get(
                "PI_WIFI_PORT",
                DEFAULTS["wifi_port"]
            )),
        )

    @classmethod
    def from_args(
        cls,
        connection_type: str = None,
        uart_device: str = None,
        uart_baud: int = None,
        wifi_host: str = None,
        wifi_port: int = None,
    ) -> "ConnectionConfig":
        """
        Create configuration from arguments with environment fallback.

        Args:
            connection_type: Connection type string ("uart" or "wifi").
            uart_device: Serial device path.
            uart_baud: Serial baud rate.
            wifi_host: WiFi host IP.
            wifi_port: WiFi UDP port.

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
        if wifi_host is not None:
            config.wifi_host = wifi_host
        if wifi_port is not None:
            config.wifi_port = wifi_port

        return config

    def get_connection_string(self) -> str:
        """
        Generate MAVSDK connection string based on configuration.

        Returns:
            str: MAVSDK-compatible connection string.
        """
        if self.connection_type == ConnectionType.UART:
            return f"serial://{self.uart_device}:{self.uart_baud}"
        else:
            return f"udp://{self.wifi_host}:{self.wifi_port}"

    def __str__(self) -> str:
        """String representation showing current settings."""
        if self.connection_type == ConnectionType.UART:
            return f"UART: {self.uart_device} @ {self.uart_baud} baud"
        else:
            return f"WiFi: {self.wifi_host}:{self.wifi_port}"


def get_connection_string(
    connection_type: str = "wifi",
    device: str = None,
    baud: int = None,
    host: str = None,
    port: int = None,
) -> str:
    """
    Generate MAVSDK connection string for the specified connection type.

    This is a convenience function for simple use cases.

    Args:
        connection_type: "uart" or "wifi" (default: wifi).
        device: Serial device path for UART (default: /dev/ttyAMA0).
        baud: Baud rate for UART (default: 57600).
        host: Host IP for WiFi (default: localhost).
        port: UDP port for WiFi (default: 14540).

    Returns:
        str: MAVSDK-compatible connection string.

    Examples:
        >>> get_connection_string("uart")
        'serial:///dev/ttyAMA0:57600'

        >>> get_connection_string("uart", device="/dev/ttyUSB0", baud=921600)
        'serial:///dev/ttyUSB0:921600'

        >>> get_connection_string("wifi", host="192.168.1.100")
        'udp://192.168.1.100:14540'

        >>> get_connection_string("wifi", host="192.168.1.100", port=14550)
        'udp://192.168.1.100:14550'
    """
    conn_type = connection_type.lower()

    if conn_type == "uart" or conn_type == "serial":
        device = device or DEFAULTS["uart_device"]
        baud = baud or DEFAULTS["uart_baud"]
        return f"serial://{device}:{baud}"

    elif conn_type == "wifi" or conn_type == "udp":
        host = host or DEFAULTS["wifi_host"]
        port = port or DEFAULTS["wifi_port"]
        return f"udp://{host}:{port}"

    else:
        raise ValueError(
            f"Unknown connection type: {connection_type}. "
            "Use 'uart' or 'wifi'."
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

    else:
        # Validate WiFi settings
        if not config.wifi_host:
            result["valid"] = False
            result["errors"].append("WiFi host not specified")

        if config.wifi_port < 1 or config.wifi_port > 65535:
            result["valid"] = False
            result["errors"].append(
                f"Invalid port number: {config.wifi_port}"
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
        choices=["uart", "wifi"],
        default=None,
        help="Connection type: uart (serial) or wifi (UDP). "
             "Default: PI_CONNECTION_TYPE env or 'wifi'"
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
        "--wifi-host",
        default=None,
        help=f"Host IP for WiFi mode. "
             f"Default: PI_WIFI_HOST env or '{DEFAULTS['wifi_host']}'"
    )

    conn_group.add_argument(
        "--wifi-port",
        type=int,
        default=None,
        help=f"UDP port for WiFi mode. "
             f"Default: PI_WIFI_PORT env or {DEFAULTS['wifi_port']}"
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
    else:
        print(f"  Host: {config.wifi_host}")
        print(f"  Port: {config.wifi_port}")

    print(f"\n  Connection String: {config.get_connection_string()}")
    print("=" * 50)


def main():
    """CLI for testing connection configuration."""
    import argparse

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
        wifi_host=args.wifi_host,
        wifi_port=args.wifi_port,
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

