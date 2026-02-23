# Screen Recording on Raspberry Pi 5

## Prerequisites

Raspberry Pi OS (Bookworm or later) running Wayland (default).

## Install

```bash
sudo apt install wf-recorder
```

Optionally, install `slurp` for region selection:

```bash
sudo apt install slurp
```

## Usage

### Record full screen

```bash
wf-recorder -f recording.mp4
```

Press `Ctrl+C` to stop.

### Record a selected region

```bash
wf-recorder -g "$(slurp)" -f recording.mp4
```

### Record with hardware-accelerated encoding

```bash
wf-recorder -c h264_v4l2m2m -f recording.mp4
```

### Record with audio

```bash
wf-recorder -f recording.mp4 --audio
```

### Common options

| Flag | Description |
|------|-------------|
| `-f <file>` | Output file path |
| `-g "<x>,<y> <w>x<h>"` | Record a specific region |
| `--audio` | Include audio |
| `-c <codec>` | Video codec (`h264_v4l2m2m` for HW accel) |
| `-r <fps>` | Frame rate (default: 30) |
