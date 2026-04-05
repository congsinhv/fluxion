"""Add parent module directory to sys.path so handler/db/utils can be imported."""

import os
import sys

# Add the module root (device_resolver/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
