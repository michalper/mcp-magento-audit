"""Checks which installed packages have a newer version available.

Shells out to `composer outdated --format=json` instead of reimplementing
version comparison — it already knows, for every installed package, what the
latest available version is and whether an update is semver-safe. This is a
third, independent signal from the other two: `security_audit` says whether
a package has a known CVE, `check_updates` says whether it's compatible with
a *target* PHP/Magento version — neither says whether the project is simply
behind on releases with no compatibility or security issue (yet). A package
can be outdated with neither of those, and that's still real tech debt worth
surfacing. `composer outdated` already excludes up-to-date packages from its
own output, so this doesn't re-filter beyond what it gives.

Shares `_process.find_composer` with `security_audit` — see that module's
docstring for why `composer` itself isn't resolved from `vendor/bin/`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._process import extract_json as _extract_json
from ._process import find_composer as _find_composer
from ._process import run as _run_process

TIMEOUT_SECONDS = 120
MAX_STORED_PACKAGES = 50


@dataclass(frozen=True)
class OutdatedPackage:
    package: str
    current: str
    latest: str
    status: str  # composer's own "latest-status": semver-safe-update | update-possible | ...


@dataclass(frozen=True)
class OutdatedPackagesResult:
    scanned: bool
    reason: str | None
    outdated_count: int
    packages: tuple[OutdatedPackage, ...]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, TIMEOUT_SECONDS)


def _parse_report(stdout: str) -> tuple[OutdatedPackage, ...]:
    report: Any = _extract_json(stdout)
    packages = []
    for entry in report.get("installed") or []:
        packages.append(
            OutdatedPackage(
                package=str(entry.get("name", "")),
                current=str(entry.get("version", "")),
                latest=str(entry.get("latest", "")),
                status=str(entry.get("latest-status", "")),
            )
        )
    return tuple(packages)


def _empty(reason: str) -> OutdatedPackagesResult:
    return OutdatedPackagesResult(scanned=False, reason=reason, outdated_count=0, packages=())


def check(project_path: Path) -> OutdatedPackagesResult:
    if not (project_path / "composer.lock").is_file():
        return _empty("no composer.lock in project — nothing to check")

    composer_path = _find_composer(project_path)
    if composer_path is None:
        reason = (
            "composer not found on PATH and no composer.phar in project — "
            "install it: https://getcomposer.org/download/"
        )
        return _empty(reason)

    # No --all: composer already excludes up-to-date packages from this
    # output, which is exactly the filtering this tool wants.
    args = [str(composer_path), "outdated", "--format=json", "--no-interaction"]
    try:
        result = _run(args, project_path)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _empty(f"could not run composer outdated: {e}")

    try:
        packages = _parse_report(result.stdout)
    except (json.JSONDecodeError, AttributeError):
        detail = result.stderr.strip() or result.stdout.strip()
        return _empty(f"composer outdated did not return a valid report: {detail}")

    # `outdated_count` is the true total; `packages` itself is capped so a
    # long-neglected project can't blow up the result size while still
    # letting the caller see how much worse it actually is.
    return OutdatedPackagesResult(
        scanned=True,
        reason=None,
        outdated_count=len(packages),
        packages=packages[:MAX_STORED_PACKAGES],
    )
