"""Shared helpers for shelling out to a project's own dev tools."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 # nosec B603 - fixed argv, no shell
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def find_composer(project_path: Path) -> Path | None:
    """Resolves the `composer` CLI itself — unlike `vendor/bin/phpcs` and
    friends, it isn't a dev dependency declared in the project (it's the tool
    that installed `composer.lock` in the first place), so it's resolved from
    a `composer.phar` in the project root or from PATH, not `vendor/bin/`."""
    phar = project_path / "composer.phar"
    if phar.is_file():
        return phar
    on_path = shutil.which("composer")
    return Path(on_path) if on_path else None


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
