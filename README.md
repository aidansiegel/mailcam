# Mailcam Delivery Detector

AI-powered delivery vehicle detection system for Home Assistant. Monitors a camera feed to detect delivery vehicles (Amazon, FedEx, UPS, USPS, DHL) using an ONNX object detection model, with daily tracking and instant notifications.

## Features

- 🚚 **Multi-carrier detection**: Amazon, FedEx, UPS, USPS, DHL
- 📅 **Daily tracking**: Individual yes/no state for each carrier, resets at 3 AM
- 🔔 **Instant notifications**: Get alerted when each carrier is detected
- 📊 **Daily reports**: 7:30 PM summary of all deliveries with timestamps
- 🏠 **Home Assistant integration**: Auto-discovered MQTT sensors
- ⚡ **Low resource usage**: ~40% CPU on Raspberry Pi 5, single-threaded ONNX Runtime
- 🔄 **Pure ONNX inference**: No Ultralytics dependency, direct ONNX Runtime implementation

## Architecture

```
Home Assistant (10.0.0.2)
    ├─ Camera → Snapshot URL
    └─ MQTT Broker ← Detector publishes here

Raspberry Pi (detector)
    └─ mailcam_detector.service
        ├─ Fetches snapshots every 2.5s
        ├─ Runs ONNX inference
        ├─ Tracks daily detections
        └─ Publishes to MQTT
```

## Requirements

### Hardware
- Raspberry Pi (tested on Pi 5 8GB) or similar Linux system
- Network access to Home Assistant

### Software
- Python 3.9+
- Home Assistant with:
  - Camera entity or snapshot URL
  - MQTT broker (Mosquitto recommended)
  - MQTT integration enabled

## Installation

### Quick Start (Recommended)

Use the interactive setup script:

```bash
git clone https://github.com/YOUR_USERNAME/mailcam.git
cd mailcam
./setup.sh
```

The script will guide you through:
- Creating virtual environment
- Installing dependencies
- Configuring MQTT and camera settings
- Testing the setup
- Installing systemd service

### Manual Installation

Alternatively, follow these steps manually:

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/mailcam.git
cd mailcam
```

### 2. Download ONNX Model

This project uses a delivery vehicle detection model from the [CodeProject.AI Custom IPcam Models](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models) repository.

**Option A: Download from CodeProject.AI repository** (recommended)

```bash
# Clone the model repository
cd ~
git clone https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models.git

# Copy the delivery model to your mailcam directory
cp ~/CodeProject.AI-Custom-IPcam-Models/ONNX\ models/delivery.onnx ~/mailcam/models/delivery_task.onnx

# Copy the labels file
cp ~/CodeProject.AI-Custom-IPcam-Models/PT\ Models/delivery.names ~/mailcam/models/
```

**Option B: Download from releases** (if available)
- Check the [Releases](https://github.com/YOUR_USERNAME/mailcam/releases) page
- Download `delivery_task.onnx`
- Place in `models/` directory

**Option C: Use your own trained model**
- Train with [Ultralytics YOLOv8](https://docs.ultralytics.com/)
- Export to ONNX format (640x640)
- Must detect: amazon, dhl, fedex, ups, usps

**Model Details:**
- **Source**: CodeProject.AI Custom IPcam Models
- **Format**: YOLOv8 ONNX (640x640)
- **Classes**: amazon, dhl, fedex, ups, usps
- **Size**: ~29MB
- **License**: Check the [original repository](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models) for licensing terms

### 3. Create Python Virtual Environment

```bash
python3 -m venv detectenv
source detectenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Detector

```bash
cd detector
cp mailcam.yml.example mailcam.yml
nano mailcam.yml
```

Update the following fields:
- `mqtt.host`: Your MQTT broker IP (e.g., 10.0.0.2)
- `mqtt.user`: MQTT username
- `mqtt.password`: MQTT password
- `source.url`: Your camera snapshot URL
- `model.path`: Path to ONNX model file
- `model.labels`: Path to label names file

### 5. Test Manually

```bash
cd detector
source ~/mailcam/detectenv/bin/activate
python mailcam_detector_onnx.py
```

You should see:
```
[mailcam] Config loaded from /path/to/mailcam.yml
[mailcam] Model loaded successfully
[mailcam] Starting detection loop
[mailcam] Connected to MQTT broker
[mailcam] Published Home Assistant discovery configuration
```

Press Ctrl+C to stop.

### 6. Install Systemd Service

```bash
# Edit the template with your paths
sudo nano systemd/mailcam_detector.service.template

# Update these fields:
#   User=YOUR_USERNAME
#   WorkingDirectory=/path/to/mailcam/detector
#   ExecStart=/path/to/detectenv/bin/python /path/to/mailcam/detector/mailcam_detector_onnx.py

# Copy to systemd
sudo cp systemd/mailcam_detector.service.template /etc/systemd/system/mailcam_detector.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mailcam_detector.service
sudo systemctl start mailcam_detector.service

# Check status
sudo systemctl status mailcam_detector.service
```

## Home Assistant Configuration

### MQTT Sensors (Auto-Discovery)

The detector automatically creates these entities via MQTT discovery:

