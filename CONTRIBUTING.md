# Contributing to Mailcam

Thank you for your interest in contributing to Mailcam!

## How to Contribute

### Reporting Issues

- Use GitHub Issues to report bugs or request features
- Provide detailed information:
  - Your OS and Python version
  - Home Assistant version
  - Error messages and logs
  - Steps to reproduce

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit with clear messages
6. Push to your fork
7. Open a Pull Request

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/mailcam.git
cd mailcam
./setup.sh
```

## Testing

Before submitting a PR:

1. Test the detector runs without errors
2. Verify MQTT messages publish correctly
3. Check Home Assistant integration works
4. Test with actual delivery vehicle images if possible

## Code Style

- Follow PEP 8 for Python code
- Use clear, descriptive variable names
- Add comments for complex logic
- Keep functions focused and small

## Model Improvements

If you improve the detection model:

1. Document training process
2. Share dataset statistics
3. Include accuracy metrics
4. Provide model file via GitHub Release

## Documentation

- Update README.md for user-facing changes
- Update CLAUDE.md for developer guidance
- Keep examples up to date

## Questions?

Open a GitHub Discussion or Issue - we're here to help!
