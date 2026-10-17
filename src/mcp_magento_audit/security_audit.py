"""Checks a project's installed packages for known security advisories.

Shells out to `composer audit` instead of reimplementing a CVE database —
it already reads the project's own `composer.lock` and checks every
installed package (core Magento, third-party extensions in `vendor/`, dev
dependencies) against `FriendsOfPHP/security-advisories`. This covers the
one axis `module_risk` deliberately doesn't: `module_risk` only scans
`app/code` for coding-standard/static-analysis issues, because custom code
has no CVE database to check against in the first place — `vendor/` is the
other way around, it has no custom code worth linting, but every package in
it is a candidate for a known, catalogued vulnerability.

Unlike `vendor/bin/phpcs`/`phpstan`/`rector`, `composer` itself isn't a dev
dependency declared in the project (it's the tool that installed
`composer.lock` in the first place), so it's resolved from PATH or a
`composer.phar` in the project root — not `vendor/bin/` (see
`_process.find_composer`, shared with `outdated_packages`).
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
MAX_STORED_ADVISORIES = 50


@dataclass(frozen=True)
class Advisory:
    package: str
    advisory_id: str
    title: str
    cve: str | None
    severity: str | None
    link: str


@dataclass(frozen=True)
class SecurityAuditResult:
    scanned: bool
    reason: str | None
    advisory_count: int
    advisories: tuple[Advisory, ...]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, TIMEOUT_SECONDS)


def _parse_report(stdout: str) -> tuple[Advisory, ...]:
    report: Any = _extract_json(stdout)
    advisories: list[Advisory] = []
    for package, entries in (report.get("advisories") or {}).items():
        advisories.extend(
            Advisory(
                package=str(package),
                advisory_id=str(entry.get("advisoryId", "")),
                title=str(entry.get("title", "")),
                cve=entry.get("cve") or None,
                severity=entry.get("severity") or None,
                link=str(entry.get("link", "")),
            )
            for entry in entries or []
        )
    return tuple(advisories)


def _empty(reason: str) -> SecurityAuditResult:
    return SecurityAuditResult(scanned=False, reason=reason, advisory_count=0, advisories=())


def audit(project_path: Path) -> SecurityAuditResult:
    if not (project_path / "composer.lock").is_file():
        return _empty("no composer.lock in project — nothing to audit")

    composer_path = _find_composer(project_path)
    if composer_path is None:
        reason = (
            "composer not found on PATH and no composer.phar in project — "
            "install it: https://getcomposer.org/download/"
        )
        return _empty(reason)

    args = [str(composer_path), "audit", "--format=json", "--no-interaction"]
    try:
        result = _run(args, project_path)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _empty(f"could not run composer audit: {e}")

    try:
        advisories = _parse_report(result.stdout)
    except (json.JSONDecodeError, AttributeError):
        detail = result.stderr.strip() or result.stdout.strip()
        return _empty(f"composer audit did not return a valid report: {detail}")

    # `advisory_count` is the true total; `advisories` itself is capped so a
    # project with a long-neglected vendor/ can't blow up the result size
    # while still letting the caller see how much worse it actually is.
    return SecurityAuditResult(
        scanned=True,
        reason=None,
        advisory_count=len(advisories),
        advisories=advisories[:MAX_STORED_ADVISORIES],
    )
