#!/bin/bash
set -e

# Configuration
PYTHON_VERSION=3.12.3
INSTALL_DIR="$HOME/.pyenv/versions/$PYTHON_VERSION"
ARCH_LIB_DIR="/usr/lib/i386-linux-gnu"

echo "🔧 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
  build-essential zlib1g-dev libncurses5-dev libgdbm-dev \
  libnss3-dev libssl-dev libreadline-dev libffi-dev \
  libsqlite3-dev wget curl tk-dev tcl-dev \
  libx11-dev libxext-dev libxrender-dev libxcb1-dev libxft-dev \
  make xz-utils

echo "📦 Downloading Python $PYTHON_VERSION..."
cd ~
wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
tar -xf Python-$PYTHON_VERSION.tgz
cd Python-$PYTHON_VERSION

echo "🛠  Configuring build with tkinter support..."
./configure \
  --prefix="$INSTALL_DIR" \
  --enable-optimizations \
  CPPFLAGS="-I/usr/include" \
  LDFLAGS="-L$ARCH_LIB_DIR -ltk8.6 -ltcl8.6" \
  PKG_CONFIG_PATH="$ARCH_LIB_DIR/pkgconfig"

echo "🔨 Building Python (this may take several minutes)..."
make -j$(nproc)

echo "📥 Installing Python to $INSTALL_DIR..."
make install

echo "🔁 Setting pyenv to use $PYTHON_VERSION..."
pyenv rehash
pyenv global "$PYTHON_VERSION"

echo "🧪 Testing tkinter support..."
python -m tkinter

echo "✅ DONE! You should see a test GUI window."

