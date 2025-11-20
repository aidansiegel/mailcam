#!/bin/bash
# Mailcam Delivery Detector - Interactive Setup Script
# This script guides you through the installation and configuration process

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

prompt_yes_no() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

prompt_input() {
    local prompt="$1"
    local default="$2"
    local result

    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " result
        result="${result:-$default}"
    else
        read -p "$prompt: " result
    fi

    echo "$result"
}

# Banner
clear
echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║          Mailcam Delivery Detector Setup                 ║
║                                                           ║
║     AI-powered delivery vehicle detection for            ║
║              Home Assistant                              ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

print_info "This script will guide you through the installation process."
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please do not run this script as root"
    exit 1
fi

# Step 1: Check Prerequisites
print_header "Step 1: Checking Prerequisites"

# Check Python version
print_info "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 9 ]; then
        print_success "Python $PYTHON_VERSION found"
        PYTHON_CMD="python3"
    else
        print_error "Python 3.9 or higher required (found $PYTHON_VERSION)"
        exit 1
    fi
else
    print_error "Python 3 not found. Please install Python 3.9 or higher"
    exit 1
fi

# Check pip
print_info "Checking pip..."
if $PYTHON_CMD -m pip --version &> /dev/null; then
    print_success "pip found"
else
    print_error "pip not found. Please install pip"
    exit 1
fi

# Check git
print_info "Checking git..."
if command -v git &> /dev/null; then
    print_success "git found"
else
    print_warning "git not found (optional, needed for version control)"
fi

# Step 2: Virtual Environment
print_header "Step 2: Creating Virtual Environment"

VENV_PATH="$SCRIPT_DIR/detectenv"

if [ -d "$VENV_PATH" ]; then
    print_warning "Virtual environment already exists at $VENV_PATH"
    if prompt_yes_no "Do you want to recreate it?"; then
        print_info "Removing existing virtual environment..."
        rm -rf "$VENV_PATH"
        print_success "Removed"
    else
        print_info "Using existing virtual environment"
    fi
fi

if [ ! -d "$VENV_PATH" ]; then
    print_info "Creating virtual environment at $VENV_PATH..."
    $PYTHON_CMD -m venv "$VENV_PATH"
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source "$VENV_PATH/bin/activate"
print_success "Activated"

# Step 3: Install Dependencies
print_header "Step 3: Installing Python Dependencies"

print_info "Upgrading pip..."
pip install --upgrade pip --quiet

print_info "Installing required packages (this may take a few minutes)..."
pip install -r requirements.txt --quiet
print_success "All dependencies installed"

# Verify critical packages
print_info "Verifying installation..."
python3 << 'PYCHECK'
import sys
try:
    import numpy
    import PIL
    import requests
    import yaml
    import paho.mqtt.client
    import onnxruntime
    print("✓ All required packages verified")
    sys.exit(0)
except ImportError as e:
    print(f"✗ Missing package: {e}")
    sys.exit(1)
PYCHECK

if [ $? -eq 0 ]; then
    print_success "Package verification complete"
else
    print_error "Package verification failed"
    exit 1
fi

# Step 4: Model Setup
print_header "Step 4: Model Setup"

MODEL_DIR="$SCRIPT_DIR/models"
MODEL_FILE="$MODEL_DIR/delivery_task.onnx"

mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_FILE" ]; then
    print_success "Model file found at $MODEL_FILE"
    MODEL_SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    print_info "Model size: $MODEL_SIZE"
