
#!/usr/bin/env python3

import subprocess
import sys

def pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def pip_upgrade(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package])

# Upgrade pip first with correct argument separation
pip_upgrade("pip")

# Core DemoKit dependencies (i686 compatible)
pip_install("numpy==1.19.5")
pip_install("pandas==1.1.5")
pip_install("openai")
pip_install("tiktoken")
pip_install("requests")

# Full Google API stack (namespace-safe versions)
pip_install("google-api-python-client")
pip_install("google-auth")
pip_install("google-auth-oauthlib")
pip_install("google-auth-httplib2")

# Other useful AI libraries (future expansions)
pip_install("aiohttp")
pip_install("scipy")
