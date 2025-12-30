#!/bin/bash
set -e

echo "🐍 Setting up Python virtual environment..."

# Ensure python3 exists
command -v python3 >/dev/null 2>&1 || {
    echo "❌ python3 not found"
    exit 1
}

# Create venv
python3 -m venv .venv

# Verify venv creation
if [ ! -f ".venv/bin/activate" ]; then
    echo "❌ Virtual environment creation failed"
    exit 1
fi

# Activate venv
source .venv/bin/activate

# Upgrade & install packages
pip install --upgrade pip
pip install numpy scipy matplotlib pyserial smbus2

echo "✅ Python virtual environment ready"
