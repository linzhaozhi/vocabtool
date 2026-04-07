# Pytest configuration: add parent directory to path so modules can be imported.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
