#!/usr/bin/env python3
"""
distance_estimator.py - Distance Estimation from Bounding Box Size

Estimates the distance to a detected person based on their bounding box size
using the pinhole camera model. Larger bbox = closer, smaller bbox = farther.

The estimation uses:
    distance = (focal_length * real_height) / apparent_height_pixels

Where focal_length is calibrated from a reference measurement.

Usage:
    from examples.person_tracker.distance_estimator import DistanceEstimator

    estimator = DistanceEstimator()
    distance = estimator.estimate(bbox_height=300, frame_height=720)
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from examples.person_tracker.config import DISTANCE_CONFIG, DistanceConfig

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """
    Represents a detection bounding box.

    Attributes:
        x: Left edge of bbox (pixels).
        y: Top edge of bbox (pixels).
        width: Width of bbox (pixels).
        height: Height of bbox (pixels).
        confidence: Detection confidence (0-1).
        label: Detection class label.
        track_id: Tracker-assigned ID (if available).
    """

    x: float
    y: float
    width: float
    height: float
    confidence: float = 0.0
    label: str = "person"
    track_id: int = 0

    @property
    def center_x(self) -> float:
        """Get x-coordinate of bbox center."""
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        """Get y-coordinate of bbox center."""
        return self.y + self.height / 2

    @property
    def area(self) -> float:
        """Get bbox area in pixels."""
        return self.width * self.height

    @classmethod
    def from_hailo_detection(cls, detection, track_id: int = 0) -> "BoundingBox":
        """
        Create BoundingBox from Hailo detection object.

        Args:
            detection: Hailo detection object with get_bbox(), get_label(), get_confidence().
            track_id: Optional tracker ID.

        Returns:
            BoundingBox: Converted bounding box.
        """
        bbox = detection.get_bbox()
        return cls(
            x=bbox.xmin(),
            y=bbox.ymin(),
            width=bbox.width(),
            height=bbox.height(),
            confidence=detection.get_confidence(),
            label=detection.get_label(),
            track_id=track_id,
        )

    @classmethod
    def from_normalized(
        cls,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        frame_width: int,
        frame_height: int,
        confidence: float = 0.0,
        label: str = "person",
        track_id: int = 0,
    ) -> "BoundingBox":
        """
        Create BoundingBox from normalized coordinates (0-1).

        Args:
            xmin: Normalized left edge (0-1).
            ymin: Normalized top edge (0-1).
            xmax: Normalized right edge (0-1).
            ymax: Normalized bottom edge (0-1).
            frame_width: Frame width in pixels.
            frame_height: Frame height in pixels.
            confidence: Detection confidence.
            label: Detection label.
            track_id: Tracker ID.

        Returns:
            BoundingBox: Pixel-space bounding box.
        """
        return cls(
            x=xmin * frame_width,
            y=ymin * frame_height,
            width=(xmax - xmin) * frame_width,
            height=(ymax - ymin) * frame_height,
            confidence=confidence,
            label=label,
            track_id=track_id,
        )


class DistanceEstimator:
    """
    Estimates distance to a person based on their bounding box height.

    Uses the pinhole camera model where apparent size is inversely
    proportional to distance. Includes smoothing to reduce noise.

    Attributes:
        config: Distance estimation configuration.
        last_distance: Most recent smoothed distance estimate.
        focal_length: Calculated focal length for distance estimation.
    """

    def __init__(self, config: Optional[DistanceConfig] = None):
        """
        Initialize the distance estimator.

        Args:
            config: Distance estimation configuration. Uses defaults if None.
        """
        self.config = config or DISTANCE_CONFIG
        self.last_distance: Optional[float] = None
        self._estimate_count = 0

        # Calculate focal length from reference measurement
        # focal_length = (reference_height_px * reference_distance_m) / person_real_height_m
        self.focal_length = (
            self.config.reference_height_px * self.config.reference_distance_m
        ) / self.config.person_real_height_m

        logger.debug(
            "DistanceEstimator initialized with focal_length=%.1f px",
            self.focal_length,
        )

    def estimate(
        self,
        bbox_height: float,
        frame_height: int,
        apply_smoothing: bool = True,
    ) -> float:
        """
        Estimate distance from bounding box height.

        Uses pinhole camera model:
            distance = (focal_length * person_height) / bbox_height_pixels

        Args:
            bbox_height: Height of person bounding box in pixels.
            frame_height: Total frame height in pixels.
            apply_smoothing: Whether to apply EMA smoothing.

        Returns:
            float: Estimated distance in meters.
        """
        if bbox_height <= 0:
            logger.warning("Invalid bbox_height: %.1f, returning last estimate", bbox_height)
            return self.last_distance or self.config.reference_distance_m

        # Calculate raw distance using pinhole model
        raw_distance = (self.focal_length * self.config.person_real_height_m) / bbox_height

        # Clamp to valid range
        clamped_distance = max(
            self.config.min_distance_m,
            min(raw_distance, self.config.max_distance_m),
        )

        # Apply exponential moving average smoothing
        if apply_smoothing and self.last_distance is not None:
            alpha = 1.0 - self.config.distance_smoothing
            smoothed_distance = (
                alpha * clamped_distance + self.config.distance_smoothing * self.last_distance
            )
        else:
            smoothed_distance = clamped_distance

        self.last_distance = smoothed_distance
        self._estimate_count += 1

        logger.debug(
            "Distance estimate: raw=%.2fm, smoothed=%.2fm (bbox_h=%.0fpx)",
            raw_distance,
            smoothed_distance,
            bbox_height,
        )

        return smoothed_distance

    def estimate_from_bbox(
        self,
        bbox: BoundingBox,
        frame_height: int,
        apply_smoothing: bool = True,
    ) -> float:
        """
        Estimate distance from a BoundingBox object.

        Args:
            bbox: BoundingBox with height in pixels.
            frame_height: Total frame height in pixels.
            apply_smoothing: Whether to apply EMA smoothing.

        Returns:
            float: Estimated distance in meters.
        """
        return self.estimate(bbox.height, frame_height, apply_smoothing)

    def estimate_from_ratio(
        self,
        bbox_height_ratio: float,
        frame_height: int = 720,
        apply_smoothing: bool = True,
    ) -> float:
        """
        Estimate distance from bbox height as fraction of frame.

        Args:
            bbox_height_ratio: Bbox height as fraction of frame (0-1).
            frame_height: Frame height for conversion.
            apply_smoothing: Whether to apply EMA smoothing.

        Returns:
            float: Estimated distance in meters.
        """
        bbox_height_px = bbox_height_ratio * frame_height
        return self.estimate(bbox_height_px, frame_height, apply_smoothing)

    def get_target_bbox_height(self, target_distance: float, frame_height: int) -> float:
        """
        Calculate expected bbox height for a given target distance.

        Useful for determining what bbox size corresponds to desired tracking distance.

        Args:
            target_distance: Desired distance in meters.
            frame_height: Frame height in pixels.

        Returns:
            float: Expected bbox height in pixels at target distance.
        """
        if target_distance <= 0:
            return frame_height

        expected_height = (self.focal_length * self.config.person_real_height_m) / target_distance
        return min(expected_height, frame_height)

    def reset(self) -> None:
        """Reset the estimator state (clears smoothing history)."""
        self.last_distance = None
        self._estimate_count = 0
        logger.debug("DistanceEstimator reset")

    def calibrate(
        self,
        known_distance: float,
        measured_bbox_height: float,
        frame_height: int,
    ) -> None:
        """
        Recalibrate the estimator with a known distance measurement.

        Updates the focal length based on a calibration measurement.

        Args:
            known_distance: Actual measured distance in meters.
            measured_bbox_height: Bbox height in pixels at that distance.
            frame_height: Frame height during measurement.
        """
        if known_distance <= 0 or measured_bbox_height <= 0:
            logger.error("Invalid calibration values")
            return

        # Update focal length: focal_length = (bbox_height * distance) / person_height
        self.focal_length = (
            measured_bbox_height * known_distance
        ) / self.config.person_real_height_m

        # Update config reference values
        self.config.reference_height_px = measured_bbox_height
        self.config.reference_distance_m = known_distance
        self.config.focal_length_px = self.focal_length

        logger.info(
            "Calibrated: focal_length=%.1f px (%.0f px at %.1fm)",
            self.focal_length,
            measured_bbox_height,
            known_distance,
        )


def calculate_tracking_offset(
    bbox: BoundingBox,
    frame_width: int,
    frame_height: int,
) -> Tuple[float, float]:
    """
    Calculate normalized offset from frame center.

    Returns values in range [-1, 1] where:
    - (-1, -1) = top-left corner
    - (0, 0) = center
    - (1, 1) = bottom-right corner

    Args:
        bbox: Detection bounding box.
        frame_width: Frame width in pixels.
        frame_height: Frame height in pixels.

    Returns:
        Tuple[float, float]: (horizontal_offset, vertical_offset) in [-1, 1].
    """
    # Calculate center of bbox
    center_x = bbox.center_x
    center_y = bbox.center_y

    # Calculate offset from frame center, normalized to [-1, 1]
    frame_center_x = frame_width / 2
    frame_center_y = frame_height / 2

    # Positive x_offset = target is to the right
    # Positive y_offset = target is below center
    x_offset = (center_x - frame_center_x) / frame_center_x
    y_offset = (center_y - frame_center_y) / frame_center_y

    return (x_offset, y_offset)


def calculate_bbox_ratio(bbox: BoundingBox, frame_height: int) -> float:
    """
    Calculate bbox height as ratio of frame height.

    Args:
        bbox: Detection bounding box.
        frame_height: Frame height in pixels.

    Returns:
        float: Bbox height ratio (0-1).
    """
    return bbox.height / frame_height if frame_height > 0 else 0.0


if __name__ == "__main__":
    # Demo/test the distance estimator
    logging.basicConfig(level=logging.DEBUG)

    estimator = DistanceEstimator()

    print("Distance Estimator Demo")
    print("=" * 40)

    # Test various bbox heights
    test_heights = [600, 400, 300, 200, 150, 100, 50]
    frame_height = 720

    print(f"\nFrame height: {frame_height}px")
    print(f"Reference: {estimator.config.reference_height_px}px at {estimator.config.reference_distance_m}m")
    print(f"Focal length: {estimator.focal_length:.1f}px")
    print()

    for height in test_heights:
        ratio = height / frame_height
        distance = estimator.estimate(height, frame_height, apply_smoothing=False)
        print(f"  Bbox {height:3d}px ({ratio*100:4.1f}%) -> Distance: {distance:5.2f}m")

    # Reset and test smoothing
    print("\nSmoothing test (simulated approach):")
    estimator.reset()

    heights = [100, 120, 140, 160, 180, 200, 220, 240]
    for height in heights:
        distance = estimator.estimate(height, frame_height, apply_smoothing=True)
        print(f"  Bbox {height:3d}px -> Smoothed distance: {distance:5.2f}m")

