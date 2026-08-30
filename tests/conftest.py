import sys
from pathlib import Path

# Make sure tests can import the app package without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))