#!/usr/bin/env python3
"""
test_manual_control.py - Tests for Manual Control Module

Tests for:
- KeyboardController control input generation
- ControlInput dataclass
- Mode manager manual control extensions

Run with:
    pytest tests/test_manual_control.py -v
"""

import asyncio
import sys
import time

import pytest

# Add project root to path
sys.path.insert(0, sys.path[0] + "/..")

from examples.manual_control.keyboard_controller import (
    KeyboardController,
    ControlInput,
    KeyMapping,
    SpecialAction,
    DEFAULT_KEY_MAPPING,
)
from examples.person_tracker.mode_manager import (
    ModeManager,
    ModeSource,
    MODE_PRIORITY,
)


# =============================================================================
# ControlInput Tests
# =============================================================================


class TestControlInput:
    """Tests for ControlInput dataclass."""

    def test_default_values(self):
        """Test default ControlInput values."""
        control = ControlInput()
        assert control.x == 0.0
        assert control.y == 0.0
        assert control.z == 0.5  # Neutral throttle for hover
        assert control.r == 0.0
        assert control.has_input is False
        assert control.special_action == SpecialAction.NONE

    def test_is_neutral(self):
        """Test is_neutral property."""
        # Default is neutral
        control = ControlInput()
        assert control.is_neutral is True

        # With non-zero values
        control = ControlInput(x=0.5)
        assert control.is_neutral is False

        # Throttle at non-neutral
        control = ControlInput(z=0.8)
        assert control.is_neutral is False

    def test_string_representation(self):
        """Test string representation."""
        control = ControlInput(x=0.5, y=-0.3, z=0.7, r=0.2, has_input=True)
        s = str(control)
        assert "+0.50" in s
        assert "-0.30" in s
        assert "0.70" in s
        assert "+0.20" in s
        assert "True" in s


class TestKeyMapping:
    """Tests for KeyMapping dataclass."""

    def test_default_mapping(self):
        """Test default key mapping values."""
        mapping = DEFAULT_KEY_MAPPING
        assert mapping.throttle_up == "w"
        assert mapping.throttle_down == "s"
        assert mapping.yaw_left == "a"
        assert mapping.yaw_right == "d"
        assert mapping.pitch_forward == "up"
        assert mapping.pitch_back == "down"
        assert mapping.roll_left == "left"
        assert mapping.roll_right == "right"
        assert mapping.emergency_stop == "space"
        assert mapping.toggle_tracking == "t"
        assert mapping.quit == "q"

    def test_custom_mapping(self):
        """Test custom key mapping."""
        mapping = KeyMapping(
            throttle_up="i",
            throttle_down="k",
            yaw_left="j",
            yaw_right="l",
        )
        assert mapping.throttle_up == "i"
        assert mapping.throttle_down == "k"
        assert mapping.yaw_left == "j"
        assert mapping.yaw_right == "l"


# =============================================================================
# KeyboardController Tests
# =============================================================================


class TestKeyboardController:
    """Tests for KeyboardController class."""

    def test_controller_creation(self):
        """Test controller initialization."""
        controller = KeyboardController()
        assert controller.is_running is False
        assert controller.sensitivity == 1.0
        assert controller.throttle_sensitivity == 0.5

    def test_custom_sensitivity(self):
        """Test controller with custom sensitivity."""
        controller = KeyboardController(
            sensitivity=0.5,
            throttle_sensitivity=0.3,
        )
        assert controller.sensitivity == 0.5
        assert controller.throttle_sensitivity == 0.3

    def test_sensitivity_clamping(self):
        """Test that sensitivity is clamped to valid range."""
        # Too low
        controller = KeyboardController(sensitivity=0.01)
        assert controller.sensitivity >= 0.1

        # Too high
        controller = KeyboardController(sensitivity=2.0)
        assert controller.sensitivity <= 1.0

    def test_get_input_no_keys(self):
        """Test get_input with no keys pressed."""
        controller = KeyboardController()
        # Don't start the listener - just test the get_input logic

        control = controller.get_input()
        assert control.x == 0.0
        assert control.y == 0.0
        assert control.z == 0.5  # Neutral throttle
        assert control.r == 0.0
        assert control.has_input is False

    def test_callback_registration(self):
        """Test callback registration."""
        controller = KeyboardController()

        quit_called = False
        toggle_called = False
        emergency_called = False

        controller.on_quit(lambda: None)
        controller.on_toggle_tracking(lambda: None)
        controller.on_emergency_stop(lambda: None)

        # Verify callbacks are registered (internal list has items)
        assert len(controller._on_quit_callbacks) == 1
        assert len(controller._on_toggle_callbacks) == 1
        assert len(controller._on_emergency_callbacks) == 1


