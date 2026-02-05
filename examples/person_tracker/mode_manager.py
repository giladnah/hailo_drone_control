#!/usr/bin/env python3
"""
mode_manager.py - Tracking Mode Enable/Disable Manager

Manages the tracking mode state with multiple control sources:
- RC Channel: Monitor auxiliary channel from remote control
- HTTP API: REST endpoint for testing/simulation
- Programmatic: Direct enable/disable from code
- Manual Keyboard: Manual control via keyboard input (highest software priority)

Control Precedence (highest to lowest):
1. RC Remote (physical) - Hardware safety override
2. Manual Keyboard Control - Software override
3. Autonomous Tracking - Lowest priority

Usage:
    from examples.person_tracker.mode_manager import ModeManager

    mode_manager = ModeManager()
    await mode_manager.start()

    # Check if tracking is enabled (respects manual override)
    if mode_manager.tracking_enabled:
        # Send tracking commands
        pass

    # Check if manual control is active
    if mode_manager.manual_active:
        # Manual control has priority, don't send tracking commands
        pass

    # Control via HTTP:
    # curl -X POST http://localhost:8080/enable
    # curl -X POST http://localhost:8080/disable
    # curl -X POST http://localhost:8080/toggle
    # curl http://localhost:8080/status
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from examples.person_tracker.config import MODE_MANAGER_CONFIG, ModeManagerConfig

logger = logging.getLogger(__name__)


class ModeSource(Enum):
    """Source that triggered mode change."""

    NONE = "none"
    RC_CHANNEL = "rc_channel"
    HTTP_API = "http_api"
    PROGRAMMATIC = "programmatic"
    TIMEOUT = "timeout"
    MANUAL_KEYBOARD = "manual_keyboard"


# Priority levels for mode sources (higher number = higher priority)
MODE_PRIORITY = {
    ModeSource.NONE: 0,
    ModeSource.PROGRAMMATIC: 1,
    ModeSource.HTTP_API: 2,
    ModeSource.TIMEOUT: 2,
    ModeSource.MANUAL_KEYBOARD: 10,  # Manual keyboard has high priority
    ModeSource.RC_CHANNEL: 20,  # RC has highest priority (hardware safety)
}


@dataclass
class ModeState:
    """
    Current mode state with metadata.

    Attributes:
        enabled: Whether tracking mode is enabled.
        source: Source that last changed the mode.
        changed_at: Timestamp of last change.
        rc_value: Last RC channel value (if monitoring).
        manual_active: Whether manual keyboard control is active.
        last_manual_input_time: Timestamp of last manual input.
    """

    enabled: bool = False
    source: ModeSource = ModeSource.NONE
    changed_at: float = 0.0
    rc_value: int = 0
    manual_active: bool = False
    last_manual_input_time: float = 0.0


class ModeManager:
    """
    Manages tracking mode enable/disable from multiple sources.

    Provides thread-safe access to mode state and async monitoring
    of RC channels and HTTP endpoints.

    Control Precedence:
        When manual_active is True, tracking is inhibited regardless of
        the enabled state. Manual control always takes priority over
        autonomous tracking.

    Attributes:
        config: Mode manager configuration.
        state: Current mode state.
        tracking_enabled: True only if tracking enabled AND manual not active.
        manual_active: Whether manual keyboard control is currently active.
    """

    # Default manual control timeout in seconds
    DEFAULT_MANUAL_TIMEOUT = 3.0

    def __init__(
        self,
        config: Optional[ModeManagerConfig] = None,
        manual_timeout: float = DEFAULT_MANUAL_TIMEOUT,
    ):
        """
        Initialize the mode manager.

        Args:
            config: Mode manager configuration. Uses defaults if None.
            manual_timeout: Seconds of no manual input before manual mode expires.
        """
        self.config = config or MODE_MANAGER_CONFIG
        self.state = ModeState()
        self.manual_timeout = manual_timeout

        self._lock = asyncio.Lock()
        self._running = False
        self._http_server = None
        self._http_runner = None
        self._rc_task = None
        self._manual_timeout_task = None
        self._drone = None

        # Callbacks for mode changes
        self._on_enable_callbacks: list[Callable] = []
        self._on_disable_callbacks: list[Callable] = []
        self._on_manual_start_callbacks: list[Callable] = []
        self._on_manual_stop_callbacks: list[Callable] = []

        logger.debug("ModeManager initialized (manual_timeout=%.1fs)", manual_timeout)

    @property
    def tracking_enabled(self) -> bool:
        """
        Check if tracking mode is currently enabled AND allowed.

        Returns False if manual control is active, even if tracking is enabled.
        This ensures manual control always takes priority.

        Returns:
            bool: True if tracking is enabled and manual is not active.
        """
        return self.state.enabled and not self.state.manual_active

    @property
    def manual_active(self) -> bool:
        """
        Check if manual keyboard control is currently active.

        Manual control is active when there has been recent manual input
        within the timeout period.

        Returns:
            bool: True if manual control is active.
        """
        return self.state.manual_active

    async def start(self, drone=None) -> None:
        """
        Start the mode manager services.

        Args:
            drone: MAVSDK System instance for RC channel monitoring.
        """
        if self._running:
            logger.warning("ModeManager already running")
            return

        self._running = True
        self._drone = drone

        # Start HTTP server if enabled
        if self.config.enable_http:
            await self._start_http_server()

        # Start RC channel monitoring if enabled and drone available
        if self.config.enable_rc and drone is not None:
            self._rc_task = asyncio.create_task(self._monitor_rc_channels())

        # Start manual timeout monitoring
        self._manual_timeout_task = asyncio.create_task(self._monitor_manual_timeout())

        logger.info(
            "ModeManager started (HTTP: %s, RC: %s, manual_timeout: %.1fs)",
            "enabled" if self.config.enable_http else "disabled",
            "enabled" if self.config.enable_rc and drone else "disabled",
            self.manual_timeout,
        )

    async def stop(self) -> None:
        """Stop the mode manager services."""
        self._running = False

        # Stop RC monitoring
        if self._rc_task:
            self._rc_task.cancel()
            try:
                await self._rc_task
            except asyncio.CancelledError:
                pass
            self._rc_task = None

        # Stop manual timeout monitoring
        if self._manual_timeout_task:
            self._manual_timeout_task.cancel()
            try:
                await self._manual_timeout_task
            except asyncio.CancelledError:
                pass
            self._manual_timeout_task = None

        # Clear manual state
        self.state.manual_active = False

        # Stop HTTP server
        await self._stop_http_server()

        logger.info("ModeManager stopped")

    async def enable(self, source: ModeSource = ModeSource.PROGRAMMATIC) -> bool:
        """
        Enable tracking mode.

        Args:
            source: Source triggering the enable.

        Returns:
            bool: True if state changed, False if already enabled.
        """
        async with self._lock:
            if self.state.enabled:
                return False

            self.state.enabled = True
            self.state.source = source
            self.state.changed_at = time.time()

            logger.info("Tracking ENABLED (source: %s)", source.value)

            # Fire callbacks
            for callback in self._on_enable_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error("Enable callback error: %s", e)

            return True

    async def disable(self, source: ModeSource = ModeSource.PROGRAMMATIC) -> bool:
        """
        Disable tracking mode.

        Args:
            source: Source triggering the disable.

        Returns:
            bool: True if state changed, False if already disabled.
        """
        async with self._lock:
            if not self.state.enabled:
                return False

            self.state.enabled = False
            self.state.source = source
            self.state.changed_at = time.time()

            logger.info("Tracking DISABLED (source: %s)", source.value)

            # Fire callbacks
            for callback in self._on_disable_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error("Disable callback error: %s", e)

            return True

    async def toggle(self, source: ModeSource = ModeSource.PROGRAMMATIC) -> bool:
        """
        Toggle tracking mode.

        Args:
            source: Source triggering the toggle.

        Returns:
            bool: New state (True = enabled, False = disabled).
        """
        if self.state.enabled:
            await self.disable(source)
        else:
            await self.enable(source)
        return self.state.enabled

    def on_enable(self, callback: Callable) -> None:
        """Register callback for when tracking is enabled."""
        self._on_enable_callbacks.append(callback)

    def on_disable(self, callback: Callable) -> None:
        """Register callback for when tracking is disabled."""
        self._on_disable_callbacks.append(callback)

    def on_manual_start(self, callback: Callable) -> None:
        """Register callback for when manual control becomes active."""
        self._on_manual_start_callbacks.append(callback)

    def on_manual_stop(self, callback: Callable) -> None:
        """Register callback for when manual control becomes inactive."""
        self._on_manual_stop_callbacks.append(callback)

    async def set_manual_input(self) -> None:
        """
        Signal that manual input has been received.

        This activates manual mode (if not already active) and resets
        the manual timeout timer. While manual mode is active, tracking
        is inhibited.

        Call this method each time a manual control input is received
        (e.g., keyboard press, joystick movement).
        """
        current_time = time.time()

        async with self._lock:
            self.state.last_manual_input_time = current_time

            if not self.state.manual_active:
                self.state.manual_active = True
                logger.info("Manual control ACTIVATED (tracking inhibited)")

                # Fire manual start callbacks
                for callback in self._on_manual_start_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback()
                        else:
                            callback()
                    except Exception as e:
                        logger.error("Manual start callback error: %s", e)

    async def clear_manual(self) -> bool:
        """
        Explicitly clear manual control mode.

        This allows tracking to resume if it was enabled.

        Returns:
            bool: True if manual mode was cleared, False if already inactive.
        """
        async with self._lock:
            if not self.state.manual_active:
                return False

            self.state.manual_active = False
            self.state.last_manual_input_time = 0.0
            logger.info("Manual control CLEARED (tracking can resume)")

            # Fire manual stop callbacks
            for callback in self._on_manual_stop_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error("Manual stop callback error: %s", e)

            return True

    async def _monitor_manual_timeout(self) -> None:
        """
        Background task to monitor manual control timeout.

        Automatically clears manual mode if no input received within
        the timeout period.
        """
        try:
            while self._running:
                await asyncio.sleep(0.5)  # Check every 500ms

                if not self.state.manual_active:
                    continue

                # Check if manual input has timed out
                elapsed = time.time() - self.state.last_manual_input_time
                if elapsed > self.manual_timeout:
                    logger.info(
                        "Manual control timeout (%.1fs without input)",
                        elapsed,
                    )
                    await self.clear_manual()

        except asyncio.CancelledError:
            logger.debug("Manual timeout monitoring cancelled")
        except Exception as e:
            logger.error("Manual timeout monitoring error: %s", e)

    def get_status(self) -> Dict[str, Any]:
        """
        Get current mode manager status.

        Returns:
            dict: Status information including manual control state.
        """
        manual_elapsed = 0.0
        if self.state.manual_active and self.state.last_manual_input_time > 0:
            manual_elapsed = time.time() - self.state.last_manual_input_time

        return {
            "tracking_enabled": self.tracking_enabled,  # Respects manual override
            "tracking_mode_on": self.state.enabled,  # Raw tracking state
            "manual_active": self.state.manual_active,
            "manual_elapsed": manual_elapsed,
            "manual_timeout": self.manual_timeout,
            "source": self.state.source.value,
            "changed_at": self.state.changed_at,
            "rc_value": self.state.rc_value,
            "http_enabled": self.config.enable_http,
            "rc_enabled": self.config.enable_rc,
            "http_port": self.config.http_port,
            "rc_channel": self.config.rc_channel + 1,  # 1-indexed for display
        }

    # -------------------------------------------------------------------------
    # HTTP Server
    # -------------------------------------------------------------------------

    async def _start_http_server(self) -> None:
        """Start the HTTP control server."""
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not installed, HTTP control disabled")
            return

        app = web.Application()
        app.router.add_get("/", self._handle_root)
        app.router.add_get("/status", self._handle_status)
        app.router.add_post("/enable", self._handle_enable)
        app.router.add_post("/disable", self._handle_disable)
        app.router.add_post("/toggle", self._handle_toggle)
        app.router.add_post("/clear_manual", self._handle_clear_manual)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()

        site = web.TCPSite(
            self._http_runner,
            self.config.http_host,
            self.config.http_port,
        )
        await site.start()

        logger.info(
            "HTTP control server started on http://%s:%d",
            self.config.http_host,
            self.config.http_port,
        )

    async def _stop_http_server(self) -> None:
        """Stop the HTTP control server."""
        if self._http_runner:
            await self._http_runner.cleanup()
            self._http_runner = None
            logger.info("HTTP control server stopped")

    async def _handle_root(self, request) -> "web.Response":
        """Handle root endpoint with usage info."""
        from aiohttp import web

        html = """
        <html>
        <head>
            <title>Person Tracker Control</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .status-box { padding: 10px; margin: 10px 0; border-radius: 5px; }
                .enabled { background: #d4edda; border: 1px solid #28a745; }
                .disabled { background: #f8d7da; border: 1px solid #dc3545; }
                .manual { background: #fff3cd; border: 1px solid #ffc107; }
                button { padding: 10px 20px; margin: 5px; cursor: pointer; }
                pre { background: #f5f5f5; padding: 10px; overflow-x: auto; }
            </style>
        </head>
        <body>
        <h1>Person Tracker Mode Control</h1>

        <div id="status-container">
            <div id="tracking-status" class="status-box">
                Tracking: <strong id="tracking">loading...</strong>
            </div>
            <div id="manual-status" class="status-box" style="display:none;">
                Manual Control: <strong>ACTIVE</strong>
                (timeout in <span id="manual-timeout">-</span>s)
            </div>
        </div>

        <p>
            <button onclick="fetch('/enable', {method: 'POST'}).then(updateStatus)">Enable Tracking</button>
            <button onclick="fetch('/disable', {method: 'POST'}).then(updateStatus)">Disable Tracking</button>
            <button onclick="fetch('/toggle', {method: 'POST'}).then(updateStatus)">Toggle</button>
            <button onclick="fetch('/clear_manual', {method: 'POST'}).then(updateStatus)">Clear Manual</button>
        </p>

        <h2>API Endpoints:</h2>
        <ul>
            <li>GET /status - Get current status</li>
            <li>POST /enable - Enable tracking</li>
            <li>POST /disable - Disable tracking</li>
            <li>POST /toggle - Toggle tracking</li>
            <li>POST /clear_manual - Clear manual control override</li>
        </ul>

        <h2>curl Examples:</h2>
        <pre>
curl http://localhost:8080/status
curl -X POST http://localhost:8080/enable
curl -X POST http://localhost:8080/disable
curl -X POST http://localhost:8080/toggle
curl -X POST http://localhost:8080/clear_manual
        </pre>

        <script>
        function updateStatus() {
            fetch('/status')
                .then(r => r.json())
                .then(d => {
                    const trackingEl = document.getElementById('tracking');
                    const trackingBox = document.getElementById('tracking-status');
                    const manualBox = document.getElementById('manual-status');
                    const manualTimeout = document.getElementById('manual-timeout');

                    // Update tracking status
                    if (d.manual_active) {
                        trackingEl.innerText = 'INHIBITED (manual active)';
                        trackingBox.className = 'status-box manual';
                        manualBox.style.display = 'block';
                        manualBox.className = 'status-box manual';
                        manualTimeout.innerText = (d.manual_timeout - d.manual_elapsed).toFixed(1);
                    } else if (d.tracking_enabled) {
                        trackingEl.innerText = 'ENABLED';
                        trackingBox.className = 'status-box enabled';
                        manualBox.style.display = 'none';
                    } else {
                        trackingEl.innerText = 'DISABLED';
                        trackingBox.className = 'status-box disabled';
                        manualBox.style.display = 'none';
                    }
                });
        }
        updateStatus();
        setInterval(updateStatus, 500);
        </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def _handle_status(self, request) -> "web.Response":
        """Handle GET /status endpoint."""
        from aiohttp import web

        return web.json_response(self.get_status())

    async def _handle_enable(self, request) -> "web.Response":
        """Handle POST /enable endpoint."""
        from aiohttp import web

        changed = await self.enable(ModeSource.HTTP_API)
        return web.json_response({
            "success": True,
            "changed": changed,
            "tracking_enabled": self.state.enabled,
        })

    async def _handle_disable(self, request) -> "web.Response":
        """Handle POST /disable endpoint."""
        from aiohttp import web

        changed = await self.disable(ModeSource.HTTP_API)
        return web.json_response({
            "success": True,
            "changed": changed,
            "tracking_enabled": self.state.enabled,
        })

    async def _handle_toggle(self, request) -> "web.Response":
        """Handle POST /toggle endpoint."""
        from aiohttp import web

        new_state = await self.toggle(ModeSource.HTTP_API)
        return web.json_response({
            "success": True,
            "tracking_enabled": new_state,
        })

    async def _handle_clear_manual(self, request) -> "web.Response":
        """Handle POST /clear_manual endpoint."""
        from aiohttp import web

        cleared = await self.clear_manual()
        return web.json_response({
            "success": True,
            "cleared": cleared,
            "manual_active": self.state.manual_active,
            "tracking_enabled": self.tracking_enabled,
        })

    # -------------------------------------------------------------------------
    # RC Channel Monitoring
    # -------------------------------------------------------------------------

    async def _monitor_rc_channels(self) -> None:
        """
        Monitor RC channel for tracking mode toggle.

        Reads auxiliary channel value and enables/disables tracking
        based on threshold crossing.
        """
        if self._drone is None:
            logger.warning("No drone instance for RC monitoring")
            return

        logger.info(
            "RC channel monitoring started (channel %d, threshold %d)",
            self.config.rc_channel + 1,
            self.config.rc_threshold,
        )

        last_state = False

        try:
            async for rc_status in self._drone.telemetry.rc_status():
                if not self._running:
                    break

                # Check if RC is connected
                if not rc_status.is_available:
                    continue

                # Note: rc_status provides signal_strength_percent but not individual channels
                # For individual channel values, we need to use raw RC messages
                # This is a simplified implementation - in production, you'd use
                # MAVLink RC_CHANNELS message directly

                # For now, track the RC availability and use HTTP for actual control
                # A full implementation would require pymavlink for raw RC channel access

                # Placeholder: update RC value from MAVLink if available
                # self.state.rc_value = channel_value

                # Note: Use asyncio.sleep(0) to prevent telemetry starvation
                # which can block command execution (see README Troubleshooting)
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.debug("RC monitoring cancelled")
        except Exception as e:
            logger.error("RC monitoring error: %s", e)


class SimulatedModeManager(ModeManager):
    """
    Mode manager with simulated RC channel for testing.

    Allows programmatic simulation of RC channel changes without
    actual hardware.
    """

    def __init__(self, config: Optional[ModeManagerConfig] = None):
        super().__init__(config)
        self._simulated_rc_value = 1000  # Default off

    async def simulate_rc_value(self, value: int) -> None:
        """
        Simulate RC channel value change.

        Args:
            value: Simulated PWM value (1000-2000 typical).
        """
        self._simulated_rc_value = value
        self.state.rc_value = value

        # Check threshold and update state
        if value > self.config.rc_threshold and not self.state.enabled:
            await self.enable(ModeSource.RC_CHANNEL)
        elif value <= self.config.rc_threshold and self.state.enabled:
            await self.disable(ModeSource.RC_CHANNEL)

        logger.debug("Simulated RC value: %d (enabled: %s)", value, self.state.enabled)

    async def simulate_rc_toggle(self) -> bool:
        """
        Simulate RC switch toggle.

        Returns:
            bool: New state.
        """
        if self._simulated_rc_value > self.config.rc_threshold:
            await self.simulate_rc_value(1000)  # Switch off
        else:
            await self.simulate_rc_value(2000)  # Switch on

        return self.state.enabled


if __name__ == "__main__":
    # Demo/test the mode manager
    logging.basicConfig(level=logging.DEBUG)

    async def demo():
        print("Mode Manager Demo")
        print("=" * 50)

        # Create mode manager
        manager = ModeManager()

        # Register callbacks
        manager.on_enable(lambda: print("  -> Callback: Tracking ENABLED"))
        manager.on_disable(lambda: print("  -> Callback: Tracking DISABLED"))

        # Start HTTP server only (no drone for demo)
        await manager.start(drone=None)

        print("\nHTTP Control Server running on http://localhost:8080")
        print("Try these commands in another terminal:")
        print("  curl http://localhost:8080/status")
        print("  curl -X POST http://localhost:8080/enable")
        print("  curl -X POST http://localhost:8080/disable")
        print("  curl -X POST http://localhost:8080/toggle")
        print("\nPress Ctrl+C to stop...")

        # Test programmatic control
        print("\nTesting programmatic control:")
        print(f"  Initial state: {manager.tracking_enabled}")

        await manager.enable()
        print(f"  After enable: {manager.tracking_enabled}")

        await manager.disable()
        print(f"  After disable: {manager.tracking_enabled}")

        await manager.toggle()
        print(f"  After toggle: {manager.tracking_enabled}")

        await manager.toggle()
        print(f"  After toggle: {manager.tracking_enabled}")

        print("\nStatus:", manager.get_status())

        # Keep running for HTTP testing
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await manager.stop()

    asyncio.run(demo())

