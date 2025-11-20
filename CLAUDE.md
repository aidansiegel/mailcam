# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a **mailcam delivery detection system** running on a Raspberry Pi 5 (hostname: `bigpi`, IP: 10.0.0.3). It monitors a camera feed from Home Assistant (10.0.0.2) to detect delivery vehicles (Amazon, FedEx, UPS, USPS, DHL) using an ONNX object detection model.

## Architecture

### Main Service (systemd)

**mailcam_detector.service** - Delivery detection daemon
   - Pure ONNX Runtime implementation (no Ultralytics dependency)
   - Polls HA snapshot every 2.5s, runs inference
   - Tracks daily carrier detections with 3 AM reset
   - Publishes to MQTT for Home Assistant integration
   - Uses `/home/user/detectenv` virtualenv
   - Script: `detector/mailcam_detector_onnx.py`

### Key Components

**Detector (`detector/mailcam_detector_onnx.py`)**:
- `DailyCarrierTracker` class: Manages per-carrier detection state with daily reset at 3 AM
- ONNX Runtime inference with single-threaded CPU execution
- YOLOv8 output decoding (handles both [1,84,8400] and [1,8400,84] formats)
- NMS, letterboxing, coordinate scaling
- Home Assistant MQTT auto-discovery
- Publishes individual carrier states (yes/no) to `mailcam/carriers/{carrier}`

**Configuration**: `detector/mailcam.yml`
- Model path, labels, inference parameters (conf_min, area_min_frac)
- MQTT broker connection (10.0.0.2:1883, user: delivery)
- Source: HTTP snapshot URL from Home Assistant

**Models**: `/home/user/mailcam/models/`
- `delivery_task.onnx` - Primary YOLOv8 ONNX model (640x640)
  - Source: [CodeProject.AI Custom IPcam Models](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models)
  - Detects: amazon, dhl, fedex, ups, usps
- `delivery.names` - Label mapping file (5 carriers)

## Common Commands

### Service Management
```bash
# Check service status
sudo systemctl status mailcam_detector.service

# View logs
journalctl -u mailcam_detector.service -f
journalctl -u mailcam_detector.service -n 100 --no-pager

# Restart service
sudo systemctl restart mailcam_detector.service
```

### Legacy Restream Service (DISABLED)
The `mailcam_restream.service` provided an MJPEG stream with bounding boxes but was disabled to save CPU (~35%). If you need visual debugging:
```bash
# Re-enable temporarily
sudo systemctl start mailcam_restream.service
# Access stream at http://10.0.0.3:8099/stream.mjpg
# Disable again when done
sudo systemctl stop mailcam_restream.service
```

### Testing and Debugging
```bash
# Test detector manually with static image
cd /home/user/mailcam/detector
source /home/user/detectenv/bin/activate
python mailcam_detector_onnx.py  # Runs continuously

# Monitor MQTT messages
mosquitto_sub -h 10.0.0.2 -t "mailcam/#" -v -u delivery -P mailcam

# Check individual carrier states
mosquitto_sub -h 10.0.0.2 -t "mailcam/carriers/#" -v -u delivery -P mailcam

# Check daily summary
mosquitto_sub -h 10.0.0.2 -t "mailcam/daily_summary" -v -u delivery -P mailcam

# Simulate carrier detection (for testing)
mosquitto_pub -h 10.0.0.2 -t "mailcam/carriers/amazon" -m "yes" -u delivery -P mailcam -r
```

### Python Environment
```bash
# Detector environment
source /home/user/detectenv/bin/activate
pip list  # Check installed packages

# Restream environment
source /home/user/restreamenv/bin/activate
```

## Important Constraints

### DO NOT Use Ultralytics YOLO Wrapper
The detector **must use pure ONNX Runtime**. The old `mailcam_daemon.py` and `mailcam_detector.py` scripts used Ultralytics YOLO wrapper which:
- Triggers auto-update attempts in externally-managed env
- Uses cv2.VideoCapture incorrectly for HTTP snapshots
- Creates unnecessary threads and CPU overhead

The current `mailcam_detector_onnx.py` implements raw ONNX inference with proper preprocessing/postprocessing.

### Image Source
- Source is HTTP snapshot, NOT RTSP stream
- URL: `http://10.0.0.2:8123/local/mailcam/latest.jpg`
- Use `requests` library for fetching, NOT `cv2.VideoCapture`

### ONNX Runtime Configuration
Always configure session for single-threaded operation:
```python
sess_options = ort.SessionOptions()
sess_options.intra_op_num_threads = 1
sess_options.inter_op_num_threads = 1
sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
```

### MQTT Pattern
- Use persistent MQTT connection with `client.loop_start()` once
- Do NOT call `loop_start()/loop_stop()` on every publish
- Publish individual carrier states AND daily summary on every cycle

## Home Assistant Integration

The detector publishes MQTT discovery messages creating these entities:
- `binary_sensor.mailcam_amazon_today` (and fedex, ups, usps, dhl)
- `sensor.mailcam_daily_summary` (contains timestamps in attributes)
- `sensor.mailcam_current_status`
- `sensor.mailcam_detection_details`

Automations in `homeassistant_automations.yaml` provide:
- Instant notifications when each carrier detected
- Daily report at 7:30 PM with all detections and timestamps

## Debugging Tips

### Service Not Detecting
1. Check logs for ONNX inference errors
2. Verify HTTP snapshot URL is accessible: `curl http://10.0.0.2:8123/local/mailcam/latest.jpg -o test.jpg`
3. Check model file exists: `ls -lh /home/user/mailcam/models/delivery_task.onnx`
4. Verify MQTT broker connectivity: `mosquitto_sub -h 10.0.0.2 -t "mailcam/state" -v -u delivery -P mailcam`

### High CPU Usage
- Should be ~40% with single-threaded ONNX Runtime
- Check thread count: `ps -T -p $(pgrep -f mailcam_detector_onnx) | wc -l` (should be ~5)
- Verify `ORT_NUM_THREADS=1` in environment

### Daily Reset Not Working
- Tracker resets at 3:00 AM based on system time
- Check logs around 3 AM for "Daily reset triggered" message
- Reset logic: if `now.hour < 3`, considers it "yesterday"

## Network Topology

- **bigpi** (10.0.0.3): Runs detector and restream services
- **machine** (10.0.0.2): Home Assistant + MQTT broker
- MQTT credentials: user=delivery, password=mailcam
- All MQTT topics under `mailcam/*`