**Binary Sensors** (per carrier):
- `binary_sensor.mailcam_amazon_today`
- `binary_sensor.mailcam_fedex_today`
- `binary_sensor.mailcam_ups_today`
- `binary_sensor.mailcam_usps_today`
- `binary_sensor.mailcam_dhl_today`

**Sensors**:
- `sensor.mailcam_daily_summary` (includes timestamps as attributes)
- `sensor.mailcam_current_status`
- `sensor.mailcam_detection_details`

### Automations

Add the automations from `homeassistant_automations.yaml` to get:
- Instant notifications when each carrier is detected
- Daily report at 7:30 PM with all deliveries and times

**To add automations:**
1. Copy contents of `homeassistant_automations.yaml`
2. In HA: **Settings** → **Automations & Scenes** → **+ Create Automation**
3. Click **⋮** → **Edit in YAML**
4. Paste each automation

## Usage

### Check Service Status

```bash
sudo systemctl status mailcam_detector.service
```

### View Logs

```bash
# Follow logs in real-time
journalctl -u mailcam_detector.service -f

# View last 100 lines
journalctl -u mailcam_detector.service -n 100 --no-pager
```

### Monitor MQTT Messages

```bash
# View all mailcam topics
mosquitto_sub -h YOUR_MQTT_HOST -t "mailcam/#" -v -u YOUR_USER -P YOUR_PASS

# View carrier states
mosquitto_sub -h YOUR_MQTT_HOST -t "mailcam/carriers/#" -v -u YOUR_USER -P YOUR_PASS

# View daily summary
mosquitto_sub -h YOUR_MQTT_HOST -t "mailcam/daily_summary" -v -u YOUR_USER -P YOUR_PASS
```

### Test Detection

```bash
# Simulate Amazon detection (for testing)
mosquitto_pub -h YOUR_MQTT_HOST -t "mailcam/carriers/amazon" -m "yes" -u YOUR_USER -P YOUR_PASS -r
```

## Configuration

### Model Parameters (`detector/mailcam.yml`)

```yaml
model:
  conf_min: 0.30          # Minimum confidence threshold (0.0-1.0)
  area_min_frac: 0.0005   # Minimum detection area as fraction of image
  imgsz: 640              # Model input size (must match ONNX model)
  allow_labels: [amazon, dhl, fedex, ups, usps]  # Carriers to detect
```

### Source Configuration

```yaml
source:
  kind: image             # Always "image" for HTTP snapshots
  url: "http://..."       # Camera snapshot URL
  poll_sec: 2.5           # How often to check (seconds)
  timeout_sec: 5.0        # HTTP request timeout
```

### Daily Reset

The detector automatically resets all carrier states to "no" at **3:00 AM** each day. This timing is hardcoded but can be changed in the `DailyCarrierTracker` class (`mailcam_detector_onnx.py`).

## Troubleshooting

### Service Not Detecting

1. Check logs for errors:
   ```bash
   journalctl -u mailcam_detector.service -n 50
   ```

2. Verify camera snapshot URL:
   ```bash
   curl http://YOUR_HA_HOST:8123/local/mailcam/latest.jpg -o test.jpg
   file test.jpg  # Should be JPEG image
   ```

3. Test MQTT connection:
   ```bash
   mosquitto_sub -h YOUR_MQTT_HOST -t "mailcam/state" -v -u YOUR_USER -P YOUR_PASS
   ```

### High CPU Usage

- Expected: ~40% on Raspberry Pi 5
- If higher: Check thread count with `ps -T -p $(pgrep -f mailcam_detector_onnx)`
- Should have ~5 threads with single-threaded ONNX Runtime

### Detection Not Accurate

1. Adjust confidence threshold in `mailcam.yml`:
   ```yaml
   conf_min: 0.25  # Lower = more detections (more false positives)
   ```

2. Adjust minimum area:
   ```yaml
   area_min_frac: 0.0003  # Lower = detect smaller objects
   ```

3. Check model quality - you may need to retrain with more/better images

## Development

See [CLAUDE.md](CLAUDE.md) for detailed development guidance including:
- Architecture overview
- Common commands
- Debugging tips
- Important constraints

## Project Structure

```
mailcam/
├── detector/
│   ├── mailcam_detector_onnx.py   # Main detector daemon
│   ├── mailcam.yml.example        # Config template
│   └── mailcam.yml                # Your config (gitignored)
├── models/
│   ├── delivery_task.onnx         # ONNX model (gitignored)
│   └── delivery.names             # Label names
├── systemd/
│   └── mailcam_detector.service.template
├── homeassistant_automations.yaml
├── requirements.txt
├── CLAUDE.md                      # Development guide
└── README.md
```

## License

MIT License - feel free to use and modify!

## Credits

Built with:
- [ONNX Runtime](https://onnxruntime.ai/)
- [YOLOv8](https://github.com/ultralytics/ultralytics)
- [Home Assistant](https://www.home-assistant.io/)
- [Eclipse Paho MQTT](https://www.eclipse.org/paho/)

**Detection Model:**
- Model by [MikeLud](https://github.com/MikeLud) from [CodeProject.AI Custom IPcam Models](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models)
- Used under the terms of their license
