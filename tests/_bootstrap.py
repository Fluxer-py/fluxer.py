from __future__ import annotations

import os
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PACKAGE_ROOT.parent
for path in (str(PACKAGE_ROOT), str(WORKSPACE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def load_dev_token() -> str:
    env_paths = (
        WORKSPACE_ROOT / "full_example" / ".env",
        WORKSPACE_ROOT / "test_implementation" / ".env",
    )
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    token = os.getenv("DEV_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DEV_TOKEN is not set in the environment or full_example/.env"
        )
    return token
