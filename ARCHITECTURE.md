# Mailcam Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                           │
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   Camera     │─────▶│  Snapshot    │                    │
│  │   Entity     │      │  /local/...  │                    │
│  └──────────────┘      └──────────────┘                    │
│                              │                              │
│  ┌──────────────┐            │                              │
│  │     MQTT     │◀───────────┼──────────────┐              │
│  │    Broker    │            │              │              │
│  └──────────────┘            │              │              │
│         │                    │              │              │
└─────────┼────────────────────┼──────────────┼──────────────┘
          │                    │              │
          │                    ▼              │
          │         ┌─────────────────────┐  │
          │         │  HTTP Snapshot URL  │  │
          │         └─────────────────────┘  │
          │                    │              │
          │                    │              │
┌─────────┼────────────────────┼──────────────┼──────────────┐
│         │      Detector Host (Raspberry Pi)│              │
│         │                    │              │              │
│         │                    ▼              │              │
│         │         ┌─────────────────────┐  │              │
│         │         │  mailcam_detector   │  │              │
│         │         │      (systemd)      │  │              │
│         │         └─────────────────────┘  │              │
│         │                    │              │              │
│         │         ┌──────────┴───────────┐ │              │
│         │         │  Fetch snapshot      │ │              │
│         │         │  every 2.5s          │ │              │
│         │         └──────────┬───────────┘ │              │
│         │                    │              │              │
│         │         ┌──────────▼───────────┐ │              │
│         │         │  ONNX Runtime        │ │              │
│         │         │  Inference           │ │              │
│         │         │  (delivery_task.onnx)│ │              │
│         │         └──────────┬───────────┘ │              │
│         │                    │              │              │
│         │         ┌──────────▼───────────┐ │              │
│         │         │  DailyCarrierTracker │ │              │
│         │         │  (per-carrier state) │ │              │
│         │         └──────────┬───────────┘ │              │
│         │                    │              │              │
│         └────────────────────┼──────────────┘              │
│                              │                              │
└──────────────────────────────┼──────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  MQTT Publish       │
                    │  mailcam/carriers/* │
                    │  mailcam/state      │
                    └─────────────────────┘
```

## Core Components

### 1. Detector Daemon (`mailcam_detector_onnx.py`)

The main detection service that runs continuously as a systemd service.

**Key Classes:**
- `DailyCarrierTracker`: Manages per-carrier detection state with automatic 3 AM reset
- Main loop: Polls snapshot URL, runs inference, publishes MQTT messages

**Flow:**
1. Load ONNX model and configuration
2. Connect to MQTT broker
3. Publish Home Assistant auto-discovery messages
4. Enter main loop:
   - Fetch snapshot via HTTP
   - Preprocess image (resize, letterbox, normalize)
   - Run ONNX inference
   - Post-process detections (NMS, coordinate scaling)
   - Update daily tracker with detected carriers
   - Publish carrier states to MQTT
   - Sleep until next poll interval

### 2. ONNX Inference Pipeline

**Preprocessing:**
```python
1. Load image from HTTP response
2. Resize to 640x640 with letterboxing (maintain aspect ratio)
3. Convert BGR → RGB
4. Normalize to [0, 1] range
5. Transpose to CHW format (channels-first)
6. Add batch dimension → [1, 3, 640, 640]
```

**Inference:**
```python
1. Run ONNX model with single-threaded CPU execution
2. Get output tensor [1, 84, 8400] or [1, 8400, 84]
3. Transpose if needed to [1, 8400, 84]
```

**Post-processing:**
```python
1. Extract bounding boxes, scores, class IDs
2. Filter by confidence threshold (conf_min)
3. Filter by minimum area (area_min_frac)
4. Apply Non-Maximum Suppression (NMS)
5. Scale coordinates back to original image size
6. Filter to allowed carrier labels only
```

### 3. Daily Carrier Tracker

Manages detection state with these rules:
- Each carrier has a yes/no state for "detected today"
- State persists across detector restarts (via MQTT retained messages)
- Resets all carriers to "no" at 3:00 AM daily
- First detection of a carrier triggers state change to "yes"
- Subsequent detections of same carrier don't re-trigger

**State Machine:**
```
no ─────▶ yes (on first detection of the day)
 ▲         │
 │         │
 └─────────┘ (reset at 3 AM)
```

### 4. MQTT Integration

**Topics:**
- `mailcam/carriers/{carrier}` - Individual carrier state ("yes"/"no"), retained
- `mailcam/state` - Current detection details (JSON)
- `mailcam/details` - Full detection info with bounding boxes
- `mailcam/daily_summary` - Summary of all carriers today

**Home Assistant Auto-Discovery:**
- Publishes discovery configs to `homeassistant/binary_sensor/mailcam_{carrier}_today/config`
- Creates binary sensors for each carrier
- Creates summary sensors for daily status

## Configuration

### mailcam.yml Structure

```yaml
model:
  path: ../models/delivery_task.onnx
  labels: ../models/delivery.names
  allow_labels: [amazon, dhl, fedex, ups, usps]
  imgsz: 640
  conf_min: 0.30           # Confidence threshold
  area_min_frac: 0.0005    # Minimum detection area

mqtt:
  host: 10.0.0.2
  port: 1883
  user: delivery
  password: ********
  state_topic: mailcam/state
  detail_topic: mailcam/details

source:
  kind: image
  url: "http://10.0.0.2:8123/local/mailcam/latest.jpg"
  poll_sec: 2.5            # Polling interval
  timeout_sec: 5.0         # HTTP timeout
```

## Performance Characteristics

### Resource Usage (Raspberry Pi 5)
- CPU: ~40% single-threaded
- Memory: ~200-300 MB
- Network: ~100 KB/s (snapshot fetching)
- Threads: 5 (main + ONNX Runtime workers)

### Timing
- Snapshot fetch: ~50-200 ms
- ONNX inference: ~150-300 ms
- Total cycle: ~200-500 ms
- Poll interval: 2.5 seconds (configurable)

### Optimization Strategies
1. **Single-threaded ONNX**: Prevents CPU oversubscription
2. **HTTP snapshots**: More efficient than RTSP streaming
3. **Retained MQTT messages**: State persists across restarts
4. **Daily reset logic**: Avoids database/file storage needs

## Failure Modes and Recovery

### Network Issues
- HTTP timeout: Skip cycle, retry next poll
- MQTT disconnect: Auto-reconnect with exponential backoff
- Home Assistant offline: Continue operation, queue messages

### Model Issues
- ONNX load failure: Fatal error, service restart via systemd
- Inference error: Log warning, skip frame, continue operation
- Invalid output shape: Auto-detect and transpose

### Resource Constraints
- CPU quota: 70% limit via systemd CPUQuota
- Memory limit: 400MB max via systemd MemoryMax
- Nice level: 5 (lower priority than critical services)

## Extension Points

### Adding New Carriers
1. Retrain model with new carrier class
2. Add carrier to `delivery.names`
3. Add to `allow_labels` in config
4. Home Assistant entities auto-created

### Custom Detection Logic
- Override `DailyCarrierTracker.on_detection()`
- Implement custom filtering in main loop
- Add additional MQTT topics for new data

### Alternative Models
- Replace `delivery_task.onnx` with custom YOLOv8 ONNX model
- Update `delivery.names` with new classes
- Adjust `imgsz` if different model size

## Security Considerations

### Credentials
- MQTT password stored in plain text in config
- Config file excluded from git via .gitignore
- Recommended: Use systemd secrets or environment variables

### Network Exposure
- Detector only makes outbound connections
- No listening ports (except systemd socket)
- All communication over local network

### Model Trust
- ONNX model from trusted source (CodeProject.AI)
- No arbitrary code execution (pure inference)
- Runs as non-root user
