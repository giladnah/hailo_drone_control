# -*- coding: utf-8 -*-
"""
Offboard Yaw Wiggle Script (Position Mode).

Holds the drone's current position when offboard mode is activated via RC switch,
then performs a yaw wiggle while maintaining position. Uses MAVSDK PositionNedYaw
for GPS-based position hold.

Safety features:
    - Waits for GPS fix (3D or better) before accepting offboard commands
    - Validates position data is being received before allowing offboard lock
    - Rejects offboard if altitude is too low (below MIN_ALTITUDE_M)
    - Monitors battery level and rejects offboard if too low
    - Falls back to safe behavior if position telemetry fails
    - Graceful shutdown on Ctrl+C / SIGTERM
    - Timeouts on all blocking waits to prevent hangs
    - Yaw normalization to prevent wrapping issues

Usage:
    1. Arm & fly manually (ensure GPS fix)
    2. Fly to at least MIN_ALTITUDE_M above ground
    3. Flip RC switch to Offboard -> Drone holds position & wiggles yaw
    4. Flip RC switch back -> Manual control regained
"""
import asyncio
import math
import signal
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, OffboardError
from mavsdk.telemetry import FixType

# --- CONFIGURATION ---
CONNECTION_STRING = "serial:///dev/ttyACM0:115200"
WIGGLE_AMPLITUDE = 15.0   # Degrees of yaw wiggle (peak-to-peak: ±15°)
WIGGLE_SPEED = 0.8        # Wiggle speed (rad/s multiplier for sin wave)
# Peak yaw rate = AMPLITUDE × SPEED = 12°/s  (very gentle)
# Full cycle period = 2π / SPEED ≈ 7.9 seconds
MIN_ALTITUDE_M = 2.0      # Minimum altitude (meters) to allow offboard lock
MIN_GPS_SATELLITES = 6     # Minimum number of GPS satellites for safe operation
MIN_BATTERY_PERCENT = 0.20  # Minimum battery level (20%) to allow offboard
CONNECTION_TIMEOUT = 30.0   # Seconds to wait for drone connection
GPS_TIMEOUT = 60.0          # Seconds to wait for GPS fix
HEALTH_TIMEOUT = 60.0       # Seconds to wait for health checks
TELEMETRY_INIT_TIMEOUT = 12.0  # Seconds to wait for telemetry initialization

# Reason: GPS fix types that provide altitude (3D). A 2D fix has no altitude
# data, making NED down values unreliable for safe position hold.
REQUIRED_FIX_TYPES = {FixType.FIX_3D, FixType.FIX_DGPS, FixType.RTK_FLOAT, FixType.RTK_FIXED}