class TestKeyboardControllerSimulated:
    """
    Tests for KeyboardController with simulated key presses.

    These tests manipulate internal state directly to avoid
    requiring an actual keyboard/pynput listener.
    """

    def test_simulated_throttle_up(self):
        """Test throttle up key simulation."""
        controller = KeyboardController(throttle_sensitivity=0.3)

        # Simulate W key pressed
        with controller._lock:
            controller._pressed_keys.add("w")

        control = controller.get_input()
        assert control.z > 0.5  # Above neutral
        assert control.z == pytest.approx(0.8, abs=0.01)  # 0.5 + 0.3
        assert control.has_input is True

    def test_simulated_throttle_down(self):
        """Test throttle down key simulation."""
        controller = KeyboardController(throttle_sensitivity=0.3)

        # Simulate S key pressed
        with controller._lock:
            controller._pressed_keys.add("s")

        control = controller.get_input()
        assert control.z < 0.5  # Below neutral
        assert control.z == pytest.approx(0.2, abs=0.01)  # 0.5 - 0.3

    def test_simulated_yaw_left(self):
        """Test yaw left key simulation."""
        controller = KeyboardController(sensitivity=0.7)

        # Simulate A key pressed
        with controller._lock:
            controller._pressed_keys.add("a")

        control = controller.get_input()
        assert control.r < 0  # Negative = counter-clockwise
        assert control.r == pytest.approx(-0.7, abs=0.01)

    def test_simulated_yaw_right(self):
        """Test yaw right key simulation."""
        controller = KeyboardController(sensitivity=0.7)

        # Simulate D key pressed
        with controller._lock:
            controller._pressed_keys.add("d")

        control = controller.get_input()
        assert control.r > 0  # Positive = clockwise
        assert control.r == pytest.approx(0.7, abs=0.01)

    def test_simulated_pitch_forward(self):
        """Test pitch forward (arrow up) key simulation."""
        controller = KeyboardController(sensitivity=0.6)

        # Simulate Up arrow pressed
        with controller._lock:
            controller._pressed_keys.add("up")

        control = controller.get_input()
        assert control.x > 0  # Positive = forward
        assert control.x == pytest.approx(0.6, abs=0.01)

    def test_simulated_pitch_back(self):
        """Test pitch backward (arrow down) key simulation."""
        controller = KeyboardController(sensitivity=0.6)

        # Simulate Down arrow pressed
        with controller._lock:
            controller._pressed_keys.add("down")

        control = controller.get_input()
        assert control.x < 0  # Negative = backward
        assert control.x == pytest.approx(-0.6, abs=0.01)

    def test_simulated_roll_left(self):
        """Test roll left (arrow left) key simulation."""
        controller = KeyboardController(sensitivity=0.5)

        # Simulate Left arrow pressed
        with controller._lock:
            controller._pressed_keys.add("left")

        control = controller.get_input()
        assert control.y < 0  # Negative = left
        assert control.y == pytest.approx(-0.5, abs=0.01)

    def test_simulated_roll_right(self):
        """Test roll right (arrow right) key simulation."""
        controller = KeyboardController(sensitivity=0.5)

        # Simulate Right arrow pressed
        with controller._lock:
            controller._pressed_keys.add("right")

        control = controller.get_input()
        assert control.y > 0  # Positive = right
        assert control.y == pytest.approx(0.5, abs=0.01)

    def test_simulated_multiple_keys(self):
        """Test multiple simultaneous key presses."""
        controller = KeyboardController(sensitivity=0.5, throttle_sensitivity=0.3)

        # Simulate W + D + Up (climb, yaw right, pitch forward)
        with controller._lock:
            controller._pressed_keys.add("w")
            controller._pressed_keys.add("d")
            controller._pressed_keys.add("up")

        control = controller.get_input()
        assert control.z == pytest.approx(0.8, abs=0.01)  # Throttle up
        assert control.r == pytest.approx(0.5, abs=0.01)  # Yaw right
        assert control.x == pytest.approx(0.5, abs=0.01)  # Pitch forward

    def test_simulated_opposing_keys_cancel(self):
        """Test that opposing keys cancel out."""
        controller = KeyboardController(sensitivity=1.0)

        # Simulate W + S (throttle up and down)
        with controller._lock:
            controller._pressed_keys.add("w")
            controller._pressed_keys.add("s")

        control = controller.get_input()
        assert control.z == pytest.approx(0.5, abs=0.01)  # Net zero change

    def test_simulated_emergency_stop(self):
        """Test emergency stop special action."""
        controller = KeyboardController()

        # Simulate emergency stop triggered
        with controller._lock:
            controller._special_action = SpecialAction.EMERGENCY_STOP

        control = controller.get_input()
        assert control.x == 0.0
        assert control.y == 0.0
        assert control.z == 0.5  # Hover throttle
        assert control.r == 0.0
        assert control.special_action == SpecialAction.EMERGENCY_STOP

    def test_value_clamping(self):
        """Test that values are clamped to valid ranges."""
        controller = KeyboardController(sensitivity=1.0, throttle_sensitivity=1.0)

        # Simulate extreme inputs by adding multiple keys that shouldn't stack
        # (they don't actually stack in real use, but test clamping)
        with controller._lock:
            controller._pressed_keys.add("w")

        control = controller.get_input()

        # All values should be within valid ranges
        assert -1.0 <= control.x <= 1.0
        assert -1.0 <= control.y <= 1.0
        assert 0.0 <= control.z <= 1.0
        assert -1.0 <= control.r <= 1.0


