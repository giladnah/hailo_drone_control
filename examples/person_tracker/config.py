#!/usr/bin/env python3
"""
config.py - Tracking Configuration Parameters

Centralized configuration for the person-following drone controller.
All parameters are tuned for subtle, stable tracking to prevent
loss of lock and erratic drone behavior.

Usage:
    from examples.person_tracker.config import TRACKING_CONFIG, DISTANCE_CONFIG
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class TrackingConfig:
    """
    Configuration for the tracking controller.

    All gains and limits are intentionally conservative to ensure
    smooth, stable tracking without aggressive maneuvers.

    Attributes:
        center_deadzone: Fraction of frame where no correction is applied.
        max_yaw_rate: Maximum yaw rotation rate (deg/s).
        max_forward_velocity: Maximum forward/backward speed (m/s).
        max_lateral_velocity: Maximum left/right speed (m/s).
        p_gain_yaw: Proportional gain for yaw (horizontal centering).
        p_gain_forward: Proportional gain for forward/backward (distance).
        p_gain_lateral: Proportional gain for lateral movement.
        d_gain_yaw: Derivative gain for yaw (damping).
        d_gain_forward: Derivative gain for forward (damping).
        velocity_smoothing: EMA factor (0-1). Higher = smoother but slower.
        target_bbox_ratio: Target person bbox height as fraction of frame.
        min_confidence: Minimum detection confidence to track.
        track_loss_timeout: Seconds without detection before stopping.
        control_rate_hz: Control loop frequency.
    """

    # Dead-zone: No correction within this fraction of frame center
    center_deadzone: float = 0.10  # 10% of frame width/height

    # Maximum velocity limits (very conservative)
    max_yaw_rate: float = 15.0  # deg/s - gentle turns
    max_forward_velocity: float = 1.5  # m/s - slow approach/retreat
    max_lateral_velocity: float = 1.0  # m/s - slow side movement

    # PID gains - tuned for subtle corrections
    # Yaw (horizontal centering)
    p_gain_yaw: float = 0.08  # Low gain for smooth turns
    d_gain_yaw: float = 0.02  # Damping to prevent oscillation

    # Forward/backward (distance control)
    p_gain_forward: float = 0.05  # Very gentle forward movement
    d_gain_forward: float = 0.01  # Light damping

    # Lateral (not used if only yaw-based centering)
    p_gain_lateral: float = 0.03
    d_gain_lateral: float = 0.01

    # Velocity smoothing (exponential moving average)
    # Higher value = smoother but slower response
    velocity_smoothing: float = 0.85

    # Target tracking parameters
    target_bbox_ratio: float = 0.25  # Person should fill 25% of frame height
    bbox_ratio_deadzone: float = 0.05  # No forward/back within ±5% of target

    # Detection thresholds
    min_confidence: float = 0.5  # Minimum confidence to consider detection
    track_loss_timeout: float = 2.0  # Seconds before declaring track lost

    # Control timing
    control_rate_hz: float = 10.0  # 10 Hz control loop

    # Safety limits
    min_tracking_distance: float = 1.5  # Minimum distance to maintain (m)
    max_tracking_distance: float = 15.0  # Maximum tracking distance (m)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "center_deadzone": self.center_deadzone,
            "max_yaw_rate": self.max_yaw_rate,
            "max_forward_velocity": self.max_forward_velocity,
            "max_lateral_velocity": self.max_lateral_velocity,
            "p_gain_yaw": self.p_gain_yaw,
            "d_gain_yaw": self.d_gain_yaw,
            "p_gain_forward": self.p_gain_forward,
            "d_gain_forward": self.d_gain_forward,
            "p_gain_lateral": self.p_gain_lateral,
            "d_gain_lateral": self.d_gain_lateral,
            "velocity_smoothing": self.velocity_smoothing,
            "target_bbox_ratio": self.target_bbox_ratio,
            "bbox_ratio_deadzone": self.bbox_ratio_deadzone,
            "min_confidence": self.min_confidence,
            "track_loss_timeout": self.track_loss_timeout,
            "control_rate_hz": self.control_rate_hz,
            "min_tracking_distance": self.min_tracking_distance,
            "max_tracking_distance": self.max_tracking_distance,
        }


@dataclass
class DistanceConfig:
    """
    Configuration for distance estimation from bounding box size.

    Uses the pinhole camera model: apparent size is inversely proportional
    to distance. Calibrate reference values for your specific camera setup.

    Attributes:
        reference_height_px: Person height in pixels at reference distance.
        reference_distance_m: Distance at which reference was measured.
        person_real_height_m: Assumed real height of person (meters).
        focal_length_px: Camera focal length in pixels (optional).
        min_distance_m: Minimum estimated distance clamp.
        max_distance_m: Maximum estimated distance clamp.
    """

    # Reference calibration values
    # Measure a person's bbox height at a known distance to calibrate
    reference_height_px: float = 400.0  # Person height in pixels at 3m
    reference_distance_m: float = 3.0  # Distance for reference measurement
    person_real_height_m: float = 1.7  # Average person height (meters)

    # Optional: if focal length is known, use proper pinhole model
    # focal_length = (reference_height_px * reference_distance_m) / person_real_height_m
    focal_length_px: float = 706.0  # Calculated from above

    # Distance clamping
    min_distance_m: float = 1.0  # Never estimate closer than this
    max_distance_m: float = 20.0  # Never estimate farther than this

    # Smoothing for distance estimates
    distance_smoothing: float = 0.7  # EMA factor for distance

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "reference_height_px": self.reference_height_px,
            "reference_distance_m": self.reference_distance_m,
            "person_real_height_m": self.person_real_height_m,
            "focal_length_px": self.focal_length_px,
            "min_distance_m": self.min_distance_m,
            "max_distance_m": self.max_distance_m,
            "distance_smoothing": self.distance_smoothing,
        }


@dataclass
class ModeManagerConfig:
    """
    Configuration for the mode manager (enable/disable tracking).

    Attributes:
        http_port: Port for HTTP control API.
        http_host: Host to bind HTTP server.
        rc_channel: RC channel index for tracking toggle (0-based).
        rc_threshold: RC channel value threshold for "on" state.
        enable_http: Whether to start HTTP control server.
        enable_rc: Whether to monitor RC channel.
    """

    # HTTP control API
    http_port: int = 8080
    http_host: str = "0.0.0.0"
    enable_http: bool = True

    # RC channel monitoring
    rc_channel: int = 6  # Channel 7 (0-indexed)
    rc_threshold: int = 1500  # PWM value threshold (>1500 = ON)
    enable_rc: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "http_port": self.http_port,
            "http_host": self.http_host,
            "enable_http": self.enable_http,
            "rc_channel": self.rc_channel,
            "rc_threshold": self.rc_threshold,
            "enable_rc": self.enable_rc,
        }


# Default configuration instances
TRACKING_CONFIG = TrackingConfig()
DISTANCE_CONFIG = DistanceConfig()
MODE_MANAGER_CONFIG = ModeManagerConfig()


def get_config_summary() -> str:
    """
    Get a human-readable summary of current configuration.

    Returns:
        str: Formatted configuration summary.
    """
    lines = [
        "=" * 50,
        "Person Tracker Configuration",
        "=" * 50,
        "",
        "Tracking Controller:",
        f"  Dead-zone: {TRACKING_CONFIG.center_deadzone * 100:.0f}% of frame",
        f"  Max yaw rate: {TRACKING_CONFIG.max_yaw_rate:.1f} deg/s",
        f"  Max forward velocity: {TRACKING_CONFIG.max_forward_velocity:.1f} m/s",
        f"  P-gain (yaw): {TRACKING_CONFIG.p_gain_yaw:.3f}",
        f"  P-gain (forward): {TRACKING_CONFIG.p_gain_forward:.3f}",
        f"  Velocity smoothing: {TRACKING_CONFIG.velocity_smoothing:.2f}",
        f"  Target bbox ratio: {TRACKING_CONFIG.target_bbox_ratio * 100:.0f}%",
        "",
        "Distance Estimation:",
        f"  Reference: {DISTANCE_CONFIG.reference_height_px:.0f}px at {DISTANCE_CONFIG.reference_distance_m:.1f}m",
        f"  Distance range: {DISTANCE_CONFIG.min_distance_m:.1f}m - {DISTANCE_CONFIG.max_distance_m:.1f}m",
        "",
        "Mode Manager:",
        f"  HTTP API: {'enabled' if MODE_MANAGER_CONFIG.enable_http else 'disabled'} (port {MODE_MANAGER_CONFIG.http_port})",
        f"  RC channel: {'enabled' if MODE_MANAGER_CONFIG.enable_rc else 'disabled'} (ch {MODE_MANAGER_CONFIG.rc_channel + 1})",
        "=" * 50,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Print configuration when run directly
    print(get_config_summary())

