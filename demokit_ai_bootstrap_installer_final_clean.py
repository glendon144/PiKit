
#!/usr/bin/env python3

import subprocess
import sys

def pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def pip_upgrade(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package])

# Downgrade pip to fully compatible legacy version (pre-PEP-517 enforcement)
pip_install("pip==20.3.4")

# Install stable AI-related packages (i686 + Python 3.9 compatible)
pip_install("numpy==1.19.5")
pip_install("pandas==1.1.5")
pip_install("openai")
pip_install("requests")

# Full Google API stack (namespace-safe versions)
pip_install("google-api-python-client")
pip_install("google-auth")
pip_install("google-auth-oauthlib")
pip_install("google-auth-httplib2")

# Other useful AI libraries (future expansions)
pip_install("aiohttp")
pip_install("scipy")
