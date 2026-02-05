#!/usr/bin/env python3
"""
tracker_app.py - Person Following Drone Controller

Main application that integrates the Hailo detection pipeline with
MAVSDK drone control for person following.

Architecture:
    GStreamer Pipeline -> Detection Callback -> Tracking Controller -> MAVSDK -> Drone

Features:
    - Uses Hailo person detection with ByteTracker
    - Smooth, subtle tracking to prevent loss of lock
    - Enable/disable via RC channel, HTTP API, or QGC
    - Distance estimation from bbox size
    - Horizontal tracking only (no altitude changes)

Usage:
    # With camera
    python -m examples.person_tracker.tracker_app --input /dev/video0

    # With video file (for testing)
    python -m examples.person_tracker.tracker_app --input video.mp4

    # Connect to SITL
    python -m examples.person_tracker.tracker_app --input /dev/video0 --tcp-host localhost

Example:
    # Terminal 1: Start SITL
    ./scripts/px4ctl.sh start

    # Terminal 2: Run tracker
    source venv_mavlink/bin/activate
    python examples/person_tracker/tracker_app.py --input /dev/video0

    # Terminal 3: Control tracking
    curl -X POST http://localhost:8080/enable
    curl -X POST http://localhost:8080/disable
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from typing import Optional

# Add parent paths for imports
sys.path.insert(0, sys.path[0] + "/../..")

import gi

gi.require_version("Gst", "1.0")

import hailo
from gi.repository import Gst

from hailo_apps.python.pipeline_apps.detection.detection_pipeline import (
    GStreamerDetectionApp,
)
from hailo_apps.python.core.common.buffer_utils import (
    get_caps_from_pad,
    get_numpy_from_buffer,
)
from hailo_apps.python.core.common.core import get_pipeline_parser
from hailo_apps.python.core.common.hailo_logger import get_logger
from hailo_apps.python.core.gstreamer.gstreamer_app import app_callback_class

from examples.person_tracker.config import (
    TRACKING_CONFIG,
    MODE_MANAGER_CONFIG,
    get_config_summary,
)
from examples.person_tracker.distance_estimator import BoundingBox
from examples.person_tracker.tracking_controller import (
    TrackingController,
    VelocityCommand,
)
from examples.person_tracker.mode_manager import ModeManager, ModeSource

# Logging setup
hailo_logger = get_logger(__name__)
logger = logging.getLogger(__name__)

# Global state for async communication between callback and control loop
_tracker_state = {
    "detection": None,
    "frame_width": 1280,
    "frame_height": 720,
    "frame_count": 0,
    "lock": None,  # Will be set to asyncio.Lock
}


class PersonTrackerCallback(app_callback_class):
    """
    Extended callback class for person tracking.

    Stores detection data for async access by the control loop.

    Attributes:
        tracking_controller: The tracking controller instance.
        mode_manager: Mode manager for enable/disable control.
        best_detection: Currently tracked person detection.
    """

    def __init__(self):
        super().__init__()
        self.best_detection: Optional[BoundingBox] = None
        self.frame_width: int = 1280
        self.frame_height: int = 720
        self.detection_count: int = 0


def person_tracking_callback(element, buffer, user_data: PersonTrackerCallback):
    """
    GStreamer callback for person detection and tracking.

    Extracts person detections from the Hailo pipeline and updates
    the global state for the async control loop.

    Args:
        element: GStreamer element (identity).
        buffer: GStreamer buffer containing detections.
        user_data: PersonTrackerCallback instance.
    """
    if buffer is None:
        hailo_logger.warning("Received None buffer")
        return

    frame_idx = user_data.get_count()

    # Get frame dimensions from pad caps
    pad = element.get_static_pad("src")
    format_type, width, height = get_caps_from_pad(pad)

    if width is not None and height is not None:
        user_data.frame_width = width
        user_data.frame_height = height

    # Get ROI and detections from buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Find best person detection (highest confidence with valid track)
    best_detection = None
    best_confidence = 0.0

    for detection in detections:
        label = detection.get_label()
        confidence = detection.get_confidence()

        if label != "person":
            continue

        if confidence < TRACKING_CONFIG.min_confidence:
            continue

        # Get track ID if available
        track_id = 0
        tracks = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
        if len(tracks) == 1:
            track_id = tracks[0].get_id()

        # Check if this is the best detection
        if confidence > best_confidence:
            best_confidence = confidence

            # Get bbox (normalized coordinates from Hailo)
            bbox = detection.get_bbox()

            # Convert to pixel coordinates
            best_detection = BoundingBox(
                x=bbox.xmin() * user_data.frame_width,
                y=bbox.ymin() * user_data.frame_height,
                width=bbox.width() * user_data.frame_width,
                height=bbox.height() * user_data.frame_height,
                confidence=confidence,
                label=label,
                track_id=track_id,
            )

    # Update user data with best detection
    user_data.best_detection = best_detection
    user_data.detection_count = len([d for d in detections if d.get_label() == "person"])

    # Update global state for async access
    _tracker_state["detection"] = best_detection
    _tracker_state["frame_width"] = user_data.frame_width
    _tracker_state["frame_height"] = user_data.frame_height
    _tracker_state["frame_count"] = frame_idx

    # Log periodically
    if frame_idx % 30 == 0:
        if best_detection:
            hailo_logger.debug(
                "Frame %d: %d person(s), best: track_id=%d, conf=%.2f, bbox=(%.0f,%.0f,%.0f,%.0f)",
                frame_idx,
                user_data.detection_count,
                best_detection.track_id,
                best_detection.confidence,
                best_detection.x,
                best_detection.y,
                best_detection.width,
                best_detection.height,
            )
        else:
            hailo_logger.debug("Frame %d: No person detected", frame_idx)

    return


class PersonTrackerApp(GStreamerDetectionApp):
    """
    Extended GStreamer detection app for person tracking.

    Adds drone control integration via MAVSDK.
    """

    def __init__(self, app_callback, user_data, parser=None):
        """
        Initialize the person tracker app.

        Args:
            app_callback: Detection callback function.
            user_data: PersonTrackerCallback instance.
            parser: Optional argument parser.
        """
        if parser is None:
            parser = get_pipeline_parser()

        # Add tracker-specific arguments
        parser.add_argument(
            "--tcp-host",
            default="localhost",
            help="MAVSDK TCP host for drone connection (default: localhost)",
        )
        parser.add_argument(
            "--tcp-port",
            type=int,
            default=5760,
            help="MAVSDK TCP port for drone connection (default: 5760)",
        )
        parser.add_argument(
            "--http-port",
            type=int,
            default=8080,
            help="HTTP control API port (default: 8080)",
        )
        parser.add_argument(
            "--no-drone",
            action="store_true",
            help="Run without drone connection (detection only)",
        )
        parser.add_argument(
            "--auto-enable",
            action="store_true",
            help="Auto-enable tracking on startup",
        )

        super().__init__(app_callback, user_data, parser)

        # Store drone connection settings
        self.tcp_host = self.options_menu.tcp_host
        self.tcp_port = self.options_menu.tcp_port
        self.http_port = self.options_menu.http_port
        self.no_drone = self.options_menu.no_drone
        self.auto_enable = self.options_menu.auto_enable

        hailo_logger.info("PersonTrackerApp initialized")
        hailo_logger.info("  Drone connection: %s:%d", self.tcp_host, self.tcp_port)
        hailo_logger.info("  HTTP control: port %d", self.http_port)


async def drone_control_loop(
    tcp_host: str,
    tcp_port: int,
    mode_manager: ModeManager,
    tracking_controller: TrackingController,
    no_drone: bool = False,
) -> None:
    """
    Async drone control loop.

    Runs alongside the GStreamer pipeline and sends velocity commands
    based on detection data.

    Args:
        tcp_host: MAVSDK TCP host.
        tcp_port: MAVSDK TCP port.
        mode_manager: Mode manager instance.
        tracking_controller: Tracking controller instance.
        no_drone: If True, skip drone connection (detection only).
    """
    drone = None

    if not no_drone:
        try:
            from mavsdk import System
            from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

            drone = System()
            connection_string = f"tcpout://{tcp_host}:{tcp_port}"

            logger.info("Connecting to drone at %s", connection_string)
            await drone.connect(system_address=connection_string)

            # Wait for connection
            logger.info("Waiting for drone connection...")
            async for state in drone.core.connection_state():
                if state.is_connected:
                    logger.info("Connected to drone!")
                    break
                await asyncio.sleep(0.5)

            # Start mode manager with drone for RC monitoring
            await mode_manager.start(drone=drone)

        except ImportError:
            logger.warning("MAVSDK not installed, running in detection-only mode")
            no_drone = True
        except Exception as e:
            logger.error("Drone connection failed: %s", e)
            no_drone = True

    if no_drone:
        # Start mode manager without drone
        await mode_manager.start(drone=None)
        logger.info("Running in detection-only mode (no drone commands)")

    # Control loop
    control_rate = TRACKING_CONFIG.control_rate_hz
    interval = 1.0 / control_rate
    last_command_time = time.time()
    offboard_started = False

    logger.info("Control loop started at %.1f Hz", control_rate)

    try:
        while True:
            loop_start = time.time()

            # Get current detection from global state
            detection = _tracker_state["detection"]
            frame_width = _tracker_state["frame_width"]
            frame_height = _tracker_state["frame_height"]

            # Compute velocity command
            command = tracking_controller.compute(detection, frame_width, frame_height)

            # Only send commands if tracking is enabled
            if mode_manager.tracking_enabled and not no_drone and drone:
                try:
                    from mavsdk.offboard import VelocityBodyYawspeed

                    # Start offboard mode if not started
                    if not offboard_started:
                        logger.info("Starting offboard mode...")

                        # Set initial setpoint (required before starting offboard)
                        await drone.offboard.set_velocity_body(
                            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
                        )

                        try:
                            await drone.offboard.start()
                            offboard_started = True
                            logger.info("Offboard mode started")
                        except Exception as e:
                            logger.error("Failed to start offboard: %s", e)

                    # Send velocity command
                    # VelocityBodyYawspeed: forward, right, down, yawspeed
                    await drone.offboard.set_velocity_body(
                        VelocityBodyYawspeed(
                            command.forward,
                            command.right,
                            command.down,
                            command.yaw_rate,
                        )
                    )

                    last_command_time = time.time()

                except Exception as e:
                    logger.error("Command send error: %s", e)

            elif not mode_manager.tracking_enabled and offboard_started and drone:
                # Tracking disabled - send hover command
                try:
                    from mavsdk.offboard import VelocityBodyYawspeed

                    await drone.offboard.set_velocity_body(
                        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
                    )
                except Exception as e:
                    logger.error("Hover command error: %s", e)

            # Sleep for remaining interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Control loop cancelled")
    finally:
        # Stop offboard mode
        if offboard_started and drone:
            try:
                logger.info("Stopping offboard mode...")
                await drone.offboard.stop()
            except Exception as e:
                logger.warning("Failed to stop offboard: %s", e)

        await mode_manager.stop()
        logger.info("Control loop stopped")


def run_async_control(
    tcp_host: str,
    tcp_port: int,
    http_port: int,
    no_drone: bool,
    auto_enable: bool,
):
    """
    Run the async control loop in a separate thread.

    Args:
        tcp_host: MAVSDK TCP host.
        tcp_port: MAVSDK TCP port.
        http_port: HTTP API port.
        no_drone: Skip drone connection.
        auto_enable: Auto-enable tracking.
    """
    import threading

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Create controller and mode manager
    tracking_controller = TrackingController()

    config = MODE_MANAGER_CONFIG
    config.http_port = http_port
    mode_manager = ModeManager(config)

    # Auto-enable if requested
    async def setup_and_run():
        if auto_enable:
            await mode_manager.enable(ModeSource.PROGRAMMATIC)

        await drone_control_loop(
            tcp_host=tcp_host,
            tcp_port=tcp_port,
            mode_manager=mode_manager,
            tracking_controller=tracking_controller,
            no_drone=no_drone,
        )

    try:
        loop.run_until_complete(setup_and_run())
    except Exception as e:
        logger.error("Async control error: %s", e)
    finally:
        loop.close()


def main():
    """Main entry point."""
    import threading

    hailo_logger.info("Starting Person Tracker Application")
    print(get_config_summary())

    # Create user data and callback
    user_data = PersonTrackerCallback()

    # Create and run the app
    app = PersonTrackerApp(person_tracking_callback, user_data)

    # Start async control loop in separate thread
    control_thread = threading.Thread(
        target=run_async_control,
        args=(
            app.tcp_host,
            app.tcp_port,
            app.http_port,
            app.no_drone,
            app.auto_enable,
        ),
        daemon=True,
    )
    control_thread.start()

    hailo_logger.info("=" * 50)
    hailo_logger.info("Person Tracker Running")
    hailo_logger.info("=" * 50)
    hailo_logger.info("HTTP Control: http://localhost:%d", app.http_port)
    hailo_logger.info("  curl -X POST http://localhost:%d/enable", app.http_port)
    hailo_logger.info("  curl -X POST http://localhost:%d/disable", app.http_port)
    hailo_logger.info("  curl http://localhost:%d/status", app.http_port)
    hailo_logger.info("=" * 50)

    # Run GStreamer pipeline (blocking)
    app.run()


if __name__ == "__main__":
    main()

