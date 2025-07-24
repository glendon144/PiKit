#!/bin/bash
set -e

PY_VERSION="3.12.3"
INSTALL_PREFIX="/usr/local"

echo "🔍 Step 1: Installing prerequisites..."
sudo apt update
sudo apt install -y \
  build-essential \
  libncursesw5-dev \
  libreadline-dev \
  libssl-dev \
  libsqlite3-dev \
  libgdbm-dev \
  libc6-dev \
  libbz2-dev \
  libffi-dev \
  zlib1g-dev \
  liblzma-dev \
  uuid-dev \
  tk-dev \
  libx11-dev \
  libxext-dev \
  libxrender-dev \
  libxrandr-dev \
  libxcursor-dev \
  libxfixes-dev \
  libxinerama-dev \
  libxi-dev \
  libgl1-mesa-dev \
  wget \
  curl \
  x11-utils

echo "📦 Step 2: Downloading Python $PY_VERSION source..."
cd /usr/src
sudo rm -rf Python-$PY_VERSION
sudo wget https://www.python.org/ftp/python/$PY_VERSION/Python-$PY_VERSION.tgz
sudo tar xvf Python-$PY_VERSION.tgz
cd Python-$PY_VERSION

echo "⚙️ Step 3: Configuring build with tkinter support..."
sudo ./configure \
  --enable-optimizations \
  --with-ensurepip=install \
  --prefix=$INSTALL_PREFIX \
  > configure.log 2>&1

if ! grep -i "using tk" configure.log; then
  echo "❌ ERROR: Tkinter support not detected during configure. Check for tk.h."
  echo "🔍 Try: 'dpkg -L tk-dev | grep tk.h' to verify tk headers exist."
  exit 1
fi

echo "🧱 Step 4: Building Python (this may take a while)..."
sudo make -j$(nproc) > build.log 2>&1

echo "📥 Step 5: Installing Python $PY_VERSION..."
sudo make altinstall

echo "✅ Step 6: Verifying tkinter support..."
PYBIN="$INSTALL_PREFIX/bin/python${PY_VERSION%.*}"

if ! "$PYBIN" -c "import tkinter; print('Tkinter OK')" 2>/dev/null; then
  echo "❌ Tkinter not available in $PYBIN"
  echo "📄 Check logs: configure.log and build.log"
  exit 1
else
  echo "🎉 SUCCESS: $PYBIN has tkinter support."
  "$PYBIN" -m tkinter
fi
