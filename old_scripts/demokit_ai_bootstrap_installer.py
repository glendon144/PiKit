
#!/usr/bin/env python3

import subprocess
import sys

def pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Upgrade pip itself
pip_install("pip --upgrade")

# Core DemoKit dependencies
pip_install("pandas")
pip_install("openai")
pip_install("tiktoken")
pip_install("requests")

# Full Google API stack to avoid namespace errors
pip_install("google-api-python-client")
pip_install("google-auth")
pip_install("google-auth-oauthlib")
pip_install("google-auth-httplib2")

# Other useful AI libraries (future expansions)
pip_install("aiohttp")
pip_install("numpy")
pip_install("scipy")
