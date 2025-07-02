
#!/usr/bin/env python3

import subprocess
import sys

def pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Pin openai package to legacy version fully compatible with DemoKit Phase 3 codebase
pip_install("openai==0.28.1")
