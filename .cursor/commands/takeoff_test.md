/takeoff_test = Use the run_terminal_cmd tool to execute a quick takeoff test using Python directly in the control container.

## Command
```bash
docker compose exec control timeout 60 python3 -c "
import asyncio
from mavsdk import System

async def test():
    drone = System()
    await drone.connect(system_address='udpin://0.0.0.0:14540')

    async for state in drone.core.connection_state():
        if state.is_connected:
            print('Connected!')
            break

    print('Arming...')
    await drone.action.arm()
    await drone.action.set_takeoff_altitude(5.0)

    print('Taking off...')
    await drone.action.takeoff()
    await asyncio.sleep(10)

    print('Landing...')
    await drone.action.land()
    await asyncio.sleep(8)
    print('Done!')

asyncio.run(test())
"
```

## Context
This command runs a quick takeoff and landing test to verify the simulator is working correctly. The drone will:
1. Connect to the simulator
2. Arm
3. Take off to 5 meters
4. Hover for 10 seconds
5. Land

The simulator must be running first.

