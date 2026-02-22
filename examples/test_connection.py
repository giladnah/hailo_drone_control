import asyncio
from mavsdk import System

async def run():
    # -------------------------------------------------------------------------
    # CONFIGURATION
    # -------------------------------------------------------------------------
    # USB connections (ACM0) technically ignore baud rate, but MAVSDK requires
    # the format "serial://port:baud". We use 115200 as a safe standard.
    connection_string = "serial:///dev/ttyACM0:115200"
    
    drone = System()
    print(f"Initiating connection to: {connection_string}")
    
    # Connect to the drone
    await drone.connect(system_address=connection_string)

    # -------------------------------------------------------------------------
    # 1. WAIT FOR HEARTBEAT
    # -------------------------------------------------------------------------
    print("Waiting for drone heartbeat...")
    
    # This loop blocks until the drone responds
    async for state in drone.core.connection_state():
        if state.is_connected:
            print(f"-- [SUCCESS] Connected to drone!")
            break

    # -------------------------------------------------------------------------
    # 2. VERIFY DATA STREAM (Read-Only)
    # -------------------------------------------------------------------------
    print("-- Fetching system info (this proves bi-directional link)...")
    
    try:
        # Fetch static info (Firmware version)
        info = await drone.info.get_version()
        print(f"   > Firmware: v{info.flight_sw_major}.{info.flight_sw_minor}.{info.flight_sw_patch}")
    except Exception as e:
        print(f"   > Warning: Could not fetch firmware version: {e}")

    print("-- Checking battery status...")
    
    # Fetch dynamic telemetry (Battery) - breaks after first reading
    async for battery in drone.telemetry.battery():
        print(f"   > Voltage: {battery.voltage_v:.2f}V")
        print(f"   > Remaining: {battery.remaining_percent * 100:.0f}%")
        break

    print("-- Test Complete. Connection is healthy.")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
