#!/usr/bin/env python3
"""
manual_control_app.py - Keyboard-Based Manual Drone Control

Main application for manual drone control using keyboard input.
Uses MAVSDK's manual_control plugin with Position Control mode for
smooth, GPS-stabilized control.

Features:
    - Keyboard control via pynput (works over SSH)
    - Integration with mode_manager for tracking override
    - Position Control mode for stability
    - Automatic hover on timeout
    - Emergency stop functionality

Control Scheme (Mode 2):
    W/S         - Throttle (climb/descend)
    A/D         - Yaw (rotate left/right)
    Arrow Up/Down   - Pitch (forward/back)
    Arrow Left/Right - Roll (strafe left/right)
    T           - Arm & Takeoff
    L           - Land
    Space       - Emergency stop (hover)
    G           - Toggle person tracking
    Q           - Quit

Usage:
    # Connect to SITL
    python -m examples.manual_control.manual_control_app -c tcp --tcp-host localhost

    # Connect via UDP
    python -m examples.manual_control.manual_control_app -c udp --udp-port 14540

    # With custom sensitivity
    python -m examples.manual_control.manual_control_app --sensitivity 0.5
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + "/../..")

from examples.manual_control.keyboard_controller import (
    KeyboardController,
    ControlInput,
    SpecialAction,
)
from examples.common.drone_helpers import (
    connect_drone,
    wait_for_gps,
    setup_logging,
    create_argument_parser,
    get_connection_string_from_args,
    setup_signal_handlers,
    is_shutdown_requested,
)
from examples.common.telemetry_manager import TelemetryManager

# Module logger
logger = logging.getLogger(__name__)

# Control rate in Hz (must be >= 10 to prevent RC loss timeout)
CONTROL_RATE_HZ = 20.0

# Default sensitivity values
DEFAULT_SENSITIVITY = 0.7
DEFAULT_THROTTLE_SENSITIVITY = 0.3


class ManualControlApp:
    """
    Manual control application using MAVSDK manual_control plugin.

    Provides keyboard-based manual control with integration to the
    mode_manager for coexistence with autonomous features like person
    tracking.

    Attributes:
        drone: MAVSDK System instance.
        keyboard: KeyboardController instance.
        mode_manager: Optional ModeManager for tracking integration.
        running: Whether the control loop is active.
    """

    def __init__(
        self,
        sensitivity: float = DEFAULT_SENSITIVITY,
        throttle_sensitivity: float = DEFAULT_THROTTLE_SENSITIVITY,
    ):
        """
        Initialize the manual control application.

        Args:
            sensitivity: Control sensitivity for pitch/roll/yaw (0.0-1.0).
            throttle_sensitivity: Control sensitivity for throttle (0.0-1.0).
        """
        self.drone = None
        self.keyboard = KeyboardController(
            sensitivity=sensitivity,
            throttle_sensitivity=throttle_sensitivity,
        )
        self.mode_manager = None
        self.telemetry = None  # TelemetryManager instance

        self._running = False
        self._quit_requested = False
        self._position_control_active = False
        self._last_input_time = 0.0
        self._last_telemetry_update = 0.0
        self._loop = None  # Event loop reference for async callbacks

        # Register keyboard callbacks
        self.keyboard.on_quit(self._on_quit)
        self.keyboard.on_toggle_tracking(self._on_toggle_tracking)
        self.keyboard.on_emergency_stop(self._on_emergency_stop)
        self.keyboard.on_arm_takeoff(self._on_arm_takeoff)
        self.keyboard.on_land(self._on_land)

        logger.debug("ManualControlApp initialized")

    @property
    def running(self) -> bool:
        """Check if the control loop is running."""
        return self._running

    async def connect(self, connection_string: str, timeout: float = 30.0) -> bool:
        """
        Connect to the drone.

        Args:
            connection_string: MAVSDK connection string.
            timeout: Connection timeout in seconds.

        Returns:
            bool: True if connected successfully.
        """
        self.drone = await connect_drone(connection_string, timeout=timeout)
        return self.drone is not None

    async def setup_mode_manager(
        self,
        http_port: int = 8080,
        manual_timeout: float = 3.0,
    ) -> None:
        """
        Set up optional mode manager for tracking integration.

        Args:
            http_port: HTTP API port for mode manager.
            manual_timeout: Manual control timeout in seconds.
        """
        try:
            from examples.person_tracker.mode_manager import ModeManager
            from examples.person_tracker.config import MODE_MANAGER_CONFIG

            config = MODE_MANAGER_CONFIG
            config.http_port = http_port

            self.mode_manager = ModeManager(
                config=config,
                manual_timeout=manual_timeout,
            )
            await self.mode_manager.start(drone=self.drone)
            logger.info("Mode manager started on port %d", http_port)

        except ImportError:
            logger.warning("Mode manager not available (person_tracker module missing)")
            self.mode_manager = None

    async def run(self) -> bool:
        """
        Run the manual control loop.

        Returns:
            bool: True if completed normally, False on error.
        """
        if self.drone is None:
            logger.error("Not connected to drone")
            return False

        # Store event loop reference for async callbacks
        self._loop = asyncio.get_event_loop()

        # Start telemetry manager for background telemetry reading
        self.telemetry = TelemetryManager(self.drone)
        await self.telemetry.start()

        # Start keyboard listener
        if not self.keyboard.start():
            logger.error("Failed to start keyboard controller")
            await self.telemetry.stop()
            return False

        # Activate the controller (enable key capture)
        self.keyboard.activate()

        self._running = True
        self._quit_requested = False
        self._last_telemetry_update = 0.0

        logger.info("Manual control active")
        # Show the ASCII art remote
        self.keyboard.print_remote()

        interval = 1.0 / CONTROL_RATE_HZ
        telemetry_update_interval = 0.2  # Update telemetry display every 200ms

        try:
            while self._running and not self._quit_requested and not is_shutdown_requested():
                loop_start = time.time()

                # Get keyboard input
                control_input = self.keyboard.get_input()

                # Handle special actions
                if control_input.special_action == SpecialAction.QUIT:
                    logger.info("Quit requested")
                    break

                # Update mode manager if available
                if self.mode_manager and control_input.has_input:
                    await self.mode_manager.set_manual_input()

                # Send control input to drone
                await self._send_control(control_input)

                # Update telemetry display (throttled)
                current_time = time.time()
                if current_time - self._last_telemetry_update >= telemetry_update_interval:
                    self.keyboard.update_telemetry(
                        altitude_m=self.telemetry.position.relative_altitude_m,
                        armed=self.telemetry.flight_state.armed,
                        in_air=self.telemetry.flight_state.in_air,
                        flight_mode=self.telemetry.flight_state.flight_mode,
                        battery_percent=self.telemetry.battery.remaining_percent * 100.0,
                        voltage_v=self.telemetry.battery.voltage_v,
                    )
                    self._last_telemetry_update = current_time

                # Sleep for remaining interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Control loop cancelled")
        except Exception as e:
            logger.error("Control loop error: %s", e)
            return False
        finally:
            self._running = False
            await self._cleanup()

        return True

    async def _send_control(self, control_input: ControlInput) -> None:
        """
        Send control input to the drone via manual_control plugin.

        Args:
            control_input: Normalized control values.
        """
        try:
            # Start position control if not active
            if not self._position_control_active:
                # Must send initial setpoint before starting
                await self.drone.manual_control.set_manual_control_input(
                    control_input.x,
                    control_input.y,
                    control_input.z,
                    control_input.r,
                )

                # Start position control mode
                try:
                    await self.drone.manual_control.start_position_control()
                    self._position_control_active = True
                    logger.info("Position control mode started")
                except Exception as e:
                    # May fail if already in a compatible mode
                    logger.debug("start_position_control: %s", e)
                    self._position_control_active = True

            # Send manual control input
            await self.drone.manual_control.set_manual_control_input(
                control_input.x,  # Pitch (-1 back, +1 forward)
                control_input.y,  # Roll (-1 left, +1 right)
                control_input.z,  # Throttle (0 down, 1 up)
                control_input.r,  # Yaw (-1 CCW, +1 CW)
            )

            # Track input time for status display
            if control_input.has_input:
                self._last_input_time = time.time()

        except Exception as e:
            logger.error("Failed to send control input: %s", e)

    async def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")

        # Deactivate and stop keyboard listener
        self.keyboard.deactivate()
        self.keyboard.stop()

        # Stop telemetry manager
        if self.telemetry:
            await self.telemetry.stop()

        # Send hover command
        if self.drone and self._position_control_active:
            try:
                await self.drone.manual_control.set_manual_control_input(
                    0.0, 0.0, 0.5, 0.0  # Hover
                )
                logger.info("Hover command sent")
            except Exception as e:
                logger.warning("Failed to send hover: %s", e)

        # Stop mode manager
        if self.mode_manager:
            await self.mode_manager.stop()

        logger.info("Cleanup complete")

    def _on_quit(self) -> None:
        """Handle quit request from keyboard."""
        self._quit_requested = True

    def _on_toggle_tracking(self) -> None:
        """Handle tracking toggle request from keyboard."""
        if self.mode_manager and self._loop:
            # Schedule the async toggle in the event loop
            asyncio.run_coroutine_threadsafe(
                self._toggle_tracking_async(), self._loop
            )
        else:
            logger.warning("Mode manager not available for tracking toggle")

    async def _toggle_tracking_async(self) -> None:
        """Async tracking toggle."""
        if self.mode_manager:
            from examples.person_tracker.mode_manager import ModeSource

            new_state = await self.mode_manager.toggle(ModeSource.MANUAL_KEYBOARD)
            logger.info("Tracking toggled: %s", "enabled" if new_state else "disabled")

    def _on_emergency_stop(self) -> None:
        """Handle emergency stop from keyboard."""
        logger.warning("Emergency stop - sending hover command")
        # The control loop will pick up the special action

    def _on_arm_takeoff(self) -> None:
        """Handle arm & takeoff request from keyboard."""
        if self.drone and self._loop:
            logger.info("Arm & Takeoff requested - executing...")
            asyncio.run_coroutine_threadsafe(
                self._arm_takeoff_async(), self._loop
            )
        else:
            logger.warning("Cannot arm/takeoff - drone not connected")

    async def _arm_takeoff_async(self) -> None:
        """Async arm and takeoff."""
        from examples.common import arm_and_takeoff

        success = await arm_and_takeoff(self.drone, altitude=5.0)
        if success:
            logger.info("Takeoff complete")
        else:
            logger.error("Takeoff failed")

    def _on_land(self) -> None:
        """Handle land request from keyboard."""
        if self.drone and self._loop:
            logger.info("Land requested - executing...")
            asyncio.run_coroutine_threadsafe(
                self._land_async(), self._loop
            )
        else:
            logger.warning("Cannot land - drone not connected")

    async def _land_async(self) -> None:
        """Async land."""
        from examples.common import land_and_disarm

        success = await land_and_disarm(self.drone)
        if success:
            logger.info("Landing complete")
        else:
            logger.error("Landing failed")


async def main_async(
    connection_string: str,
    sensitivity: float,
    throttle_sensitivity: float,
    http_port: int,
    manual_timeout: float,
) -> bool:
    """
    Async main function.

    Args:
        connection_string: MAVSDK connection string.
        sensitivity: Control sensitivity.
        throttle_sensitivity: Throttle sensitivity.
        http_port: HTTP API port.
        manual_timeout: Manual control timeout.

    Returns:
        bool: True if successful.
    """
    app = ManualControlApp(
        sensitivity=sensitivity,
        throttle_sensitivity=throttle_sensitivity,
    )

    # Connect to drone
    logger.info("Connecting to drone...")
    if not await app.connect(connection_string):
        logger.error("Failed to connect to drone")
        return False

    # Wait for GPS (required for position control)
    logger.info("Waiting for GPS lock...")
    if not await wait_for_gps(app.drone, timeout=60.0):
        logger.warning("GPS lock not acquired, proceeding anyway...")

    # Set up mode manager (optional)
    await app.setup_mode_manager(
        http_port=http_port,
        manual_timeout=manual_timeout,
    )

    # Run control loop
    return await app.run()


def main():
    """Main entry point."""
    # Set up signal handlers
    setup_signal_handlers()

    # Create argument parser
    parser = create_argument_parser(
        description="Keyboard-based manual drone control",
        add_altitude=False,
    )

    # Add manual control specific arguments
    parser.add_argument(
        "--sensitivity",
        type=float,
        default=DEFAULT_SENSITIVITY,
        help=f"Control sensitivity for pitch/roll/yaw (default: {DEFAULT_SENSITIVITY})",
    )
    parser.add_argument(
        "--throttle-sensitivity",
        type=float,
        default=DEFAULT_THROTTLE_SENSITIVITY,
        help=f"Throttle sensitivity (default: {DEFAULT_THROTTLE_SENSITIVITY})",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8080,
        help="HTTP API port for mode manager (default: 8080)",
    )
    parser.add_argument(
        "--manual-timeout",
        type=float,
        default=3.0,
        help="Manual control timeout in seconds (default: 3.0)",
    )

    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)

    # Get connection string
    connection_string = get_connection_string_from_args(args)

    print("\n" + "=" * 60)
    print("MANUAL DRONE CONTROL")
    print("=" * 60)
    print(f"  Connection: {connection_string}")
    print(f"  Sensitivity: {args.sensitivity}")
    print(f"  Throttle: {args.throttle_sensitivity}")
    print(f"  HTTP Port: {args.http_port}")
    print("=" * 60 + "\n")

    # Run async main
    try:
        success = asyncio.run(
            main_async(
                connection_string=connection_string,
                sensitivity=args.sensitivity,
                throttle_sensitivity=args.throttle_sensitivity,
                http_port=args.http_port,
                manual_timeout=args.manual_timeout,
            )
        )
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)


if __name__ == "__main__":
    main()

