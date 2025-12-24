#!/bin/bash
# Setup and activation script for Media Extractor

echo "Setting up Media Extractor with virtual environment..."

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Virtual environment created at: venv/"
echo ""
echo "To activate the environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To deactivate, run:"
echo "  deactivate"
echo ""
echo "To run the media extractor:"
echo "  source venv/bin/activate"
echo "  python3 media_extractor.py"
echo ""
echo "Or in one command:"
echo "  source venv/bin/activate && python3 media_extractor.py"
