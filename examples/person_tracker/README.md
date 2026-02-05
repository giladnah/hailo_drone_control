# Person Tracking Drone Controller

A person-following drone controller that integrates the Hailo detection pipeline with MAVSDK for smooth, subtle tracking control.

## Features

- **Person Detection**: Uses Hailo AI accelerator for real-time person detection
- **Smooth Tracking**: PID controller with dead-zone and velocity smoothing for stable tracking
- **Distance Estimation**: Estimates distance from bounding box size
- **Multiple Control Sources**: Enable/disable tracking via RC channel, HTTP API, or QGroundControl
- **Safety First**: No altitude changes, velocity limiting, and track loss timeout

## Architecture

```
Camera → Hailo Detection → Tracking Callback → PID Controller → MAVSDK → Drone
                                                     ↑
                                          Mode Manager (HTTP/RC)
```

## Quick Start

### 1. Start SITL Simulation

```bash
# Terminal 1: Start PX4 SITL with QGroundControl
./scripts/px4ctl.sh start
```

### 2. Run the Person Tracker

```bash
# Terminal 2: Activate virtual environment and run tracker
source venv_mavlink/bin/activate
python examples/person_tracker/tracker_app.py --input /dev/video0
```

### 3. Control Tracking Mode

```bash
# Terminal 3: Enable/disable tracking via HTTP
curl -X POST http://localhost:8080/enable   # Start tracking
curl -X POST http://localhost:8080/disable  # Stop tracking
curl -X POST http://localhost:8080/toggle   # Toggle state
curl http://localhost:8080/status           # Check status
```

## Command Line Options

```bash
python examples/person_tracker/tracker_app.py [OPTIONS]

Options:
  --input PATH          Video source (camera device, video file, or RTSP URL)
  --tcp-host HOST       MAVSDK TCP host (default: localhost)
  --tcp-port PORT       MAVSDK TCP port (default: 5760)
  --http-port PORT      HTTP control API port (default: 8080)
  --no-drone           Run detection only (no drone connection)
  --auto-enable        Automatically enable tracking on startup
  --show-fps           Display FPS overlay
  --use-frame          Extract frames for OpenCV processing
```

## Enabling/Disabling Tracking

### Method 1: HTTP API (Recommended for Testing)

The tracker exposes a REST API on port 8080:

| Endpoint   | Method | Description               |
| ---------- | ------ | ------------------------- |
| `/`        | GET    | Web UI with buttons       |
| `/status`  | GET    | Get current status (JSON) |
| `/enable`  | POST   | Enable tracking           |
| `/disable` | POST   | Disable tracking          |
| `/toggle`  | POST   | Toggle tracking state     |

**Examples:**

```bash
# Check status
curl http://localhost:8080/status
# {"tracking_enabled": false, "source": "none", ...}

# Enable tracking
curl -X POST http://localhost:8080/enable
# {"success": true, "changed": true, "tracking_enabled": true}

# Disable tracking
curl -X POST http://localhost:8080/disable
# {"success": true, "changed": true, "tracking_enabled": false}
```

Or open http://localhost:8080 in a browser for a simple web UI.

### Method 2: RC Remote Control (Production)

Configure an auxiliary channel (7 or 8) on your RC transmitter as a two-position switch:

1. Set switch position LOW (< 1500 PWM) = Tracking OFF
2. Set switch position HIGH (> 1500 PWM) = Tracking ON

The tracker monitors RC channels via MAVLink and toggles tracking automatically.

**Note:** RC monitoring requires an active MAVLink connection with RC telemetry.

### Method 3: QGroundControl

While QGC cannot directly toggle tracking mode, you can:

1. Use QGC to switch between flight modes (Manual/Guided/etc.)
2. Switch to GUIDED mode to allow offboard control
3. Use the HTTP API or RC switch to enable tracking

**Important QGC Settings:**

Disable **Application Settings > General > Miscellaneous > Stream GCS Position** to avoid conflicts with the tracker's position commands.

