#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

echo "Installing Python 3, pip, and Tkinter..."
sudo apt-get install -y python3 python3-pip python3-venv python3-tk

# Set your app directory here
APP_DIR=~/Engelbart

echo "Creating app directory at $APP_DIR"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip inside virtual environment..."
pip install --upgrade pip

echo "Installing required Python packages..."
pip install requests

echo "Verifying tkinter availability..."
python3 -c "import tkinter; print('Tkinter installed successfully.')"

echo "Environment setup complete."
echo "To activate the environment in the future, run:"
echo "  source $APP_DIR/venv/bin/activate"

