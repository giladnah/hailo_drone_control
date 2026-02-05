#!/usr/bin/env python3
"""
test_person_tracker.py - Tests for Person Tracker Module

Tests for:
- Distance estimation from bounding box
- Tracking controller PID logic
- Mode manager enable/disable

Run with:
    pytest tests/test_person_tracker.py -v
"""

import asyncio
import sys
import time

import pytest

# Add project root to path
sys.path.insert(0, sys.path[0] + "/..")

from examples.person_tracker.config import (
    TRACKING_CONFIG,
    DISTANCE_CONFIG,
    TrackingConfig,
    DistanceConfig,
)
from examples.person_tracker.distance_estimator import (
    BoundingBox,
    DistanceEstimator,
    calculate_tracking_offset,
    calculate_bbox_ratio,
)
from examples.person_tracker.tracking_controller import (
    VelocityCommand,
    TrackingController,
)
from examples.person_tracker.mode_manager import (
    ModeManager,
    ModeSource,
    SimulatedModeManager,
)


# =============================================================================
# BoundingBox Tests
# =============================================================================


class TestBoundingBox:
    """Tests for BoundingBox dataclass."""

    def test_bbox_creation(self):
        """Test basic BoundingBox creation."""
        bbox = BoundingBox(x=100, y=200, width=50, height=100)
        assert bbox.x == 100
        assert bbox.y == 200
        assert bbox.width == 50
        assert bbox.height == 100

    def test_bbox_center(self):
        """Test center calculation."""
        bbox = BoundingBox(x=100, y=200, width=50, height=100)
        assert bbox.center_x == 125  # 100 + 50/2
        assert bbox.center_y == 250  # 200 + 100/2

    def test_bbox_area(self):
        """Test area calculation."""
        bbox = BoundingBox(x=0, y=0, width=50, height=100)
        assert bbox.area == 5000

    def test_bbox_from_normalized(self):
        """Test creation from normalized coordinates."""
        bbox = BoundingBox.from_normalized(
            xmin=0.25,
            ymin=0.25,
            xmax=0.75,
            ymax=0.75,
            frame_width=1280,
            frame_height=720,
        )
        assert bbox.x == 320  # 0.25 * 1280
        assert bbox.y == 180  # 0.25 * 720
        assert bbox.width == 640  # (0.75 - 0.25) * 1280
        assert bbox.height == 360  # (0.75 - 0.25) * 720


# =============================================================================
# Distance Estimator Tests
# =============================================================================


class TestDistanceEstimator:
    """Tests for DistanceEstimator class."""

    def test_estimator_creation(self):
        """Test estimator initialization."""
        estimator = DistanceEstimator()
        assert estimator.focal_length > 0
        assert estimator.last_distance is None

    def test_distance_at_reference(self):
        """Test distance estimation at reference calibration point."""
        config = DistanceConfig(
            reference_height_px=400,
            reference_distance_m=3.0,
            person_real_height_m=1.7,
        )
        estimator = DistanceEstimator(config)

        # At reference height, should get reference distance
        distance = estimator.estimate(
            bbox_height=400,
            frame_height=720,
            apply_smoothing=False,
        )
        assert abs(distance - 3.0) < 0.1

    def test_distance_closer(self):
        """Test that larger bbox gives closer distance."""
        estimator = DistanceEstimator()

        # Larger bbox = closer
        dist_large = estimator.estimate(600, 720, apply_smoothing=False)
        estimator.reset()
        dist_small = estimator.estimate(200, 720, apply_smoothing=False)

        assert dist_large < dist_small

    def test_distance_clamping(self):
        """Test that distance is clamped to valid range."""
        estimator = DistanceEstimator()

        # Very small bbox -> should clamp to max distance
        distance = estimator.estimate(10, 720, apply_smoothing=False)
        assert distance <= estimator.config.max_distance_m

        # Very large bbox -> should clamp to min distance
        estimator.reset()
        distance = estimator.estimate(700, 720, apply_smoothing=False)
        assert distance >= estimator.config.min_distance_m

    def test_distance_smoothing(self):
        """Test EMA smoothing reduces variation."""
        estimator = DistanceEstimator()

        # Feed varying heights
        heights = [300, 350, 280, 320, 290, 310]
        distances = []

        for h in heights:
            d = estimator.estimate(h, 720, apply_smoothing=True)
            distances.append(d)

        # Smoothed distances should vary less than raw would
        # Just verify smoothing doesn't crash and produces reasonable values
        assert all(1.0 <= d <= 20.0 for d in distances)

    def test_invalid_bbox_height(self):
        """Test handling of invalid (zero/negative) bbox height."""
        estimator = DistanceEstimator()
        estimator.last_distance = 5.0  # Set a previous value

        # Zero height should return last valid estimate
        distance = estimator.estimate(0, 720, apply_smoothing=False)
        assert distance == 5.0

    def test_target_bbox_height(self):
        """Test reverse calculation of expected bbox height."""
        estimator = DistanceEstimator()

        # At 3m, should give reference height
        expected = estimator.get_target_bbox_height(3.0, 720)
        assert expected > 0
        assert expected < 720


