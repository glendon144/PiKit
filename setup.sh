#!/usr/bin/env bash
set -e

# Install system dependencies (WSL/Ubuntu 22.04)
sudo apt update
sudo apt install -y build-essential python3-dev libatlas-base-dev gfortran

# Create & activate virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip, setuptools, wheel
pip install --upgrade pip setuptools wheel

# Install Python dependencies
pip install numpy pandas pyserial tk

echo "Setup complete! Virtualenv is active. To start working, run 'source .venv/bin/activate'."