# =============================================================================
# Mode Manager Manual Control Tests
# =============================================================================


class TestModeManagerManualControl:
    """Tests for ModeManager manual control extensions."""

    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing."""
        return ModeManager(manual_timeout=1.0)  # Short timeout for tests

    @pytest.mark.asyncio
    async def test_manual_source_exists(self):
        """Test that MANUAL_KEYBOARD source exists."""
        assert ModeSource.MANUAL_KEYBOARD.value == "manual_keyboard"

    @pytest.mark.asyncio
    async def test_manual_priority(self):
        """Test that manual keyboard has higher priority than tracking."""
        assert MODE_PRIORITY[ModeSource.MANUAL_KEYBOARD] > MODE_PRIORITY[ModeSource.HTTP_API]
        assert MODE_PRIORITY[ModeSource.MANUAL_KEYBOARD] > MODE_PRIORITY[ModeSource.PROGRAMMATIC]
        assert MODE_PRIORITY[ModeSource.RC_CHANNEL] > MODE_PRIORITY[ModeSource.MANUAL_KEYBOARD]

    @pytest.mark.asyncio
    async def test_initial_manual_state(self, mode_manager):
        """Test initial manual state is inactive."""
        assert mode_manager.manual_active is False

    @pytest.mark.asyncio
    async def test_set_manual_input(self, mode_manager):
        """Test setting manual input activates manual mode."""
        await mode_manager.set_manual_input()
        assert mode_manager.manual_active is True
        assert mode_manager.state.last_manual_input_time > 0

    @pytest.mark.asyncio
    async def test_manual_overrides_tracking(self, mode_manager):
        """Test that manual control overrides tracking."""
        # Enable tracking
        await mode_manager.enable()
        assert mode_manager.state.enabled is True

        # Activate manual
        await mode_manager.set_manual_input()

        # tracking_enabled should return False due to manual override
        assert mode_manager.tracking_enabled is False
        assert mode_manager.manual_active is True

    @pytest.mark.asyncio
    async def test_clear_manual(self, mode_manager):
        """Test clearing manual mode."""
        # Activate manual
        await mode_manager.set_manual_input()
        assert mode_manager.manual_active is True

        # Clear manual
        cleared = await mode_manager.clear_manual()
        assert cleared is True
        assert mode_manager.manual_active is False

        # Clear again (no change)
        cleared = await mode_manager.clear_manual()
        assert cleared is False

    @pytest.mark.asyncio
    async def test_tracking_resumes_after_manual_clear(self, mode_manager):
        """Test that tracking resumes after manual is cleared."""
        # Enable tracking
        await mode_manager.enable()
        assert mode_manager.tracking_enabled is True

        # Activate manual
        await mode_manager.set_manual_input()
        assert mode_manager.tracking_enabled is False

        # Clear manual
        await mode_manager.clear_manual()
        assert mode_manager.tracking_enabled is True

    @pytest.mark.asyncio
    async def test_manual_timeout(self, mode_manager):
        """Test manual mode timeout."""
        # Start the mode manager to enable timeout monitoring
        await mode_manager.start()

        try:
            # Activate manual
            await mode_manager.set_manual_input()
            assert mode_manager.manual_active is True

            # Wait for timeout (1 second + buffer)
            await asyncio.sleep(1.5)

            # Should have timed out
            assert mode_manager.manual_active is False

        finally:
            await mode_manager.stop()

    @pytest.mark.asyncio
    async def test_manual_input_resets_timeout(self, mode_manager):
        """Test that manual input resets the timeout."""
        await mode_manager.start()

        try:
            # Activate manual
            await mode_manager.set_manual_input()

            # Wait partial timeout
            await asyncio.sleep(0.5)

            # Send another input (resets timeout)
            await mode_manager.set_manual_input()

            # Wait partial timeout again
            await asyncio.sleep(0.5)

            # Should still be active (timeout reset)
            assert mode_manager.manual_active is True

        finally:
            await mode_manager.stop()

    @pytest.mark.asyncio
    async def test_manual_callbacks(self, mode_manager):
        """Test manual start/stop callbacks."""
        start_called = False
        stop_called = False

        def on_start():
            nonlocal start_called
            start_called = True

        def on_stop():
            nonlocal stop_called
            stop_called = True

        mode_manager.on_manual_start(on_start)
        mode_manager.on_manual_stop(on_stop)

        # Activate manual
        await mode_manager.set_manual_input()
        assert start_called is True

        # Clear manual
        await mode_manager.clear_manual()
        assert stop_called is True

    @pytest.mark.asyncio
    async def test_status_includes_manual(self, mode_manager):
        """Test that status includes manual control fields."""
        status = mode_manager.get_status()

        assert "manual_active" in status
        assert "manual_elapsed" in status
        assert "manual_timeout" in status
        assert "tracking_mode_on" in status  # Raw tracking state


# =============================================================================
# Integration Tests
# =============================================================================


class TestManualControlIntegration:
    """Integration tests for manual control with mode manager."""

    @pytest.mark.asyncio
    async def test_keyboard_to_mode_manager_flow(self):
        """Test flow from keyboard input to mode manager."""
        mode_manager = ModeManager(manual_timeout=2.0)
        controller = KeyboardController()

        # Enable tracking
        await mode_manager.enable()
        assert mode_manager.tracking_enabled is True

        # Simulate keyboard input
        with controller._lock:
            controller._pressed_keys.add("w")

        control_input = controller.get_input()
        assert control_input.has_input is True

        # Signal manual input to mode manager
        await mode_manager.set_manual_input()

        # Tracking should be inhibited
        assert mode_manager.tracking_enabled is False
        assert mode_manager.manual_active is True

    @pytest.mark.asyncio
    async def test_full_manual_override_cycle(self):
        """Test complete manual override and release cycle."""
        mode_manager = ModeManager(manual_timeout=1.0)
        await mode_manager.start()

        try:
            # 1. Enable tracking
            await mode_manager.enable()
            assert mode_manager.tracking_enabled is True
            assert mode_manager.manual_active is False

            # 2. Manual takeover
            await mode_manager.set_manual_input()
            assert mode_manager.tracking_enabled is False
            assert mode_manager.manual_active is True

            # 3. Continue manual input
            for _ in range(5):
                await asyncio.sleep(0.3)
                await mode_manager.set_manual_input()
            assert mode_manager.manual_active is True

            # 4. Stop manual input, wait for timeout
            await asyncio.sleep(1.5)
            assert mode_manager.manual_active is False

            # 5. Tracking should resume
            assert mode_manager.tracking_enabled is True

        finally:
            await mode_manager.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

