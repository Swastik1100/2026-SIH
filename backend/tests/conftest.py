"""Pytest configuration and shared fixtures."""
import sys
from pathlib import Path

# Ensure backend root is in sys.path for all tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
