#!/bin/bash
# Commands to initialize Git repository and push to GitHub

echo "Initializing Git repository..."

# 1. Initialize git (if not already done)
if [ ! -d .git ]; then
    git init
    echo "✓ Git initialized"
else
    echo "✓ Git already initialized"
fi

# 2. Add files
echo "Adding files to git..."
git add .gitignore
git add LICENSE
git add README.md CLAUDE.md INSTALL.md CONTRIBUTING.md
git add ARCHITECTURE.md CHANGELOG.md MODEL_DISTRIBUTION.md
git add requirements.txt
git add setup.sh
git add detector/mailcam_detector_onnx.py
git add detector/mailcam.yml.example
git add homeassistant_automations.yaml
git add systemd/
git add models/.gitkeep
git add models/delivery.names
git add .github/

echo "✓ Files staged"

# 3. Check if initial commit exists
if git rev-parse HEAD >/dev/null 2>&1; then
    echo "Git repository already has commits"
    echo "Run: git status"
    echo "Then: git commit -m 'Your message'"
else
    # Create initial commit
    echo "Creating initial commit..."
    git commit -m "Initial commit: Mailcam delivery detector

- ONNX-based delivery vehicle detection
- Daily per-carrier tracking with 3 AM reset
- Home Assistant MQTT integration
- Interactive setup script
- Comprehensive documentation"
    echo "✓ Initial commit created"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Create a new repository on GitHub"
echo "   Visit: https://github.com/new"
echo ""
echo "2. Add the remote:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/mailcam.git"
echo ""
echo "3. Push to GitHub:"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "4. (Optional) Add model as GitHub Release"
echo "   - Go to your repo → Releases → Create new release"
echo "   - Upload delivery_task.onnx as release asset"
echo ""