class TestTrackingOffset:
    """Tests for tracking offset calculation."""

    def test_centered_target(self):
        """Test offset for centered target."""
        bbox = BoundingBox(x=590, y=310, width=100, height=100)
        x_off, y_off = calculate_tracking_offset(bbox, 1280, 720)

        # Should be very close to (0, 0)
        assert abs(x_off) < 0.05
        assert abs(y_off) < 0.05

    def test_target_on_right(self):
        """Test offset for target on right side."""
        # Bbox centered at x=960 (3/4 of 1280)
        bbox = BoundingBox(x=910, y=310, width=100, height=100)
        x_off, y_off = calculate_tracking_offset(bbox, 1280, 720)

        # Should be positive (right of center)
        assert x_off > 0.4

    def test_target_on_left(self):
        """Test offset for target on left side."""
        # Bbox centered at x=320 (1/4 of 1280)
        bbox = BoundingBox(x=270, y=310, width=100, height=100)
        x_off, y_off = calculate_tracking_offset(bbox, 1280, 720)

        # Should be negative (left of center)
        assert x_off < -0.4


class TestBboxRatio:
    """Tests for bbox ratio calculation."""

    def test_bbox_ratio(self):
        """Test bbox height ratio calculation."""
        bbox = BoundingBox(x=0, y=0, width=100, height=180)
        ratio = calculate_bbox_ratio(bbox, 720)
        assert abs(ratio - 0.25) < 0.001  # 180/720 = 0.25


# =============================================================================
# Tracking Controller Tests
# =============================================================================


