#!/usr/bin/env python3
"""
tracking_controller.py - PID Controller for Person Tracking

Implements a smooth, subtle tracking controller that generates velocity
commands to keep a detected person centered in the frame and at the
desired distance.

Key features:
- Dead-zone: No correction when target is near center
- Velocity smoothing: Exponential moving average prevents jerky movement
- Low gains: Gentle corrections to prevent loss of lock
- Rate limiting: Maximum velocities capped for safety

Usage:
    from examples.person_tracker.tracking_controller import TrackingController

    controller = TrackingController()
    velocity = controller.compute(bbox, frame_width, frame_height)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from examples.person_tracker.config import TRACKING_CONFIG, TrackingConfig
from examples.person_tracker.distance_estimator import (
    BoundingBox,
    DistanceEstimator,
    calculate_tracking_offset,
    calculate_bbox_ratio,
)

logger = logging.getLogger(__name__)


@dataclass
class VelocityCommand:
    """
    Velocity command for drone control.

    Uses NED (North-East-Down) body frame for compatibility with MAVSDK.

    Attributes:
        forward: Forward velocity (positive = forward) in m/s.
        right: Right velocity (positive = right) in m/s.
        down: Down velocity (positive = down) in m/s.
        yaw_rate: Yaw rotation rate (positive = clockwise) in deg/s.
        timestamp: Command generation timestamp.
    """

    forward: float = 0.0
    right: float = 0.0
    down: float = 0.0
    yaw_rate: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def is_zero(self) -> bool:
        """Check if this is a zero/hover command."""
        return (
            abs(self.forward) < 0.01
            and abs(self.right) < 0.01
            and abs(self.down) < 0.01
            and abs(self.yaw_rate) < 0.1
        )

    def __str__(self) -> str:
        return (
            f"Velocity(fwd={self.forward:+.2f}m/s, "
            f"right={self.right:+.2f}m/s, "
            f"down={self.down:+.2f}m/s, "
            f"yaw={self.yaw_rate:+.1f}°/s)"
        )


class TrackingController:
    """
    PID controller for person tracking.

    Generates velocity commands to:
    1. Yaw to keep person horizontally centered
    2. Move forward/backward to maintain target distance

    No altitude changes (down velocity always 0).

    Attributes:
        config: Tracking controller configuration.
        distance_estimator: Distance estimation module.
        last_error_yaw: Previous yaw error for derivative term.
        last_error_forward: Previous forward error for derivative term.
        smoothed_yaw_rate: EMA-smoothed yaw rate command.
        smoothed_forward_vel: EMA-smoothed forward velocity command.
    """

    def __init__(
        self,
        config: Optional[TrackingConfig] = None,
        distance_estimator: Optional[DistanceEstimator] = None,
    ):
        """
        Initialize the tracking controller.

        Args:
            config: Tracking configuration. Uses defaults if None.
            distance_estimator: Distance estimator instance. Creates new if None.
        """
        self.config = config or TRACKING_CONFIG
        self.distance_estimator = distance_estimator or DistanceEstimator()

        # PID state
        self.last_error_yaw: float = 0.0
        self.last_error_forward: float = 0.0
        self.last_update_time: float = 0.0

        # Smoothed outputs
        self.smoothed_yaw_rate: float = 0.0
        self.smoothed_forward_vel: float = 0.0
        self.smoothed_lateral_vel: float = 0.0

        # Tracking state
        self.tracking_active: bool = False
        self.last_detection_time: float = 0.0
        self.frames_without_detection: int = 0

        # Statistics
        self._command_count: int = 0

        logger.debug("TrackingController initialized")

    def compute(
        self,
        bbox: Optional[BoundingBox],
        frame_width: int,
        frame_height: int,
    ) -> VelocityCommand:
        """
        Compute velocity command from detection.

        Args:
            bbox: Detected person bounding box (None if no detection).
            frame_width: Frame width in pixels.
            frame_height: Frame height in pixels.

        Returns:
            VelocityCommand: Velocity command for drone control.
        """
        current_time = time.time()

        # Handle no detection
        if bbox is None:
            return self._handle_no_detection(current_time)

        # Check confidence threshold
        if bbox.confidence < self.config.min_confidence:
            logger.debug("Detection below confidence threshold: %.2f", bbox.confidence)
            return self._handle_no_detection(current_time)

        # Valid detection - update tracking state
        self.last_detection_time = current_time
        self.frames_without_detection = 0
        self.tracking_active = True

        # Calculate tracking offset (normalized -1 to 1)
        x_offset, y_offset = calculate_tracking_offset(bbox, frame_width, frame_height)

        # Calculate distance and bbox ratio
        distance = self.distance_estimator.estimate_from_bbox(bbox, frame_height)
        bbox_ratio = calculate_bbox_ratio(bbox, frame_height)

        # Compute control outputs
        yaw_rate = self._compute_yaw(x_offset, current_time)
        forward_vel = self._compute_forward(bbox_ratio, distance, current_time)

        # No altitude changes per requirements
        down_vel = 0.0

        # Apply smoothing
        yaw_rate = self._smooth_yaw(yaw_rate)
        forward_vel = self._smooth_forward(forward_vel)

        self.last_update_time = current_time
        self._command_count += 1

        command = VelocityCommand(
            forward=forward_vel,
            right=0.0,  # No lateral movement (yaw-based tracking)
            down=down_vel,
            yaw_rate=yaw_rate,
            timestamp=current_time,
        )

        if self._command_count % 30 == 0:  # Log every 30 frames
            logger.info(
                "Tracking: offset=(%.2f, %.2f), dist=%.1fm, ratio=%.1f%%, cmd=%s",
                x_offset,
                y_offset,
                distance,
                bbox_ratio * 100,
                command,
            )

        return command

    def _compute_yaw(self, x_offset: float, current_time: float) -> float:
        """
        Compute yaw rate to center target horizontally.

        Uses PD control with dead-zone.

        Args:
            x_offset: Horizontal offset (-1 to 1, positive = right).
            current_time: Current timestamp.

        Returns:
            float: Yaw rate in deg/s (positive = clockwise/right).
        """
        # Apply dead-zone
        if abs(x_offset) < self.config.center_deadzone:
            self.last_error_yaw = 0.0
            return 0.0

        # Error is the offset (we want it to be 0)
        error = x_offset

        # Calculate derivative (rate of change of error)
        dt = current_time - self.last_update_time if self.last_update_time > 0 else 0.1
        dt = max(dt, 0.001)  # Prevent division by zero

        derivative = (error - self.last_error_yaw) / dt
        self.last_error_yaw = error

        # PD control
        # Positive offset (target on right) -> positive yaw (turn right)
        yaw_rate = (
            self.config.p_gain_yaw * error * 100  # Scale to deg/s
            + self.config.d_gain_yaw * derivative * 100
        )

        # Apply rate limiting
        yaw_rate = max(-self.config.max_yaw_rate, min(yaw_rate, self.config.max_yaw_rate))

        return yaw_rate

    def _compute_forward(
        self,
        bbox_ratio: float,
        distance: float,
        current_time: float,
    ) -> float:
        """
        Compute forward velocity to maintain target distance.

        Uses bbox ratio compared to target ratio with PD control.

        Args:
            bbox_ratio: Current bbox height as fraction of frame.
            distance: Estimated distance in meters.
            current_time: Current timestamp.

        Returns:
            float: Forward velocity in m/s (positive = forward).
        """
        # Error = how much bigger/smaller bbox is than target
        # Positive error = bbox too big = too close = need to back up
        ratio_error = bbox_ratio - self.config.target_bbox_ratio

        # Apply dead-zone
        if abs(ratio_error) < self.config.bbox_ratio_deadzone:
            self.last_error_forward = 0.0
            return 0.0

        # Safety check: enforce minimum distance
        if distance < self.config.min_tracking_distance:
            logger.warning("Too close (%.1fm), backing up", distance)
            return -0.5  # Back up slowly

        # Calculate derivative
        dt = current_time - self.last_update_time if self.last_update_time > 0 else 0.1
        dt = max(dt, 0.001)

        derivative = (ratio_error - self.last_error_forward) / dt
        self.last_error_forward = ratio_error

        # PD control
        # Negative error (bbox too small = too far) -> positive velocity (move forward)
        forward_vel = -(
            self.config.p_gain_forward * ratio_error * 10  # Scale factor
            + self.config.d_gain_forward * derivative * 10
        )

        # Apply velocity limiting
        forward_vel = max(
            -self.config.max_forward_velocity,
            min(forward_vel, self.config.max_forward_velocity),
        )

        return forward_vel

    def _smooth_yaw(self, yaw_rate: float) -> float:
        """Apply exponential moving average smoothing to yaw rate."""
        alpha = 1.0 - self.config.velocity_smoothing
        self.smoothed_yaw_rate = (
            alpha * yaw_rate + self.config.velocity_smoothing * self.smoothed_yaw_rate
        )
        return self.smoothed_yaw_rate

    def _smooth_forward(self, forward_vel: float) -> float:
        """Apply exponential moving average smoothing to forward velocity."""
        alpha = 1.0 - self.config.velocity_smoothing
        self.smoothed_forward_vel = (
            alpha * forward_vel + self.config.velocity_smoothing * self.smoothed_forward_vel
        )
        return self.smoothed_forward_vel

    def _handle_no_detection(self, current_time: float) -> VelocityCommand:
        """
        Handle case when no valid detection is present.

        Returns hover command and manages track loss timeout.

        Args:
            current_time: Current timestamp.

        Returns:
            VelocityCommand: Zero velocity (hover) command.
        """
        self.frames_without_detection += 1

        # Check for track loss timeout
        if self.tracking_active and self.last_detection_time > 0:
            time_since_detection = current_time - self.last_detection_time
            if time_since_detection > self.config.track_loss_timeout:
                logger.warning(
                    "Track lost (no detection for %.1fs)",
                    time_since_detection,
                )
                self.tracking_active = False

        # Decay smoothed values toward zero
        self.smoothed_yaw_rate *= 0.9
        self.smoothed_forward_vel *= 0.9

        # Return hover command
        return VelocityCommand(
            forward=0.0,
            right=0.0,
            down=0.0,
            yaw_rate=0.0,
            timestamp=current_time,
        )

    def reset(self) -> None:
        """Reset controller state."""
        self.last_error_yaw = 0.0
        self.last_error_forward = 0.0
        self.last_update_time = 0.0
        self.smoothed_yaw_rate = 0.0
        self.smoothed_forward_vel = 0.0
        self.smoothed_lateral_vel = 0.0
        self.tracking_active = False
        self.last_detection_time = 0.0
        self.frames_without_detection = 0
        self.distance_estimator.reset()
        logger.debug("TrackingController reset")

    def get_status(self) -> dict:
        """
        Get current controller status.

        Returns:
            dict: Controller status information.
        """
        return {
            "tracking_active": self.tracking_active,
            "last_detection_time": self.last_detection_time,
            "frames_without_detection": self.frames_without_detection,
            "smoothed_yaw_rate": self.smoothed_yaw_rate,
            "smoothed_forward_vel": self.smoothed_forward_vel,
            "command_count": self._command_count,
            "last_distance": self.distance_estimator.last_distance,
        }


class AsyncTrackingController:
    """
    Async wrapper for TrackingController with rate-limited control loop.

    Provides an async interface suitable for integration with MAVSDK
    and GStreamer callback-based detection.

    Attributes:
        controller: Underlying TrackingController.
        current_detection: Most recent detection from callback.
        running: Whether the control loop is running.
    """

    def __init__(self, config: Optional[TrackingConfig] = None):
        """
        Initialize async tracking controller.

        Args:
            config: Tracking configuration.
        """
        self.controller = TrackingController(config)
        self.config = self.controller.config

        self.current_detection: Optional[BoundingBox] = None
        self.frame_width: int = 1280
        self.frame_height: int = 720

        self.running: bool = False
        self._lock = asyncio.Lock()
        self._latest_command: VelocityCommand = VelocityCommand()

    async def update_detection(
        self,
        bbox: Optional[BoundingBox],
        frame_width: int,
        frame_height: int,
    ) -> None:
        """
        Update current detection from callback.

        Thread-safe update of detection data.

        Args:
            bbox: New detection bounding box.
            frame_width: Frame width.
            frame_height: Frame height.
        """
        async with self._lock:
            self.current_detection = bbox
            self.frame_width = frame_width
            self.frame_height = frame_height

    async def get_command(self) -> VelocityCommand:
        """
        Compute and return current velocity command.

        Returns:
            VelocityCommand: Latest computed velocity command.
        """
        async with self._lock:
            bbox = self.current_detection
            width = self.frame_width
            height = self.frame_height

        command = self.controller.compute(bbox, width, height)
        self._latest_command = command
        return command

    async def control_loop(
        self,
        command_callback,
        rate_hz: Optional[float] = None,
    ) -> None:
        """
        Run the control loop at specified rate.

        Args:
            command_callback: Async callback to send velocity commands.
            rate_hz: Control loop rate in Hz. Uses config default if None.
        """
        rate = rate_hz or self.config.control_rate_hz
        interval = 1.0 / rate

        self.running = True
        logger.info("Control loop started at %.1f Hz", rate)

        try:
            while self.running:
                loop_start = time.time()

                # Get current command
                command = await self.get_command()

                # Send to drone
                await command_callback(command)

                # Sleep for remaining interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Control loop cancelled")
        except Exception as e:
            logger.error("Control loop error: %s", e)
            raise
        finally:
            self.running = False
            logger.info("Control loop stopped")

    def stop(self) -> None:
        """Stop the control loop."""
        self.running = False

    def reset(self) -> None:
        """Reset controller state."""
        self.controller.reset()
        self.current_detection = None
        self._latest_command = VelocityCommand()


if __name__ == "__main__":
    # Demo/test the tracking controller
    import random

    logging.basicConfig(level=logging.DEBUG)

    controller = TrackingController()

    print("Tracking Controller Demo")
    print("=" * 50)
    print(f"Dead-zone: {controller.config.center_deadzone * 100:.0f}%")
    print(f"Max yaw rate: {controller.config.max_yaw_rate:.1f} deg/s")
    print(f"Max forward velocity: {controller.config.max_forward_velocity:.1f} m/s")
    print()

    frame_width = 1280
    frame_height = 720

    # Simulate tracking scenarios
    scenarios = [
        ("Centered, correct distance", 0.5, 0.5, 0.25),
        ("Target on right", 0.7, 0.5, 0.25),
        ("Target on left", 0.3, 0.5, 0.25),
        ("Target too close", 0.5, 0.5, 0.40),
        ("Target too far", 0.5, 0.5, 0.15),
        ("Target right and far", 0.8, 0.5, 0.12),
    ]

    for name, x_center, y_center, bbox_ratio in scenarios:
        # Create bbox from normalized position
        bbox_height = frame_height * bbox_ratio
        bbox_width = bbox_height * 0.4  # Typical person aspect ratio
        bbox_x = (x_center * frame_width) - bbox_width / 2
        bbox_y = (y_center * frame_height) - bbox_height / 2

        bbox = BoundingBox(
            x=bbox_x,
            y=bbox_y,
            width=bbox_width,
            height=bbox_height,
            confidence=0.85,
        )

        command = controller.compute(bbox, frame_width, frame_height)
        distance = controller.distance_estimator.last_distance

        print(f"\n{name}:")
        print(f"  Position: ({x_center:.1f}, {y_center:.1f}), bbox_ratio: {bbox_ratio*100:.0f}%")
        print(f"  Distance: {distance:.1f}m")
        print(f"  Command: {command}")

    # Test no detection
    print("\n\nNo detection test:")
    for i in range(5):
        command = controller.compute(None, frame_width, frame_height)
        print(f"  Frame {i+1}: {command}")
        time.sleep(0.1)

    print("\n" + "=" * 50)
    print("Status:", controller.get_status())