else
    print_warning "Model file not found at $MODEL_FILE"
    echo ""
    echo "This project uses a delivery detection model from:"
    echo "  CodeProject.AI Custom IPcam Models"
    echo "  https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models"
    echo ""
    echo "Options:"
    echo "  1. Download from CodeProject.AI repository (recommended)"
    echo "  2. Copy an existing model file"
    echo "  3. Skip for now (manual setup later)"
    echo ""

    read -p "Choose option (1/2/3): " choice
    case $choice in
        1)
            print_info "Downloading model from CodeProject.AI repository..."
            CPAI_DIR="/tmp/cpai-models"

            if [ -d "$CPAI_DIR" ]; then
                print_info "Using existing clone at $CPAI_DIR"
            else
                print_info "Cloning CodeProject.AI-Custom-IPcam-Models..."
                git clone https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models.git "$CPAI_DIR" --depth 1 --quiet
            fi

            if [ -f "$CPAI_DIR/ONNX models/delivery.onnx" ]; then
                print_info "Copying model file..."
                cp "$CPAI_DIR/ONNX models/delivery.onnx" "$MODEL_FILE"
                print_success "Model downloaded and copied!"

                # Copy labels file if exists
                if [ -f "$CPAI_DIR/PT Models/delivery.names" ]; then
                    cp "$CPAI_DIR/PT Models/delivery.names" "$MODEL_DIR/"
                    print_success "Labels file copied"
                fi
            else
                print_error "Model not found in CodeProject.AI repository"
                print_warning "You'll need to add the model file manually"
            fi
            ;;
        2)
            MODEL_SOURCE=$(prompt_input "Enter path to your ONNX model file")
            if [ -f "$MODEL_SOURCE" ]; then
                print_info "Copying model file..."
                cp "$MODEL_SOURCE" "$MODEL_FILE"
                print_success "Model copied to $MODEL_FILE"
            else
                print_error "File not found: $MODEL_SOURCE"
                print_warning "You'll need to add the model file manually before running"
            fi
            ;;
        3)
            print_warning "Skipping model download"
            print_info "Download instructions: See README.md section 2"
            ;;
        *)
            print_warning "Invalid option. Skipping model download"
            ;;
    esac
fi

# Check for labels file
LABELS_FILE="$SCRIPT_DIR/models/delivery.names"
if [ ! -f "$LABELS_FILE" ]; then
    print_warning "Labels file not found at $LABELS_FILE"

    if prompt_yes_no "Create a default labels file?"; then
        cat > "$LABELS_FILE" << 'EOF'
amazon
dhl
fedex
ups
usps
EOF
        print_success "Created default labels file with 5 carriers"
    fi
fi

# Step 5: Configuration
print_header "Step 5: Configuration"

CONFIG_FILE="$SCRIPT_DIR/detector/mailcam.yml"
CONFIG_EXAMPLE="$SCRIPT_DIR/detector/mailcam.yml.example"

if [ -f "$CONFIG_FILE" ]; then
    print_warning "Configuration file already exists at $CONFIG_FILE"
    if prompt_yes_no "Do you want to reconfigure?"; then
        RECONFIGURE=true
    else
        RECONFIGURE=false
        print_info "Using existing configuration"
    fi
else
    RECONFIGURE=true
fi

if [ "$RECONFIGURE" = true ]; then
    print_info "Starting configuration wizard..."
    echo ""

    # MQTT Settings
    echo -e "${YELLOW}MQTT Broker Settings:${NC}"
    MQTT_HOST=$(prompt_input "MQTT broker hostname/IP" "10.0.0.2")
    MQTT_PORT=$(prompt_input "MQTT broker port" "1883")
    MQTT_USER=$(prompt_input "MQTT username" "delivery")
    MQTT_PASS=$(prompt_input "MQTT password" "")

    # Camera Settings
    echo ""
    echo -e "${YELLOW}Camera Settings:${NC}"
    echo "Enter the URL to your camera snapshot (usually from Home Assistant)"
    echo "Example: http://homeassistant.local:8123/local/mailcam/latest.jpg"
    CAMERA_URL=$(prompt_input "Camera snapshot URL" "http://10.0.0.2:8123/local/mailcam/latest.jpg")

    # Detection Settings
    echo ""
    echo -e "${YELLOW}Detection Settings:${NC}"
    POLL_INTERVAL=$(prompt_input "Polling interval in seconds" "2.5")
    CONF_MIN=$(prompt_input "Minimum confidence threshold (0.0-1.0)" "0.30")
    AREA_MIN=$(prompt_input "Minimum detection area fraction" "0.0005")

    # Create configuration file
    print_info "Creating configuration file..."

    cat > "$CONFIG_FILE" << EOF