# Global shutdown flag for signal handling
_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle shutdown signals (Ctrl+C, SIGTERM)."""
    global _shutdown_requested
    print("\n[SHUTDOWN] Signal received — shutting down gracefully...")
    _shutdown_requested = True


def _normalize_yaw(yaw_deg: float) -> float:
    """
    Normalize yaw angle to [-180, 180] range.

    Args:
        yaw_deg (float): Yaw angle in degrees (any range).

    Returns:
        float: Normalized yaw in [-180, 180].
    """
    return ((yaw_deg + 180.0) % 360.0) - 180.0


async def run():
    """
    Main function: connects to drone, tracks position/yaw, and performs
    yaw wiggle in offboard mode while holding position.

    Includes safety checks for GPS fix, position validity, minimum altitude,
    and battery level. All blocking waits have timeouts.
    """
    global _shutdown_requested

    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # 1. CONNECT (with timeout)
    drone = System()
    print(f"-- Connecting to drone on {CONNECTION_STRING}...")
    await drone.connect(system_address=CONNECTION_STRING)

    print("-- Waiting for connection...")
    connected = False
    conn_start = asyncio.get_running_loop().time()
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("-- [CONNECTED] Drone is ready.")
            connected = True
            break
        if asyncio.get_running_loop().time() - conn_start > CONNECTION_TIMEOUT:
            break
        if _shutdown_requested:
            return

    if not connected:
        print(f"[SAFETY] ERROR: Connection timeout after {CONNECTION_TIMEOUT}s. Exiting.")
        return

    # 2. WAIT FOR GPS FIX (with timeout and fix type validation)
    # Reason: Position mode requires accurate 3D GPS. Without it, NED coordinates
    # can be wrong and the drone could fly to an unintended location.
    print("-- Waiting for GPS fix (3D or better)...")
    gps_ok = False
    gps_start = asyncio.get_running_loop().time()
    async for gps_info in drone.telemetry.gps_info():
        elapsed = asyncio.get_running_loop().time() - gps_start
        num_sats = gps_info.num_satellites
        fix_type = gps_info.fix_type
        print(f"   GPS: {num_sats} satellites, fix type: {fix_type}")

        if num_sats >= MIN_GPS_SATELLITES and fix_type in REQUIRED_FIX_TYPES:
            print(f"-- [GPS OK] {num_sats} satellites, fix: {fix_type} "
                  f"(min: {MIN_GPS_SATELLITES} sats, 3D fix).")
            gps_ok = True
            break

        if elapsed > GPS_TIMEOUT:
            print(f"[SAFETY] ERROR: GPS timeout after {GPS_TIMEOUT}s. Exiting.")
            break

        if _shutdown_requested:
            return

    if not gps_ok:
        print("[SAFETY] ERROR: GPS fix not acquired. Exiting.")
        return

    # 3. WAIT FOR HEALTH CHECKS (with timeout)
    print("-- Waiting for position estimate to be OK...")
    health_ok = False
    health_start = asyncio.get_running_loop().time()
    async for health in drone.telemetry.health():
        elapsed = asyncio.get_running_loop().time() - health_start
        if (health.is_global_position_ok
                and health.is_local_position_ok
                and health.is_home_position_ok):
            print("-- [HEALTH OK] Global, local, and home position estimates are good.")
            health_ok = True
            break

        if elapsed > HEALTH_TIMEOUT:
            print(f"[SAFETY] ERROR: Health check timeout after {HEALTH_TIMEOUT}s.")
            break

        if _shutdown_requested:
            return

    if not health_ok:
        print("[SAFETY] ERROR: Health checks failed. Exiting.")
        return

    # 4. SHARED STATE
    current_yaw = 0.0
    current_north = 0.0
    current_east = 0.0
    current_down = 0.0
    current_battery = 1.0  # Default to full until first reading
    # Reason: This flag prevents locking position at 0,0,0 (ground/home) if
    # telemetry hasn't started or has failed. Without it, offboard could
    # command the drone to dive to ground level.
    position_valid = False

    is_offboard = False
    wiggle_start_time = 0.0
    locked_yaw = 0.0
    locked_north = 0.0
    locked_east = 0.0
    locked_down = 0.0

    # 5. BACKGROUND TELEMETRY
    async def telemetry_loop():
        """Runs telemetry tasks in parallel to track yaw, position, battery, and flight mode."""
        nonlocal current_yaw, current_north, current_east, current_down
        nonlocal current_battery, position_valid
        nonlocal is_offboard, locked_yaw, locked_north, locked_east, locked_down
        nonlocal wiggle_start_time

        # Task A: Track Attitude (Yaw)
        async def att_task():
            """Continuously reads yaw from attitude telemetry."""
            nonlocal current_yaw
            try:
                async for angle in drone.telemetry.attitude_euler():
                    if _shutdown_requested:
                        return
                    if not is_offboard:
                        current_yaw = angle.yaw_deg
                    await asyncio.sleep(0)
            except Exception as e:
                print(f"[SAFETY] WARNING: Attitude telemetry failed: {e}")

        # Task B: Track Position (NED)
        async def position_task():
            """Continuously reads NED position from telemetry."""
            nonlocal current_north, current_east, current_down, position_valid
            try:
                async for pos_vel in drone.telemetry.position_velocity_ned():
                    if _shutdown_requested:
                        return
                    if not is_offboard:
                        current_north = pos_vel.position.north_m
                        current_east = pos_vel.position.east_m
                        current_down = pos_vel.position.down_m
                        # Reason: Mark position as valid only after first real update.
                        if not position_valid:
                            position_valid = True
                            print(f"-- [POSITION OK] First NED reading: "
                                  f"N={current_north:.2f} E={current_east:.2f} "
                                  f"D={current_down:.2f}")
                    await asyncio.sleep(0)
            except Exception as e:
                print(f"[SAFETY] CRITICAL: Position telemetry failed: {e}")
                print("[SAFETY] Offboard lock is DISABLED until position recovers.")
                position_valid = False

        # Task C: Track Battery
        async def battery_task():
            """Continuously monitors battery level."""
            nonlocal current_battery
            try:
                async for battery in drone.telemetry.battery():
                    if _shutdown_requested:
                        return
                    current_battery = battery.remaining_percent
                    await asyncio.sleep(0)
            except Exception as e:
                print(f"[SAFETY] WARNING: Battery telemetry failed: {e}")

        # Task D: Monitor Flight Mode
        async def mode_task():
            """Detects offboard mode changes from RC switch with safety validation."""
            nonlocal is_offboard, locked_yaw, locked_north, locked_east, locked_down
            nonlocal wiggle_start_time
            last_mode_str = ""
            try:
                async for flight_mode in drone.telemetry.flight_mode():
                    if _shutdown_requested:
                        return
                    mode_str = str(flight_mode)

                    # Print mode changes (only when mode actually changes)
                    if mode_str != last_mode_str:
                        print(f"[MODE] Current mode: {mode_str}")
                        last_mode_str = mode_str

                    # Check for OFFBOARD mode (case-insensitive)
                    if "OFFBOARD" in mode_str.upper():
                        if not is_offboard:
                            # --- SAFETY CHECKS BEFORE LOCKING ---
                            # Check 1: Position data must be valid
                            if not position_valid:
                                print("\n[SAFETY] ⚠ OFFBOARD REJECTED: No valid position data!")
                                print("[SAFETY] Position telemetry not received yet.")
                                print("[SAFETY] Switch back to manual immediately!")
                                await asyncio.sleep(0)
                                continue

                            # Check 2: Altitude must be above minimum
                            # In NED frame, down is negative when above home
                            altitude_m = -current_down
                            if altitude_m < MIN_ALTITUDE_M:
                                print(f"\n[SAFETY] ⚠ OFFBOARD REJECTED: Too low!")
                                print(f"[SAFETY] Current altitude: {altitude_m:.1f}m "
                                      f"(minimum: {MIN_ALTITUDE_M:.1f}m)")
                                print("[SAFETY] Fly higher before switching to offboard!")
                                await asyncio.sleep(0)
                                continue

                            # Check 3: Battery must be above minimum
                            if current_battery < MIN_BATTERY_PERCENT:
                                print(f"\n[SAFETY] ⚠ OFFBOARD REJECTED: Battery too low!")
                                print(f"[SAFETY] Battery: {current_battery * 100:.0f}% "
                                      f"(minimum: {MIN_BATTERY_PERCENT * 100:.0f}%)")
                                print("[SAFETY] Land immediately!")
                                await asyncio.sleep(0)
                                continue

                            # All checks passed — LOCK position and yaw
                            locked_yaw = current_yaw
                            locked_north = current_north
                            locked_east = current_east
                            locked_down = current_down

                            print(f"\n>>> OFFBOARD MODE ACTIVE! <<<")
                            print(f"    Locked Position: N={locked_north:.2f} "
                                  f"E={locked_east:.2f} D={locked_down:.2f} "
                                  f"(alt: {-locked_down:.1f}m)")
                            print(f"    Locked Yaw: {locked_yaw:.1f}°")
                            print(f"    Battery: {current_battery * 100:.0f}%")
                            is_offboard = True
                            wiggle_start_time = asyncio.get_running_loop().time()
                    else:
                        if is_offboard:
                            print(f"\n<<< MANUAL CONTROL REGAINED (Mode: {mode_str}). <<<")
                            is_offboard = False

                    await asyncio.sleep(0)
            except Exception as e:
                print(f"[SAFETY] CRITICAL: Flight mode telemetry failed: {e}")
                is_offboard = False

        await asyncio.gather(
            att_task(), position_task(), battery_task(), mode_task()
        )

    # Start telemetry loop
    telemetry_task = asyncio.create_task(telemetry_loop())

    # Wait for telemetry to initialize and get real position data
    print("-- Waiting for telemetry to initialize...")
    await asyncio.sleep(2.0)

    # Verify position data is valid before proceeding
    if not position_valid:
        print("-- Still waiting for valid position data...")
        # Reason: Wait up to TELEMETRY_INIT_TIMEOUT for position data.
        # If it never arrives, something is fundamentally wrong with GPS/telemetry.
        wait_steps = int(TELEMETRY_INIT_TIMEOUT / 0.5)
        for _ in range(wait_steps):
            await asyncio.sleep(0.5)
            if position_valid or _shutdown_requested:
                break
        if not position_valid:
            print(f"[SAFETY] ERROR: No position data received after "
                  f"{TELEMETRY_INIT_TIMEOUT}s!")
            print("[SAFETY] Check GPS connection and antenna. Exiting.")
            telemetry_task.cancel()
            return

    if _shutdown_requested:
        telemetry_task.cancel()
        return

    print(f"-- Current position: N={current_north:.2f} E={current_east:.2f} "
          f"D={current_down:.2f} (alt: {-current_down:.1f}m)")
    print(f"-- Current yaw: {current_yaw:.1f}°")
    print(f"-- Battery: {current_battery * 100:.0f}%")

    # 6. PREPARE FOR BUMPLESS TRANSFER
    # Reason: We send position commands continuously BEFORE switching to offboard
    # so the transition is seamless when the RC switch is flipped.
    print("-- Sending offboard commands continuously (waiting for RC switch)...")
    print("-- NOTE: Offboard mode will be activated by your RC switch, not this script!")

    print("\n" + "=" * 60)
    print(" STATUS: READY (Position Hold + Yaw Wiggle)")
    print(" MODE:   Position (GPS-based)")
    print(f" SAFETY: Min altitude: {MIN_ALTITUDE_M}m | Min GPS sats: {MIN_GPS_SATELLITES}")
    print(f"         Min battery: {MIN_BATTERY_PERCENT * 100:.0f}% | GPS fix: 3D+")
    print(" LOGIC:  Script tracks current NED position and yaw.")
    print("         On offboard switch, holds position & wiggles yaw.")
    print("         Commands sent continuously - ready for RC switch.")
    print(" ACTION: 1. Arm & Fly Manually (above 2m)")
    print("         2. Flip RC Switch to Offboard -> Holds position & Wiggles")
    print("=" * 60 + "\n")

    # 7. CONTROL LOOP
    last_print_time = 0.0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 20  # ~1 second at 20Hz before giving up

    try:
        while not _shutdown_requested:
            if is_offboard:
                # --- ACTIVE MODE (Offboard): Hold position, wiggle yaw ---
                elapsed = asyncio.get_running_loop().time() - wiggle_start_time

                # Wiggle yaw around locked heading
                yaw_offset = math.sin(elapsed * WIGGLE_SPEED) * WIGGLE_AMPLITUDE
                target_yaw = _normalize_yaw(locked_yaw + yaw_offset)

                try:
                    await drone.offboard.set_position_ned(
                        PositionNedYaw(
                            locked_north, locked_east, locked_down, target_yaw
                        )
                    )
                    consecutive_errors = 0
                except OffboardError as e:
                    consecutive_errors += 1
                    if consecutive_errors <= 3:
                        print(f"[SAFETY] Offboard command error: {e}")
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        print("[SAFETY] CRITICAL: Too many offboard errors! "
                              "Stopping offboard commands.")
                        is_offboard = False
                        break
                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors <= 3:
                        print(f"[SAFETY] Command send error: {e}")
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        print("[SAFETY] CRITICAL: Communication lost! Exiting control loop.")
                        break

                # Print status every second
                current_time = asyncio.get_running_loop().time()
                if current_time - last_print_time >= 1.0:
                    print(
                        f"   [OFFBOARD] Pos: N={locked_north:.2f} E={locked_east:.2f} "
                        f"D={locked_down:.2f} (alt: {-locked_down:.1f}m) | "
                        f"Yaw: {target_yaw:.1f}° (locked: {locked_yaw:.1f}°) | "
                        f"Batt: {current_battery * 100:.0f}%"
                    )
                    last_print_time = current_time

            else:
                # --- PASSIVE MODE (Syncing): Send current position to match state ---
                # Reason: Continuous commands ensure no jump when the RC switch flips.
                # Only send if we have valid position data.
                if position_valid:
                    try:
                        await drone.offboard.set_position_ned(
                            PositionNedYaw(
                                current_north, current_east, current_down,
                                _normalize_yaw(current_yaw)
                            )
                        )
                        consecutive_errors = 0
                    except (OffboardError, Exception):
                        # Reason: In passive mode, errors are less critical since
                        # the pilot has manual control. Silently retry.
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            print("[SAFETY] WARNING: Cannot send setpoints. "
                                  "Offboard switch may not work.")
                            consecutive_errors = 0  # Reset to avoid spam

            await asyncio.sleep(0.05)  # 20Hz

    finally:
        print("\n-- Shutting down...")
        telemetry_task.cancel()
        try:
            await telemetry_task
        except asyncio.CancelledError:
            pass
        print("-- Script stopped.")



if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopping script...")
