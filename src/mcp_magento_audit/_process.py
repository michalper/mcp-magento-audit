"""Shared helpers for shelling out to a project's own dev tools."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 # nosec B603 - fixed argv, no shell
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def extract_json(text: str) -> Any:
    """Parses the first JSON object embedded in `text`, skipping any leading
    noise a CLI tool wrote to stdout before its machine-readable report —
    e.g. phpcs prints its own sniff deprecation notices ("DEPRECATED:
    Scanning CSS/JS files...") before the JSON when a project's ruleset
    still has CSS sniffs enabled; phpstan prints a "Note: Using
    configuration file ..." line in some setups. Confirmed against a real
    phpcs run on a real Magento module's phpcs.xml.dist, not assumed."""
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found in output", text, 0)
    return json.loads(text[start:])