model:
  # ONNX delivery model
  path: $SCRIPT_DIR/models/delivery_task.onnx
  # Labels file
  labels: $SCRIPT_DIR/models/delivery.names
  # Inference parameters
  allow_labels: [amazon, dhl, fedex, ups, usps]
  imgsz: 640
  conf_min: $CONF_MIN
  area_min_frac: $AREA_MIN

mqtt:
  host: $MQTT_HOST
  port: $MQTT_PORT
  user: $MQTT_USER
  password: $MQTT_PASS
  state_topic: mailcam/state
  detail_topic: mailcam/details

source:
  # We are reading a single JPEG snapshot periodically, not an RTSP stream
  kind: image
  url: "$CAMERA_URL"
  # Polling interval in seconds
  poll_sec: $POLL_INTERVAL
  timeout_sec: 5.0
EOF

    print_success "Configuration file created at $CONFIG_FILE"
    print_warning "Note: Your MQTT password is stored in plain text in this file"
fi

# Step 6: Test Configuration
print_header "Step 6: Testing Configuration"

print_info "Testing detector (this will run for a few iterations)..."
echo ""
echo "Press Ctrl+C to stop the test early"
echo ""
sleep 2

cd "$SCRIPT_DIR/detector"
timeout 15 python mailcam_detector_onnx.py || true

echo ""
if [ $? -eq 124 ]; then
    print_success "Test completed (timed out after 15 seconds)"
else
    print_info "Test stopped"
fi

echo ""
if prompt_yes_no "Did the detector start successfully?"; then
    print_success "Configuration test passed!"
else
    print_error "Configuration test failed"
    echo ""
    echo "Common issues:"
    echo "  - Model file missing or incorrect path"
    echo "  - Camera URL not accessible"
    echo "  - MQTT broker connection failed"
    echo "  - Labels file missing"
    echo ""
    print_info "Check the error messages above for details"

    if ! prompt_yes_no "Continue with setup anyway?"; then
        exit 1
    fi
fi

# Step 7: Systemd Service Installation
print_header "Step 7: Systemd Service Installation (Optional)"

if prompt_yes_no "Do you want to install the detector as a systemd service?"; then
    SERVICE_FILE="/etc/systemd/system/mailcam_detector.service"
    TEMPLATE_FILE="$SCRIPT_DIR/systemd/mailcam_detector.service.template"

    print_info "Creating systemd service file..."

    # Get current user
    CURRENT_USER=$(whoami)

    # Create service file with proper paths
    sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=Mailcam Detector (ONNX)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR/detector

# Python settings
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONWARNINGS=ignore::DeprecationWarning

# ONNX Runtime settings
Environment=ORT_NUM_THREADS=1

# Optional: override poll interval (default: from YAML)
Environment=MAILCAM_POLL=$POLL_INTERVAL

# Execute the ONNX-based detector daemon
ExecStart=$VENV_PATH/bin/python $SCRIPT_DIR/detector/mailcam_detector_onnx.py

# Restart policy
Restart=on-failure
RestartSec=3

# Logging
StandardOutput=journal
StandardError=journal

# Resource limits
CPUAccounting=yes
CPUQuota=70%
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6
MemoryMax=400M

[Install]
WantedBy=multi-user.target
EOF

    print_success "Service file created at $SERVICE_FILE"

    print_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    print_info "Enabling service to start on boot..."
    sudo systemctl enable mailcam_detector.service

    if prompt_yes_no "Start the service now?"; then
        print_info "Starting mailcam_detector.service..."
        sudo systemctl start mailcam_detector.service
        sleep 2

        echo ""
        print_info "Service status:"
        sudo systemctl status mailcam_detector.service --no-pager -l | head -20
        echo ""

        if sudo systemctl is-active --quiet mailcam_detector.service; then
            print_success "Service is running!"
        else
            print_error "Service failed to start"
            echo ""
            print_info "Check logs with: journalctl -u mailcam_detector.service -n 50"
        fi
    else
        print_info "Service installed but not started"
        print_info "Start it later with: sudo systemctl start mailcam_detector.service"
    fi
