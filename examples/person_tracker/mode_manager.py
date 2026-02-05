#!/usr/bin/env python3
"""
mode_manager.py - Tracking Mode Enable/Disable Manager

Manages the tracking mode state with multiple control sources:
- RC Channel: Monitor auxiliary channel from remote control
- HTTP API: REST endpoint for testing/simulation
- Programmatic: Direct enable/disable from code

Usage:
    from examples.person_tracker.mode_manager import ModeManager

    mode_manager = ModeManager()
    await mode_manager.start()

    # Check if tracking is enabled
    if mode_manager.tracking_enabled:
        # Send tracking commands
        pass

    # Control via HTTP:
    # curl -X POST http://localhost:8080/enable
    # curl -X POST http://localhost:8080/disable
    # curl -X POST http://localhost:8080/toggle
    # curl http://localhost:8080/status
"""

import asyncio
import json
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


@dataclass
class ModeState:
    """
    Current mode state with metadata.

    Attributes:
        enabled: Whether tracking mode is enabled.
        source: Source that last changed the mode.
        changed_at: Timestamp of last change.
        rc_value: Last RC channel value (if monitoring).
    """

    enabled: bool = False
    source: ModeSource = ModeSource.NONE
    changed_at: float = 0.0
    rc_value: int = 0


class ModeManager:
    """
    Manages tracking mode enable/disable from multiple sources.

    Provides thread-safe access to mode state and async monitoring
    of RC channels and HTTP endpoints.

    Attributes:
        config: Mode manager configuration.
        state: Current mode state.
        tracking_enabled: Shorthand for state.enabled.
    """

    def __init__(self, config: Optional[ModeManagerConfig] = None):
        """
        Initialize the mode manager.

        Args:
            config: Mode manager configuration. Uses defaults if None.
        """
        self.config = config or MODE_MANAGER_CONFIG
        self.state = ModeState()

        self._lock = asyncio.Lock()
        self._running = False
        self._http_server = None
        self._http_runner = None
        self._rc_task = None
        self._drone = None

        # Callbacks for mode changes
        self._on_enable_callbacks: list[Callable] = []
        self._on_disable_callbacks: list[Callable] = []

        logger.debug("ModeManager initialized")

    @property
    def tracking_enabled(self) -> bool:
        """Check if tracking mode is currently enabled."""
        return self.state.enabled

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

        logger.info(
            "ModeManager started (HTTP: %s, RC: %s)",
            "enabled" if self.config.enable_http else "disabled",
            "enabled" if self.config.enable_rc and drone else "disabled",
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

    def get_status(self) -> Dict[str, Any]:
        """
        Get current mode manager status.

        Returns:
            dict: Status information.
        """
        return {
            "tracking_enabled": self.state.enabled,
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
        <head><title>Person Tracker Control</title></head>
        <body>
        <h1>Person Tracker Mode Control</h1>
        <p>Current status: <strong id="status">loading...</strong></p>
        <p>
            <button onclick="fetch('/enable', {method: 'POST'}).then(updateStatus)">Enable</button>
            <button onclick="fetch('/disable', {method: 'POST'}).then(updateStatus)">Disable</button>
            <button onclick="fetch('/toggle', {method: 'POST'}).then(updateStatus)">Toggle</button>
        </p>
        <h2>API Endpoints:</h2>
        <ul>
            <li>GET /status - Get current status</li>
            <li>POST /enable - Enable tracking</li>
            <li>POST /disable - Disable tracking</li>
            <li>POST /toggle - Toggle tracking</li>
        </ul>
        <h2>curl Examples:</h2>
        <pre>
curl http://localhost:8080/status
curl -X POST http://localhost:8080/enable
curl -X POST http://localhost:8080/disable
curl -X POST http://localhost:8080/toggle
        </pre>
        <script>
        function updateStatus() {
            fetch('/status')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('status').innerText =
                        d.tracking_enabled ? 'ENABLED' : 'DISABLED';
                    document.getElementById('status').style.color =
                        d.tracking_enabled ? 'green' : 'red';
                });
        }
        updateStatus();
        setInterval(updateStatus, 1000);
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

                await asyncio.sleep(0.1)  # 10 Hz polling

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

