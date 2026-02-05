#!/usr/bin/env python3
"""
keyboard_controller.py - Non-blocking Keyboard Input Handler

Provides keyboard-based control input for drone manual control.
Uses pynput for cross-platform, non-blocking keyboard input that
works over SSH connections.

Control Scheme (Mode 2 Standard):
    W/S         - Throttle (up/down) -> z-axis
    A/D         - Yaw (left/right)   -> r-axis
    Arrow Up/Down   - Pitch (forward/back) -> x-axis
    Arrow Left/Right - Roll (left/right)   -> y-axis
    Space       - Emergency stop (all axes to neutral)
    T           - Toggle tracking mode
    Q           - Quit manual control

Usage:
    from examples.manual_control.keyboard_controller import KeyboardController

    controller = KeyboardController()
    controller.start()

    # In control loop:
    control_input = controller.get_input()
    # Use control_input.x, control_input.y, control_input.z, control_input.r

    controller.stop()
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


class SpecialAction(Enum):
    """Special actions triggered by specific keys."""

    NONE = auto()
    EMERGENCY_STOP = auto()
    TOGGLE_TRACKING = auto()
    ARM_TAKEOFF = auto()
    LAND = auto()
    QUIT = auto()


@dataclass
class ControlInput:
    """
    Normalized control input values.

    All values are in range [-1.0, 1.0] except z (throttle) which
    is [0.0, 1.0] for multicopters.

    Attributes:
        x: Pitch axis (-1 = back, +1 = forward).
        y: Roll axis (-1 = left, +1 = right).
        z: Throttle axis (0 = down, +1 = up for multicopter).
        r: Yaw axis (-1 = counter-clockwise, +1 = clockwise).
        timestamp: When this input was captured.
        has_input: Whether any control key is currently pressed.
        special_action: Any special action triggered.
    """

    x: float = 0.0  # Pitch (forward/back)
    y: float = 0.0  # Roll (left/right)
    z: float = 0.5  # Throttle (default to hover for multicopter)
    r: float = 0.0  # Yaw (rotation)
    timestamp: float = field(default_factory=time.time)
    has_input: bool = False
    special_action: SpecialAction = SpecialAction.NONE

    def __str__(self) -> str:
        return (
            f"Input(x={self.x:+.2f}, y={self.y:+.2f}, "
            f"z={self.z:.2f}, r={self.r:+.2f}, input={self.has_input})"
        )

    @property
    def is_neutral(self) -> bool:
        """Check if all axes are at neutral position."""
        return (
            abs(self.x) < 0.01
            and abs(self.y) < 0.01
            and abs(self.z - 0.5) < 0.01  # Neutral throttle is 0.5
            and abs(self.r) < 0.01
        )


@dataclass
class KeyMapping:
    """
    Key-to-axis mapping configuration.

    Attributes:
        throttle_up: Key for throttle up (z+).
        throttle_down: Key for throttle down (z-).
        yaw_left: Key for yaw left/counter-clockwise (r-).
        yaw_right: Key for yaw right/clockwise (r+).
        pitch_forward: Key for pitch forward (x+).
        pitch_back: Key for pitch backward (x-).
        roll_left: Key for roll left (y-).
        roll_right: Key for roll right (y+).
        emergency_stop: Key for emergency stop (hover).
        arm_takeoff: Key for arm and takeoff.
        land: Key for land.
        toggle_tracking: Key for toggle tracking mode.
        quit: Key for quit.
    """

    throttle_up: str = "w"
    throttle_down: str = "s"
    yaw_left: str = "a"
    yaw_right: str = "d"
    pitch_forward: str = "up"
    pitch_back: str = "down"
    roll_left: str = "left"
    roll_right: str = "right"
    emergency_stop: str = "space"
    arm_takeoff: str = "t"
    land: str = "l"
    toggle_tracking: str = "g"  # Changed from 't' to 'g' for "go tracking"
    quit: str = "q"


# Default key mapping
DEFAULT_KEY_MAPPING = KeyMapping()


class KeyboardController:
    """
    Non-blocking keyboard input controller for drone manual control.

    Uses pynput for keyboard event handling in a separate thread.
    Thread-safe access to current control state.

    Attributes:
        key_mapping: Key-to-axis mapping configuration.
        sensitivity: Control sensitivity multiplier (0.0-1.0).
        is_running: Whether the controller is currently active.
    """

    def __init__(
        self,
        key_mapping: Optional[KeyMapping] = None,
        sensitivity: float = 1.0,
        throttle_sensitivity: float = 0.5,
    ):
        """
        Initialize the keyboard controller.

        Args:
            key_mapping: Custom key mapping. Uses defaults if None.
            sensitivity: Control sensitivity (0.0-1.0) for x, y, r axes.
            throttle_sensitivity: Throttle sensitivity for z axis.
        """
        self.key_mapping = key_mapping or DEFAULT_KEY_MAPPING
        self.sensitivity = max(0.1, min(1.0, sensitivity))
        self.throttle_sensitivity = max(0.1, min(1.0, throttle_sensitivity))

        # Current state
        self._pressed_keys: Set[str] = set()
        self._special_action: SpecialAction = SpecialAction.NONE
        self._last_input_time: float = 0.0

        # Debouncing for special actions (prevent key repeat)
        self._last_action_time: Dict[SpecialAction, float] = {}
        self._action_debounce_time: float = 0.5  # 500ms debounce

        # Threading
        self._lock = threading.Lock()
        self._listener = None
        self._running = False
        self._active = False  # Context flag - only capture when active

        # Telemetry data (updated from external source)
        self._telemetry = {
            "altitude_m": 0.0,
            "armed": False,
            "in_air": False,
            "flight_mode": "UNKNOWN",
            "battery_percent": 100.0,
            "voltage_v": 0.0,
        }

        # Callbacks
        self._on_quit_callbacks: list[Callable] = []
        self._on_toggle_callbacks: list[Callable] = []
        self._on_emergency_callbacks: list[Callable] = []
        self._on_arm_takeoff_callbacks: list[Callable] = []
        self._on_land_callbacks: list[Callable] = []

        logger.debug(
            "KeyboardController initialized (sensitivity=%.2f, throttle=%.2f)",
            sensitivity,
            throttle_sensitivity,
        )

    @property
    def is_running(self) -> bool:
        """Check if the keyboard listener is running."""
        return self._running

    def start(self) -> bool:
        """
        Start the keyboard listener.

        Note: The listener starts but is inactive by default. Call activate()
        to enable key capture.

        Returns:
            bool: True if started successfully, False if already running or failed.
        """
        if self._running:
            logger.warning("KeyboardController already running")
            return False

        try:
            from pynput import keyboard

            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.start()
            self._running = True
            self._active = False  # Start inactive - must call activate()

            logger.info("KeyboardController started (inactive - call activate() to enable)")
            return True

        except ImportError:
            logger.error(
                "pynput not installed. Install with: pip install pynput"
            )
            return False
        except Exception as e:
            logger.error("Failed to start keyboard listener: %s", e)
            return False

    def activate(self) -> None:
        """
        Activate the keyboard controller (enable key capture).

        Only keys will be captured when the controller is active.
        This prevents capturing keys when the app is not in focus.
        """
        with self._lock:
            self._active = True
        logger.debug("KeyboardController activated")

    def deactivate(self) -> None:
        """
        Deactivate the keyboard controller (disable key capture).

        Clears all pressed keys and stops capturing input.
        """
        with self._lock:
            self._active = False
            self._pressed_keys.clear()
            self._special_action = SpecialAction.NONE
        logger.debug("KeyboardController deactivated")

    @property
    def is_active(self) -> bool:
        """Check if the controller is active (capturing keys)."""
        return self._active

    def stop(self) -> None:
        """Stop the keyboard listener."""
        self._running = False

        if self._listener:
            self._listener.stop()
            self._listener = None

        with self._lock:
            self._pressed_keys.clear()
            self._special_action = SpecialAction.NONE

        logger.info("KeyboardController stopped")

    def get_input(self) -> ControlInput:
        """
        Get current control input based on pressed keys.

        Returns:
            ControlInput: Current normalized control values.
        """
        with self._lock:
            pressed = self._pressed_keys.copy()
            action = self._special_action
            self._special_action = SpecialAction.NONE  # Clear after reading

        # Check for emergency stop first
        if action == SpecialAction.EMERGENCY_STOP:
            return ControlInput(
                x=0.0,
                y=0.0,
                z=0.5,  # Neutral throttle (hover)
                r=0.0,
                timestamp=time.time(),
                has_input=True,
                special_action=action,
            )

        # Calculate axis values from pressed keys
        x = 0.0  # Pitch
        y = 0.0  # Roll
        z = 0.5  # Throttle (neutral)
        r = 0.0  # Yaw

        has_input = len(pressed) > 0

        # Pitch (forward/back) - Arrow Up/Down
        if self.key_mapping.pitch_forward in pressed:
            x += self.sensitivity
        if self.key_mapping.pitch_back in pressed:
            x -= self.sensitivity

        # Roll (left/right) - Arrow Left/Right
        if self.key_mapping.roll_right in pressed:
            y += self.sensitivity
        if self.key_mapping.roll_left in pressed:
            y -= self.sensitivity

        # Throttle (up/down) - W/S
        if self.key_mapping.throttle_up in pressed:
            z += self.throttle_sensitivity
        if self.key_mapping.throttle_down in pressed:
            z -= self.throttle_sensitivity

        # Yaw (left/right) - A/D
        if self.key_mapping.yaw_right in pressed:
            r += self.sensitivity
        if self.key_mapping.yaw_left in pressed:
            r -= self.sensitivity

        # Clamp values
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        z = max(0.0, min(1.0, z))
        r = max(-1.0, min(1.0, r))

        return ControlInput(
            x=x,
            y=y,
            z=z,
            r=r,
            timestamp=time.time(),
            has_input=has_input,
            special_action=action,
        )

    def on_quit(self, callback: Callable) -> None:
        """Register callback for quit action."""
        self._on_quit_callbacks.append(callback)

    def on_toggle_tracking(self, callback: Callable) -> None:
        """Register callback for tracking toggle action."""
        self._on_toggle_callbacks.append(callback)

    def on_emergency_stop(self, callback: Callable) -> None:
        """Register callback for emergency stop action."""
        self._on_emergency_callbacks.append(callback)

    def on_arm_takeoff(self, callback: Callable) -> None:
        """Register callback for arm & takeoff action."""
        self._on_arm_takeoff_callbacks.append(callback)

    def on_land(self, callback: Callable) -> None:
        """Register callback for land action."""
        self._on_land_callbacks.append(callback)

    def _normalize_key(self, key) -> str:
        """
        Normalize key object to string representation.

        Args:
            key: pynput Key object or KeyCode.

        Returns:
            str: Normalized key name.
        """
        try:
            from pynput.keyboard import Key

            # Handle special keys
            key_map = {
                Key.up: "up",
                Key.down: "down",
                Key.left: "left",
                Key.right: "right",
                Key.space: "space",
                Key.enter: "enter",
                Key.esc: "esc",
                Key.tab: "tab",
            }

            if key in key_map:
                return key_map[key]

            # Handle regular character keys
            if hasattr(key, "char") and key.char:
                return key.char.lower()

            return str(key)

        except Exception:
            return str(key)

    def _on_key_press(self, key) -> None:
        """Handle key press event."""
        # Only capture keys when active
        if not self._active:
            return

        key_name = self._normalize_key(key)
        current_time = time.time()

        with self._lock:
            self._pressed_keys.add(key_name)
            self._last_input_time = current_time

            # Check for special actions with debouncing
            if key_name == self.key_mapping.emergency_stop:
                if self._should_trigger_action(SpecialAction.EMERGENCY_STOP, current_time):
                    self._special_action = SpecialAction.EMERGENCY_STOP
                    for callback in self._on_emergency_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error("Emergency callback error: %s", e)

            elif key_name == self.key_mapping.arm_takeoff:
                if self._should_trigger_action(SpecialAction.ARM_TAKEOFF, current_time):
                    self._special_action = SpecialAction.ARM_TAKEOFF
                    for callback in self._on_arm_takeoff_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error("Arm/Takeoff callback error: %s", e)

            elif key_name == self.key_mapping.land:
                if self._should_trigger_action(SpecialAction.LAND, current_time):
                    self._special_action = SpecialAction.LAND
                    for callback in self._on_land_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error("Land callback error: %s", e)

            elif key_name == self.key_mapping.toggle_tracking:
                if self._should_trigger_action(SpecialAction.TOGGLE_TRACKING, current_time):
                    self._special_action = SpecialAction.TOGGLE_TRACKING
                    for callback in self._on_toggle_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error("Toggle callback error: %s", e)

            elif key_name == self.key_mapping.quit:
                if self._should_trigger_action(SpecialAction.QUIT, current_time):
                    self._special_action = SpecialAction.QUIT
                    for callback in self._on_quit_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error("Quit callback error: %s", e)

    def _should_trigger_action(self, action: SpecialAction, current_time: float) -> bool:
        """
        Check if action should be triggered based on debounce time.

        Args:
            action: The action to check.
            current_time: Current timestamp.

        Returns:
            bool: True if action should be triggered.
        """
        last_time = self._last_action_time.get(action, 0.0)
        if current_time - last_time >= self._action_debounce_time:
            self._last_action_time[action] = current_time
            return True
        return False

    def _on_key_release(self, key) -> None:
        """Handle key release event."""
        # Only process releases when active
        if not self._active:
            return

        key_name = self._normalize_key(key)

        with self._lock:
            self._pressed_keys.discard(key_name)

    def get_pressed_keys(self) -> Set[str]:
        """
        Get currently pressed keys (for debugging).

        Returns:
            Set[str]: Set of currently pressed key names.
        """
        with self._lock:
            return self._pressed_keys.copy()

    def update_telemetry(
        self,
        altitude_m: float = None,
        armed: bool = None,
        in_air: bool = None,
        flight_mode: str = None,
        battery_percent: float = None,
        voltage_v: float = None,
    ) -> None:
        """
        Update telemetry data for display in remote.

        Args:
            altitude_m: Current altitude in meters.
            armed: Whether the drone is armed.
            in_air: Whether the drone is in the air.
            flight_mode: Current flight mode.
            battery_percent: Battery remaining percentage (0-100).
            voltage_v: Battery voltage in volts.
        """
        with self._lock:
            if altitude_m is not None:
                self._telemetry["altitude_m"] = altitude_m
            if armed is not None:
                self._telemetry["armed"] = armed
            if in_air is not None:
                self._telemetry["in_air"] = in_air
            if flight_mode is not None:
                self._telemetry["flight_mode"] = flight_mode
            if battery_percent is not None:
                self._telemetry["battery_percent"] = battery_percent
            if voltage_v is not None:
                self._telemetry["voltage_v"] = voltage_v

    def get_remote_display(self) -> str:
        """
        Generate ASCII art remote control display showing available keys and pressed state.

        Returns:
            str: ASCII art representation of the remote control.
        """
        with self._lock:
            pressed = self._pressed_keys.copy()
            tel = self._telemetry.copy()

        def key_display(key: str, label: str, width: int = 3) -> str:
            """Format a key with highlighting if pressed."""
            is_pressed = key in pressed
            if is_pressed:
                # Highlight pressed key with brackets
                return f"[{label:^{width-2}}]"
            else:
                return f" {label:^{width-2}} "

        # Format telemetry values
        alt_str = f"{tel['altitude_m']:6.2f}m"
        armed_str = "ARMED" if tel['armed'] else "DISARMED"
        in_air_str = "IN AIR" if tel['in_air'] else "GROUND"
        mode_str = str(tel['flight_mode'])[:12]  # Truncate long mode names
        bat_str = f"{tel['battery_percent']:5.1f}%"
        volt_str = f"{tel['voltage_v']:5.2f}V"

        # Build the remote display
        lines = []
        lines.append("╔════════════════════════════════════════════════╗")
        lines.append("║         DRONE MANUAL CONTROL REMOTE          ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║              TELEMETRY                         ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append(f"║  Altitude: {alt_str:>15}                    ║")
        lines.append(f"║  Status:   {armed_str:>15}                    ║")
        lines.append(f"║  Flight:   {in_air_str:>15}                    ║")
        lines.append(f"║  Mode:     {mode_str:>15}                    ║")
        lines.append(f"║  Battery:  {bat_str:>15}                    ║")
        lines.append(f"║  Voltage:  {volt_str:>15}                    ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║                                                ║")
        lines.append("║              THROTTLE & YAW                    ║")
        lines.append("║                                                ║")
        lines.append(f"║         {key_display(self.key_mapping.throttle_up, 'W', 5)}         ║")
        lines.append("║                                                ║")
        lines.append(f"║  {key_display(self.key_mapping.yaw_left, 'A', 5)}     {key_display(self.key_mapping.yaw_right, 'D', 5)}  ║")
        lines.append("║                                                ║")
        lines.append(f"║         {key_display(self.key_mapping.throttle_down, 'S', 5)}         ║")
        lines.append("║                                                ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║                                                ║")
        lines.append("║              PITCH & ROLL                      ║")
        lines.append("║                                                ║")
        lines.append(f"║         {key_display(self.key_mapping.pitch_forward, '↑', 5)}         ║")
        lines.append("║                                                ║")
        lines.append(f"║  {key_display(self.key_mapping.roll_left, '←', 5)}     {key_display(self.key_mapping.roll_right, '→', 5)}  ║")
        lines.append("║                                                ║")
        lines.append(f"║         {key_display(self.key_mapping.pitch_back, '↓', 5)}         ║")
        lines.append("║                                                ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║                                                ║")
        lines.append("║              FLIGHT ACTIONS                     ║")
        lines.append("║                                                ║")
        lines.append(f"║  {key_display(self.key_mapping.arm_takeoff, 'T', 5)}  {key_display(self.key_mapping.land, 'L', 5)}  {key_display(self.key_mapping.emergency_stop, 'SPACE', 8)}  ║")
        lines.append("║  Takeoff  Land    Hover                        ║")
        lines.append("║                                                ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║                                                ║")
        lines.append("║              OTHER ACTIONS                     ║")
        lines.append("║                                                ║")
        lines.append(f"║  {key_display(self.key_mapping.toggle_tracking, 'G', 5)}  {key_display(self.key_mapping.quit, 'Q', 5)}                              ║")
        lines.append("║  Track    Quit                                ║")
        lines.append("║                                                ║")
        lines.append("╠════════════════════════════════════════════════╣")
        lines.append("║  Status: " + ("ACTIVE " if self._active else "INACTIVE") + "                              ║")
        lines.append("╚════════════════════════════════════════════════╝")

        return "\n".join(lines)

    def print_remote(self) -> None:
        """Print the ASCII art remote control display."""
        print("\n" + self.get_remote_display() + "\n")


def print_controls() -> None:
    """Print control scheme to console (legacy function)."""
    print("\n" + "=" * 50)
    print("KEYBOARD CONTROLS (Mode 2 Layout)")
    print("=" * 50)
    print("  Movement:")
    print("    W/S         - Throttle Up/Down")
    print("    A/D         - Yaw Left/Right (rotation)")
    print("    ↑/↓         - Pitch Forward/Back")
    print("    ←/→         - Roll Left/Right")
    print()
    print("  Flight Actions:")
    print("    T           - Arm & Takeoff (5m)")
    print("    L           - Land")
    print("    Space       - Emergency Stop (hover)")
    print()
    print("  Other:")
    print("    G           - Toggle Tracking Mode")
    print("    Q           - Quit Manual Control")
    print("=" * 50 + "\n")
    print("Note: Use controller.print_remote() for visual remote display")


if __name__ == "__main__":
    # Demo/test the keyboard controller
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print_controls()

    controller = KeyboardController()

    # Register callbacks
    quit_requested = False

    def on_quit():
        global quit_requested
        quit_requested = True

    controller.on_quit(on_quit)
    controller.on_emergency_stop(lambda: print(">>> EMERGENCY STOP <<<"))
    controller.on_toggle_tracking(lambda: print(">>> TOGGLE TRACKING <<<"))

    if not controller.start():
        print("Failed to start keyboard controller")
        sys.exit(1)

    print("\nPress keys to test. Press Q to quit.\n")

    try:
        while not quit_requested:
            control_input = controller.get_input()

            # Only print if there's input
            if control_input.has_input or not control_input.is_neutral:
                print(f"\r{control_input}  ", end="", flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        controller.stop()
        print("\nKeyboard controller stopped")

