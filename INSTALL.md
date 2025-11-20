# Quick Installation Guide

## Prerequisites

- Raspberry Pi or Linux system
- Python 3.9+
- Home Assistant with MQTT broker

## Automated Setup (Recommended)

```bash
git clone https://github.com/YOUR_USERNAME/mailcam.git
cd mailcam
./setup.sh
```

The interactive script handles everything! Or follow the manual steps below:

## Manual Setup

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/mailcam.git
cd mailcam

# 2. Create virtual environment
python3 -m venv detectenv
source detectenv/bin/activate
pip install -r requirements.txt

# 3. Download/place your ONNX model
# Place delivery_task.onnx in models/ directory

# 4. Configure
cd detector
cp mailcam.yml.example mailcam.yml
nano mailcam.yml  # Edit with your settings

# 5. Test
python mailcam_detector_onnx.py

# 6. Install as service
cd ..
sudo cp systemd/mailcam_detector.service.template /etc/systemd/system/mailcam_detector.service
sudo nano /etc/systemd/system/mailcam_detector.service  # Update paths
sudo systemctl daemon-reload
sudo systemctl enable --now mailcam_detector.service
```

See [README.md](README.md) for detailed instructions.
