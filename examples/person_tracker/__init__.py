"""
person_tracker - Person Following Drone Controller

This package implements a person-following drone controller that integrates
the Hailo detection pipeline with MAVSDK for smooth, subtle tracking control.

Main components:
- config: Tunable tracking parameters
- distance_estimator: Estimate distance from bounding box size
- tracking_controller: PID controller for drone movement
- mode_manager: Enable/disable tracking from RC, QGC, or HTTP
- tracker_app: Main application integrating all components

Usage:
    python -m examples.person_tracker.tracker_app --input /dev/video0

For more information, see the README in this directory.
"""

from examples.person_tracker.config import (
    TRACKING_CONFIG,
    DISTANCE_CONFIG,
    MODE_MANAGER_CONFIG,
    TrackingConfig,
    DistanceConfig,
    ModeManagerConfig,
    get_config_summary,
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
    AsyncTrackingController,
)

from examples.person_tracker.mode_manager import (
    ModeSource,
    ModeState,
    ModeManager,
    SimulatedModeManager,
)

__all__ = [
    # Config
    "TRACKING_CONFIG",
    "DISTANCE_CONFIG",
    "MODE_MANAGER_CONFIG",
    "TrackingConfig",
    "DistanceConfig",
    "ModeManagerConfig",
    "get_config_summary",
    # Distance estimation
    "BoundingBox",
    "DistanceEstimator",
    "calculate_tracking_offset",
    "calculate_bbox_ratio",
    # Tracking controller
    "VelocityCommand",
    "TrackingController",
    "AsyncTrackingController",
    # Mode manager
    "ModeSource",
    "ModeState",
    "ModeManager",
    "SimulatedModeManager",
]

