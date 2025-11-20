# Changelog

All notable changes to Mailcam will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-11-20

### Added
- Initial release of Mailcam delivery detector
- ONNX-based delivery vehicle detection (Amazon, FedEx, UPS, USPS, DHL)
- Daily per-carrier tracking with automatic 3 AM reset
- Home Assistant MQTT auto-discovery integration
- Interactive setup script (`setup.sh`)
- Systemd service template
- Comprehensive documentation (README, ARCHITECTURE, CLAUDE.md)
- GitHub issue and PR templates
- CI/CD workflow for validation

### Features
- Pure ONNX Runtime inference (no Ultralytics dependency)
- Low resource usage (~40% CPU on Raspberry Pi 5)
- HTTP snapshot polling (2.5s intervals)
- Persistent carrier state via MQTT retained messages
- Instant notifications when carriers detected
- Daily summary reports at 7:30 PM
- Configurable confidence and area thresholds
- Automatic Home Assistant entity creation

### Documentation
- Complete installation guide with automated setup
- Architecture documentation with diagrams
- Developer guide (CLAUDE.md) for contributors
- Home Assistant automation examples
- Model distribution and licensing information

## Legacy Versions

Previous implementations (Ultralytics-based detector, restream service) have been moved to the `legacy/` directory and are no longer supported.

---

## Release Notes

### Version 1.0.0

This is the first stable release of Mailcam, rewritten from scratch to use pure ONNX Runtime instead of the Ultralytics YOLO wrapper. Key improvements over legacy versions:

**Performance:**
- 35% CPU reduction (from ~75% to ~40% on Raspberry Pi 5)
- Single-threaded ONNX execution prevents CPU oversubscription
- Proper HTTP snapshot fetching (no cv2.VideoCapture issues)

**Reliability:**
- No auto-update issues with externally-managed Python environments
- Better resource control via systemd limits
- Persistent state across restarts

**Usability:**
- Interactive setup script guides installation
- Portable configuration with relative paths
- Clear documentation and examples

**Maintenance:**
- Clean codebase with legacy code separated
- GitHub templates for issues and PRs
- CI/CD validation workflow
