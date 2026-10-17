"""Shared subprocess runner for shelling out to a project's own dev tools."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 # nosec B603 - fixed argv, no shell
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
