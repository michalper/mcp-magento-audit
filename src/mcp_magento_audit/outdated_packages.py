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

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._process import extract_json as _extract_json
from ._process import run as _run_process
from ._process import run_composer_json as _run_composer_json

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
    return tuple(
        OutdatedPackage(
            package=str(entry.get("name", "")),
            current=str(entry.get("version", "")),
            latest=str(entry.get("latest", "")),
            status=str(entry.get("latest-status", "")),
        )
        for entry in report.get("installed") or []
    )


def _empty(reason: str) -> OutdatedPackagesResult:
    return OutdatedPackagesResult(scanned=False, reason=reason, outdated_count=0, packages=())


def check(project_path: Path) -> OutdatedPackagesResult:
    if not (project_path / "composer.lock").is_file():
        return _empty("no composer.lock in project — nothing to check")

    # No --all: composer already excludes up-to-date packages from this
    # output, which is exactly the filtering this tool wants.
    packages, reason = _run_composer_json(
        project_path,
        subcommand="outdated",
        extra_args=["--format=json", "--no-interaction"],
        runner=_run,
        parse=_parse_report,
    )
    if reason is not None or packages is None:
        return _empty(reason or "composer outdated did not return a valid report")

    # `outdated_count` is the true total; `packages` itself is capped so a
    # long-neglected project can't blow up the result size while still
    # letting the caller see how much worse it actually is.
    return OutdatedPackagesResult(
        scanned=True,
        reason=None,
        outdated_count=len(packages),
        packages=packages[:MAX_STORED_PACKAGES],
    )
