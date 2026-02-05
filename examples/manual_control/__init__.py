#!/usr/bin/env python3
"""
Manual Control Module

Provides keyboard-based manual control for drones using MAVSDK.
Works in both SITL and HITL environments.

Key Components:
    - KeyboardController: Non-blocking keyboard input handler
    - ManualControlApp: Main application integrating with MAVSDK

Usage:
    from examples.manual_control import KeyboardController, ManualControlApp

    # Or run directly:
    # python -m examples.manual_control.manual_control_app --tcp-host localhost
"""

from examples.manual_control.keyboard_controller import (
    KeyboardController,
    ControlInput,
    KeyMapping,
    DEFAULT_KEY_MAPPING,
)

__all__ = [
    "KeyboardController",
    "ControlInput",
    "KeyMapping",
    "DEFAULT_KEY_MAPPING",
]