## Manual Control of Simulated Drone

### Using QGroundControl

1. QGC connects automatically to SITL via UDP 14550
2. Use the Fly view to manually control the drone
3. The tracker only sends commands when tracking is enabled
4. Switch tracking OFF to regain full manual control

### Priority System

When tracking is disabled, the tracker sends zero velocity commands (hover). This allows QGC or RC to take control. When tracking is enabled, the tracker sends velocity commands based on person detection.

## Testing Without Hardware

### Detection-Only Mode

Run without drone connection to test detection:

```bash
python examples/person_tracker/tracker_app.py \
    --input /dev/video0 \
    --no-drone
```

### With Video File

Test with a pre-recorded video:

```bash
python examples/person_tracker/tracker_app.py \
    --input /path/to/video_with_person.mp4 \
    --tcp-host localhost
```

### Simulating RC Control

Use the HTTP API to simulate RC switch behavior:

```bash
# Simulate RC switch ON
curl -X POST http://localhost:8080/enable

# Simulate RC switch OFF
curl -X POST http://localhost:8080/disable
```

## Configuration

Tracking parameters are defined in `config.py`:

```python
TRACKING_CONFIG = {
    "center_deadzone": 0.10,      # 10% of frame - no movement
    "max_yaw_rate": 15.0,         # deg/s - gentle turns
    "max_forward_velocity": 1.5,  # m/s - slow approach
    "p_gain_yaw": 0.08,           # Low proportional gain
    "p_gain_forward": 0.05,       # Very gentle forward movement
    "target_bbox_ratio": 0.25,    # Target person fills 25% of frame height
    "velocity_smoothing": 0.85,   # Exponential smoothing factor
}
```

### Tuning Tips

- **Increase dead-zone** if tracking is jittery when centered
- **Decrease P-gains** for smoother but slower tracking
- **Increase velocity_smoothing** (closer to 1.0) for slower response
- **Adjust target_bbox_ratio** to change following distance

## Safety Features

| Feature             | Description                                  |
| ------------------- | -------------------------------------------- |
| No altitude changes | Down velocity is always 0                    |
| Velocity limits     | Max 15°/s yaw, 1.5 m/s forward               |
| Track loss timeout  | Hovers after 2s without detection            |
| Dead-zone           | No movement when target is centered          |
| Ctrl+C              | Triggers immediate land command              |
| Geofence            | PX4 geofence remains active (500m, 120m alt) |

## Troubleshooting

### "Failed to start offboard mode"

- Ensure the drone is armed and in a mode that allows offboard control
- Check that GPS lock is acquired (for SITL, wait ~30s after start)
- Verify MAVLink connection with `curl http://localhost:8080/status`

### "No person detected"

- Check that the camera is working: `--input /dev/video0`
- Verify Hailo is initialized (check logs for "Hailo Detection App")
- Try with a video file containing people

### Tracking is jittery

- Increase `velocity_smoothing` in config (e.g., 0.90)
- Increase `center_deadzone` (e.g., 0.15)
- Decrease `p_gain_yaw` and `p_gain_forward`

### QGC conflicts with tracker

- Disable "Stream GCS Position" in QGC settings
- Ensure only one application is sending position commands

## Module Structure

```
examples/person_tracker/
├── __init__.py              # Package exports
├── config.py                # Configuration parameters
├── distance_estimator.py    # Bbox to distance conversion
├── tracking_controller.py   # PID controller for tracking
├── mode_manager.py          # Enable/disable mode control
├── tracker_app.py           # Main application
└── README.md                # This file
```

## Running Tests

```bash
pytest tests/test_person_tracker.py -v
```

## Dependencies

- MAVSDK-Python
- Hailo Apps (detection pipeline)
- aiohttp (for HTTP API)
- GStreamer 1.0

Install with:

```bash
pip install mavsdk aiohttp
```

## License

See project root LICENSE file.

