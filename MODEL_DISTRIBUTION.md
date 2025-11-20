# Model Distribution Guide

The delivery detection model comes from the [CodeProject.AI Custom IPcam Models](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models) repository.

## For Repository Maintainer

You have two options for distributing the model:

### Option 1: Users Download from Source (Recommended)

**Pros:**
- No copyright concerns
- Users get latest model updates
- Keeps your repo lightweight
- Proper attribution

**Cons:**
- Users need extra download step

This is already documented in the README. Users will:
```bash
git clone https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models.git
cp CodeProject.AI-Custom-IPcam-Models/ONNX\ models/delivery.onnx mailcam/models/delivery_task.onnx
```

### Option 2: Provide via GitHub Release

**If you choose to include the model in your releases:**

1. **Check the License**: Review [CodeProject.AI's license](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models/blob/main/LICENSE)

2. **Create Release with Model**:
   ```bash
   # After pushing your code to GitHub:
   # 1. Go to your repo → Releases → "Create a new release"
   # 2. Tag: v1.0.0
   # 3. Title: "Initial Release"
   # 4. Click "Attach binaries by dropping them here"
   # 5. Upload: ~/mailcam/models/delivery_task.onnx
   # 6. In description, add:
   ```

   **Release Description Template:**
   ```markdown
   ## Mailcam v1.0.0

   Initial release of the Mailcam Delivery Detector.

   ### Included Model

   The `delivery_task.onnx` model is from the [CodeProject.AI Custom IPcam Models](https://github.com/MikeLud/CodeProject.AI-Custom-IPcam-Models) repository by [MikeLud](https://github.com/MikeLud).

   **Model Details:**
   - Format: YOLOv8 ONNX (640x640)
   - Classes: amazon, dhl, fedex, ups, usps
   - Size: ~29MB
   - License: See original repository

   ### Installation

   ```bash
   git clone https://github.com/YOUR_USERNAME/mailcam.git
   cd mailcam

   # Download model from this release
   wget https://github.com/YOUR_USERNAME/mailcam/releases/download/v1.0.0/delivery_task.onnx -P models/

   # Or run setup script (will prompt for model)
   ./setup.sh
   ```
   ```

3. **Update README**: Add release download link as an option

## For Users

See the [Installation section in README.md](README.md#installation) for model download instructions.

## Model Alternatives

If you want to use a different model:
1. Train your own with YOLOv8
2. Export to ONNX (640x640)
3. Ensure it detects: amazon, dhl, fedex, ups, usps
4. Place at `models/delivery_task.onnx`
