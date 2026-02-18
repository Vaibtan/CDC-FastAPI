"""Root conftest — ensures local packages are on sys.path for tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Add root so that `control.app.*` works when running from root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# walstream-proto is a sibling directory, not an installed package
proto_path = str(ROOT / "walstream-proto")
if proto_path not in sys.path:
    sys.path.insert(0, proto_path)

# control/app needs to be importable as `app.*`
control_path = str(ROOT / "control")
if control_path not in sys.path:
    sys.path.insert(0, control_path)
