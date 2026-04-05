"""Add parent src directory to sys.path so handler/db/utils can be imported."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