else
    print_info "Skipping systemd service installation"
    print_info "You can run the detector manually with:"
    echo "  cd $SCRIPT_DIR/detector"
    echo "  source $VENV_PATH/bin/activate"
    echo "  python mailcam_detector_onnx.py"
fi

# Step 8: Home Assistant Setup
print_header "Step 8: Home Assistant Integration"

echo "The detector publishes MQTT discovery messages automatically."
echo ""
echo "In Home Assistant, you should see these entities appear:"
echo "  - binary_sensor.mailcam_amazon_today"
echo "  - binary_sensor.mailcam_fedex_today"
echo "  - binary_sensor.mailcam_ups_today"
echo "  - binary_sensor.mailcam_usps_today"
echo "  - binary_sensor.mailcam_dhl_today"
echo "  - sensor.mailcam_daily_summary"
echo ""
echo "To add automations for notifications and daily reports:"
echo "  1. Open homeassistant_automations.yaml"
echo "  2. Copy each automation to Home Assistant"
echo "  3. Settings → Automations & Scenes → Create Automation → Edit in YAML"
echo ""

if prompt_yes_no "Would you like to view the automations file now?"; then
    less "$SCRIPT_DIR/homeassistant_automations.yaml" || cat "$SCRIPT_DIR/homeassistant_automations.yaml"
fi

# Final Summary
print_header "Setup Complete!"

echo -e "${GREEN}✓ Virtual environment created${NC}"
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo -e "${GREEN}✓ Configuration created${NC}"

if [ -f "$MODEL_FILE" ]; then
    echo -e "${GREEN}✓ Model file present${NC}"
else
    echo -e "${YELLOW}! Model file needed${NC}"
fi

if sudo systemctl is-active --quiet mailcam_detector.service 2>/dev/null; then
    echo -e "${GREEN}✓ Service running${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Next Steps:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ ! -f "$MODEL_FILE" ]; then
    echo "1. Place your ONNX model at: $MODEL_FILE"
fi

echo "2. Check service logs:"
echo "   journalctl -u mailcam_detector.service -f"
echo ""
echo "3. Monitor MQTT messages:"
echo "   mosquitto_sub -h $MQTT_HOST -t 'mailcam/#' -v -u $MQTT_USER -P <password>"
echo ""
echo "4. Verify Home Assistant entities appear"
echo ""
echo "5. Add automations from homeassistant_automations.yaml"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Useful Commands:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Service management:"
echo "  sudo systemctl status mailcam_detector.service"
echo "  sudo systemctl restart mailcam_detector.service"
echo "  sudo systemctl stop mailcam_detector.service"
echo ""
echo "View logs:"
echo "  journalctl -u mailcam_detector.service -n 100"
echo "  journalctl -u mailcam_detector.service -f"
echo ""
echo "Manual testing:"
echo "  cd $SCRIPT_DIR/detector"
echo "  source $VENV_PATH/bin/activate"
echo "  python mailcam_detector_onnx.py"
echo ""
echo "Edit configuration:"
echo "  nano $CONFIG_FILE"
echo ""

echo -e "${GREEN}Installation complete! 🎉${NC}"
echo ""

# Save setup info
cat > "$SCRIPT_DIR/.setup-info" << EOF
# Mailcam Setup Information
# Generated: $(date)

VENV_PATH=$VENV_PATH
CONFIG_FILE=$CONFIG_FILE
MODEL_FILE=$MODEL_FILE
MQTT_HOST=$MQTT_HOST
CAMERA_URL=$CAMERA_URL
EOF

print_info "Setup information saved to .setup-info"