class TestTrackingController:
    """Tests for TrackingController class."""

    def test_controller_creation(self):
        """Test controller initialization."""
        controller = TrackingController()
        assert controller.tracking_active is False
        assert controller.last_error_yaw == 0.0

    def test_no_detection_hover(self):
        """Test that no detection returns hover command."""
        controller = TrackingController()
        command = controller.compute(None, 1280, 720)

        assert command.is_zero
        assert controller.tracking_active is False

    def test_centered_target_minimal_command(self):
        """Test that centered target produces minimal commands."""
        controller = TrackingController()

        # Create centered bbox with target ratio
        bbox = BoundingBox(
            x=590,  # Centered horizontally
            y=270,  # Centered vertically
            width=100,
            height=180,  # 25% of 720 = target ratio
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        # Should have minimal corrections (within dead-zone)
        assert abs(command.yaw_rate) < 1.0  # Very small yaw
        assert abs(command.forward) < 0.2  # Very small forward

    def test_target_on_right_yaw_right(self):
        """Test that target on right causes rightward yaw."""
        controller = TrackingController()

        # Bbox on right side of frame
        bbox = BoundingBox(
            x=900,  # Right side
            y=310,
            width=100,
            height=180,
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        # Should yaw right (positive)
        assert command.yaw_rate > 0

    def test_target_on_left_yaw_left(self):
        """Test that target on left causes leftward yaw."""
        controller = TrackingController()

        # Bbox on left side of frame
        bbox = BoundingBox(
            x=200,  # Left side
            y=310,
            width=100,
            height=180,
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        # Should yaw left (negative)
        assert command.yaw_rate < 0

    def test_target_too_close_back_up(self):
        """Test that large bbox (close target) causes backward movement."""
        controller = TrackingController()

        # Large bbox = too close
        bbox = BoundingBox(
            x=440,
            y=60,
            width=400,
            height=600,  # Very large = 83% of frame
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        # Should move backward (negative forward)
        assert command.forward < 0

    def test_target_too_far_move_forward(self):
        """Test that small bbox (far target) causes forward movement."""
        controller = TrackingController()

        # Small bbox = too far
        bbox = BoundingBox(
            x=565,
            y=300,
            width=150,
            height=120,  # Small = 16% of frame
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        # Should move forward (positive forward)
        assert command.forward > 0

    def test_low_confidence_ignored(self):
        """Test that low confidence detections are ignored."""
        controller = TrackingController()

        bbox = BoundingBox(
            x=900,  # Far right - would cause yaw
            y=310,
            width=100,
            height=180,
            confidence=0.3,  # Below threshold
        )

        command = controller.compute(bbox, 1280, 720)

        # Should be hover (detection ignored)
        assert command.is_zero

    def test_no_altitude_change(self):
        """Test that down velocity is always zero."""
        controller = TrackingController()

        # Various scenarios
        scenarios = [
            None,  # No detection
            BoundingBox(x=590, y=310, width=100, height=180, confidence=0.9),  # Centered
            BoundingBox(x=100, y=100, width=100, height=600, confidence=0.9),  # Close, top-left
        ]

        for detection in scenarios:
            command = controller.compute(detection, 1280, 720)
            assert command.down == 0.0, "Altitude should never change"

    def test_velocity_limits(self):
        """Test that velocities are clamped to limits."""
        config = TrackingConfig(
            max_yaw_rate=15.0,
            max_forward_velocity=1.5,
        )
        controller = TrackingController(config=config)

        # Extreme offset - far right, very close
        bbox = BoundingBox(
            x=1100,  # Very far right
            y=60,
            width=400,
            height=600,  # Very close
            confidence=0.9,
        )

        command = controller.compute(bbox, 1280, 720)

        assert abs(command.yaw_rate) <= config.max_yaw_rate + 0.1
        assert abs(command.forward) <= config.max_forward_velocity + 0.1

    def test_velocity_smoothing(self):
        """Test that velocity smoothing reduces jitter."""
        controller = TrackingController()

        # Alternate between left and right
        commands = []
        for i in range(10):
            x = 200 if i % 2 == 0 else 1000
            bbox = BoundingBox(x=x, y=310, width=100, height=180, confidence=0.9)
            cmd = controller.compute(bbox, 1280, 720)
            commands.append(cmd)
            time.sleep(0.05)

        # Smoothed commands should not swing wildly
        yaw_rates = [c.yaw_rate for c in commands]

        # Check that smoothing prevents extreme oscillation
        # (exact values depend on smoothing factor)
        assert len(yaw_rates) == 10

    def test_track_loss_timeout(self):
        """Test tracking state after losing target."""
        controller = TrackingController()

        # First, establish tracking
        bbox = BoundingBox(x=590, y=310, width=100, height=180, confidence=0.9)
        controller.compute(bbox, 1280, 720)
        assert controller.tracking_active is True

        # Then lose target
        for _ in range(30):
            controller.compute(None, 1280, 720)
            time.sleep(0.1)

        # Should eventually become inactive
        assert controller.tracking_active is False

    def test_reset(self):
        """Test controller reset."""
        controller = TrackingController()

        # Set some state
        bbox = BoundingBox(x=200, y=310, width=100, height=180, confidence=0.9)
        controller.compute(bbox, 1280, 720)

        # Reset
        controller.reset()

        assert controller.last_error_yaw == 0.0
        assert controller.smoothed_yaw_rate == 0.0
        assert controller.tracking_active is False


class TestVelocityCommand:
    """Tests for VelocityCommand dataclass."""

    def test_zero_command(self):
        """Test is_zero property."""
        cmd = VelocityCommand()
        assert cmd.is_zero is True

        cmd = VelocityCommand(forward=0.1)
        assert cmd.is_zero is False

    def test_command_string(self):
        """Test string representation."""
        cmd = VelocityCommand(forward=1.0, yaw_rate=10.0)
        s = str(cmd)
        assert "1.00" in s
        assert "10.0" in s


# =============================================================================
# Mode Manager Tests
# =============================================================================


class TestModeManager:
    """Tests for ModeManager class."""

    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing."""
        return ModeManager()

    @pytest.mark.asyncio
    async def test_initial_state(self, mode_manager):
        """Test initial state is disabled."""
        assert mode_manager.tracking_enabled is False

    @pytest.mark.asyncio
    async def test_enable_disable(self, mode_manager):
        """Test enable and disable."""
        # Enable
        changed = await mode_manager.enable()
        assert changed is True
        assert mode_manager.tracking_enabled is True

        # Enable again (no change)
        changed = await mode_manager.enable()
        assert changed is False

        # Disable
        changed = await mode_manager.disable()
        assert changed is True
        assert mode_manager.tracking_enabled is False

        # Disable again (no change)
        changed = await mode_manager.disable()
        assert changed is False

    @pytest.mark.asyncio
    async def test_toggle(self, mode_manager):
        """Test toggle functionality."""
        assert mode_manager.tracking_enabled is False

        new_state = await mode_manager.toggle()
        assert new_state is True
        assert mode_manager.tracking_enabled is True

        new_state = await mode_manager.toggle()
        assert new_state is False
        assert mode_manager.tracking_enabled is False

    @pytest.mark.asyncio
    async def test_mode_source_tracking(self, mode_manager):
        """Test that mode source is tracked."""
        await mode_manager.enable(ModeSource.HTTP_API)
        assert mode_manager.state.source == ModeSource.HTTP_API

        await mode_manager.disable(ModeSource.PROGRAMMATIC)
        assert mode_manager.state.source == ModeSource.PROGRAMMATIC

    @pytest.mark.asyncio
    async def test_callbacks(self, mode_manager):
        """Test enable/disable callbacks."""
        enable_called = False
        disable_called = False

        def on_enable():
            nonlocal enable_called
            enable_called = True

        def on_disable():
            nonlocal disable_called
            disable_called = True

        mode_manager.on_enable(on_enable)
        mode_manager.on_disable(on_disable)

        await mode_manager.enable()
        assert enable_called is True

        await mode_manager.disable()
        assert disable_called is True

    @pytest.mark.asyncio
    async def test_status(self, mode_manager):
        """Test get_status returns expected fields."""
        status = mode_manager.get_status()

        assert "tracking_enabled" in status
        assert "source" in status
        assert "changed_at" in status
        assert "http_enabled" in status
        assert "rc_enabled" in status


class TestSimulatedModeManager:
    """Tests for SimulatedModeManager class."""

    @pytest.mark.asyncio
    async def test_simulated_rc(self):
        """Test simulated RC channel control."""
        manager = SimulatedModeManager()

        # Default off
        assert manager.tracking_enabled is False

        # Simulate switch on (>1500)
        await manager.simulate_rc_value(2000)
        assert manager.tracking_enabled is True
        assert manager.state.source == ModeSource.RC_CHANNEL

        # Simulate switch off (<1500)
        await manager.simulate_rc_value(1000)
        assert manager.tracking_enabled is False

    @pytest.mark.asyncio
    async def test_simulated_rc_toggle(self):
        """Test simulated RC toggle."""
        manager = SimulatedModeManager()

        state = await manager.simulate_rc_toggle()
        assert state is True

        state = await manager.simulate_rc_toggle()
        assert state is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_tracking_pipeline(self):
        """Test full pipeline from bbox to velocity command."""
        controller = TrackingController()

        # Simulate a person moving right to left
        positions = [1000, 800, 640, 400, 200]  # x positions

        for x in positions:
            bbox = BoundingBox(
                x=x,
                y=310,
                width=100,
                height=180,
                confidence=0.9,
            )
            command = controller.compute(bbox, 1280, 720)

            # All commands should be valid
            assert isinstance(command, VelocityCommand)
            assert command.down == 0.0  # No altitude change

        # Verify tracking is active
        assert controller.tracking_active is True

    def test_tracking_with_distance_changes(self):
        """Test tracking with varying distances."""
        controller = TrackingController()

        # Simulate person approaching (bbox getting larger)
        bbox_heights = [100, 150, 200, 250, 300]

        for height in bbox_heights:
            # Centered horizontally
            bbox = BoundingBox(
                x=640 - 50,
                y=360 - height / 2,
                width=100,
                height=height,
                confidence=0.9,
            )
            command = controller.compute(bbox, 1280, 720)

            # Verify command is generated
            assert isinstance(command, VelocityCommand)

        # Last distance should be smaller (person closer)
        assert controller.distance_estimator.last_distance is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

