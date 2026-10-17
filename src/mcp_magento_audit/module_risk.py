"""Scan a project's custom code for Magento rule violations.

Shells out to the audited project's own tools instead of reimplementing
deprecated-API detection or type analysis:

- `vendor/bin/phpcs` with the `Magento2` coding standard (from
  `magento/magento-coding-standard`) — legacy API usage, PHP-compatibility
  and security sniffs.
- `vendor/bin/phpstan` (typically with `bitexpert/phpstan-magento`) — type
  errors and misuse of Magento's DI/plugin/interceptor magic that phpcs's
  pattern-based sniffs can't see.
- `vendor/bin/rector` with the project's *own* `rector.php` (dead code,
  code-quality rules — not the PHP-version compatibility check, which lives
  in `php_compatibility.py` with its own, synthetic, throwaway config: a
  target PHP version isn't something a project's own rector.php would be
  tuned for).

All three are only run against the project's *own* configuration
(`phpcs.xml`/`phpcs.xml.dist`, `phpstan.neon`/`.dist`, `rector.php`) when
present, instead of forcing ours — agencies commonly tune these (excluded
sniffs, baselines, a narrower scan scope, skipped rules). phpcs has an
official bare `--standard=Magento2` fallback for projects without their own
config; phpstan and rector have no equivalent (no `paths`/level/extensions,
or rule sets, to guess), so they are skipped entirely without one, rather
than guessing.

A fourth, separate check (`vendor_phpcs`) covers the one thing the three
above deliberately don't: third-party Magento modules installed in
`vendor/` (marketplace extensions, agency-bought modules) rather than
`app/code`. It's phpcs-only, always with the bare `Magento2` standard (never
the project's own `phpcs.xml` — that's tuned for the project's own code, not
a vendor's) — no phpstan or rector, deliberately: static-analysis findings
on someone else's code aren't actionable the same way `app/code`'s are, and
without the project's own bootstrap config, broad phpstan runs over
arbitrary third-party packages are noisy and prone to false positives. The
target packages are discovered from `composer.lock`: every package of type
`magento2-module` that isn't `magento/*` (core, not a third-party module, and
already covered by `security_audit`'s CVE check for known vulnerabilities
rather than coding-standard violations).

`issue_count` on the result is always the true total found by each tool;
the `issues` list itself is capped per tool (`MAX_STORED_ISSUES_PER_TOOL`) so
one badly-neglected module can't blow up the result size while still
letting the caller see how much worse it actually is than what's shown.
"""

from __future__ import annotations

import functools
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._process import extract_json as _extract_json
from ._process import run as _run_process
from .composer import ProjectError
from .composer import load_project as _load_project

STANDARD = "Magento2"
FALLBACK_TARGET = "app/code"
TIMEOUT_SECONDS = 120
VENDOR_SCAN_TIMEOUT_SECONDS = 300
MAX_STORED_ISSUES_PER_TOOL = 50
# phpstan's own default (128M) reliably crashes on a real Magento-scale
# project reflecting the full framework (confirmed against a real module) -
# the project's own dev docs already recommend 2G for exactly this reason.
PHPSTAN_MEMORY_LIMIT = "2G"
PHPCS_CONFIG_FILE_NAMES = ("phpcs.xml", "phpcs.xml.dist")
PHPSTAN_CONFIG_FILE_NAMES = ("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon")
RECTOR_CONFIG_FILE_NAMES = ("rector.php",)


@dataclass(frozen=True)
class Issue:
    tool: str  # "phpcs" | "phpstan" | "rector"
    file: str
    line: int
    severity: str  # "error" | "warning"
    source: str
    message: str
    scope: str = "app_code"  # "app_code" | "vendor"


@dataclass(frozen=True)
class ToolRun:
    scanned: bool
    reason: str | None
    target: str


@dataclass(frozen=True)
class ModuleRiskResult:
    phpcs: ToolRun
    phpstan: ToolRun
    rector: ToolRun
    vendor_phpcs: ToolRun
    vendor_packages: tuple[str, ...]
    issue_count: int
    issues: tuple[Issue, ...]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, TIMEOUT_SECONDS)


def _run_vendor(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, VENDOR_SCAN_TIMEOUT_SECONDS)


def _relative(file_path: str, project_path: Path) -> str:
    try:
        return str(Path(file_path).relative_to(project_path))
    except ValueError:
        return file_path


def _find_config(project_path: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = project_path / name
        if candidate.is_file():
            return candidate
    return None


def _parse_phpcs_report(
    stdout: str, project_path: Path, *, scope: str = "app_code"
) -> tuple[Issue, ...]:
    report: Any = _extract_json(stdout)
    issues: list[Issue] = []
    for file_path, file_report in (report.get("files") or {}).items():
        relative = _relative(file_path, project_path)
        for message in file_report.get("messages") or []:
            issues.append(
                Issue(
                    tool="phpcs",
                    file=relative,
                    line=int(message.get("line") or 0),
                    severity=str(message.get("type", "")).lower(),
                    source=str(message.get("source", "")),
                    message=str(message.get("message", "")),
                    scope=scope,
                )
            )
    return tuple(issues)


def _parse_phpstan_report(stdout: str, project_path: Path) -> tuple[Issue, ...]:
    report: Any = _extract_json(stdout)
    issues: list[Issue] = []
    for file_path, file_report in (report.get("files") or {}).items():
        relative = _relative(file_path, project_path)
        for message in file_report.get("messages") or []:
            issues.append(
                Issue(
                    tool="phpstan",
                    file=relative,
                    line=int(message.get("line") or 0),
                    severity="error",
                    source=str(message.get("identifier", "")),
                    message=str(message.get("message", "")),
                )
            )
    # Generic errors not attached to a specific file (e.g. config problems,
    # autoload failures) — not tied to one module's code, but still a real
    # finding that would otherwise silently vanish.
    for generic_error in report.get("errors") or []:
        message = (
            str(generic_error.get("message", generic_error))
            if isinstance(generic_error, dict)
            else str(generic_error)
        )
        issues.append(
            Issue(tool="phpstan", file="", line=0, severity="error", source="", message=message)
        )
    return tuple(issues)


def _parse_rector_report(stdout: str, project_path: Path) -> tuple[Issue, ...]:
    report: Any = _extract_json(stdout)
    issues: list[Issue] = []
    for file_diff in report.get("file_diffs") or []:
        # rector reports paths already relative to `cwd` (= project_path) —
        # unlike phpcs/phpstan, which report absolute paths.
        relative = str(file_diff.get("file", ""))
        for change in file_diff.get("changes") or []:
            rule = str(change.get("rector", ""))
            issues.append(
                Issue(
                    tool="rector",
                    file=relative,
                    line=int(change.get("line") or 0),
                    severity="warning",  # a dry-run suggestion, not a pass/fail violation
                    source=rule,
                    message=f"{rule} would change this",
                )
            )
    return tuple(issues)


def _execute(
    *,
    binary_path: Path,
    binary_label: str,
    install_hint: str,
    args: list[str],
    project_path: Path,
    target: str,
    parse: Callable[[str, Path], tuple[Issue, ...]],
    runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]],
) -> tuple[ToolRun, tuple[Issue, ...]]:
    if not binary_path.is_file():
        location = binary_path.relative_to(project_path)
        reason = f"{binary_label} not found at {location} — install it with `{install_hint}`"
        return ToolRun(scanned=False, reason=reason, target=target), ()

    try:
        result = runner(args, project_path)
    except (OSError, subprocess.TimeoutExpired) as e:
        reason = f"could not run {binary_label}: {e}"
        return ToolRun(scanned=False, reason=reason, target=target), ()

    try:
        issues = parse(result.stdout, project_path)
    except (json.JSONDecodeError, AttributeError):
        detail = result.stderr.strip() or result.stdout.strip()
        reason = f"{binary_label} did not return a valid report: {detail}"
        return ToolRun(scanned=False, reason=reason, target=target), ()

    return ToolRun(scanned=True, reason=None, target=target), issues


def _run_phpcs(project_path: Path) -> tuple[ToolRun, tuple[Issue, ...]]:
    config = _find_config(project_path, PHPCS_CONFIG_FILE_NAMES)

    if config is not None:
        extra_args: list[str] = []
        target = config.name
    else:
        target_dir = project_path / "app" / "code"
        if not target_dir.is_dir():
            return ToolRun(scanned=True, reason=None, target=FALLBACK_TARGET), ()
        extra_args = [f"--standard={STANDARD}", str(target_dir)]
        target = FALLBACK_TARGET

    phpcs_path = project_path / "vendor" / "bin" / "phpcs"
    return _execute(
        binary_path=phpcs_path,
        binary_label="phpcs",
        install_hint="composer require --dev magento/magento-coding-standard",
        args=[str(phpcs_path), "--report=json", *extra_args],
        project_path=project_path,
        target=target,
        parse=_parse_phpcs_report,
        runner=_run,
    )


def _run_phpstan(project_path: Path) -> tuple[ToolRun, tuple[Issue, ...]]:
    config = _find_config(project_path, PHPSTAN_CONFIG_FILE_NAMES)
    if config is None:
        reason = "no phpstan.neon(.dist) in project — skipping static analysis"
        return ToolRun(scanned=False, reason=reason, target=""), ()

    phpstan_path = project_path / "vendor" / "bin" / "phpstan"
    return _execute(
        binary_path=phpstan_path,
        binary_label="phpstan",
        install_hint="composer require --dev phpstan/phpstan",
        args=[
            str(phpstan_path),
            "analyse",
            "--no-progress",
            "--error-format=json",
            f"--memory-limit={PHPSTAN_MEMORY_LIMIT}",
        ],
        project_path=project_path,
        target=config.name,
        parse=_parse_phpstan_report,
        runner=_run,
    )


def _run_rector(project_path: Path) -> tuple[ToolRun, tuple[Issue, ...]]:
    config = _find_config(project_path, RECTOR_CONFIG_FILE_NAMES)
    if config is None:
        reason = "no rector.php in project — skipping dead-code/quality checks"
        return ToolRun(scanned=False, reason=reason, target=""), ()

    rector_path = project_path / "vendor" / "bin" / "rector"
    return _execute(
        binary_path=rector_path,
        binary_label="rector",
        install_hint="composer require --dev rector/rector",
        # No --config override: unlike php_compatibility.py's synthetic,
        # throwaway config, this deliberately uses whatever rule sets the
        # project's own rector.php picked (dead code, code quality, ...).
        args=[
            str(rector_path),
            "process",
            "--dry-run",
            "--no-progress-bar",
            "--output-format=json",
        ],
        project_path=project_path,
        target=config.name,
        parse=_parse_rector_report,
        runner=_run,
    )


def _discover_vendor_modules(project_path: Path) -> list[Path] | None:
    """Third-party (non-`magento/*`) `magento2-module` packages actually
    present under `vendor/`. Returns None when composer.lock/composer.json
    couldn't be read at all (can't determine the target list — different
    from a project that has them but legitimately has no such packages)."""
    try:
        project = _load_project(project_path)
    except ProjectError:
        return None

    targets = []
    for package in project.packages:
        if package.type != "magento2-module" or package.name.startswith("magento/"):
            continue
        package_dir = project_path / "vendor" / package.name
        if package_dir.is_dir():
            targets.append(package_dir)
    return targets


def _run_vendor_phpcs(project_path: Path) -> tuple[ToolRun, tuple[Path, ...], tuple[Issue, ...]]:
    targets = _discover_vendor_modules(project_path)
    if targets is None:
        reason = (
            "no composer.json/composer.lock — can't determine third-party vendor/ Magento modules"
        )
        return ToolRun(scanned=False, reason=reason, target=""), (), ()
    if not targets:
        return ToolRun(scanned=True, reason=None, target="vendor"), (), ()

    phpcs_path = project_path / "vendor" / "bin" / "phpcs"
    target_desc = f"vendor ({len(targets)} third-party magento2-module package(s))"
    run, issues = _execute(
        binary_path=phpcs_path,
        binary_label="phpcs",
        install_hint="composer require --dev magento/magento-coding-standard",
        # Bare --standard=Magento2, never the project's own phpcs.xml — that
        # ruleset is tuned for the project's own code, not a vendor's.
        args=[str(phpcs_path), "--report=json", f"--standard={STANDARD}", *map(str, targets)],
        project_path=project_path,
        target=target_desc,
        parse=functools.partial(_parse_phpcs_report, scope="vendor"),
        runner=_run_vendor,
    )
    return run, tuple(targets), issues


def _cap(issues: tuple[Issue, ...]) -> tuple[Issue, ...]:
    """Caps the stored issues, keeping errors over warnings when truncating
    (insertion order alone could bury a real error behind earlier warnings)."""
    prioritized = sorted(issues, key=lambda i: i.severity != "error")
    return tuple(prioritized[:MAX_STORED_ISSUES_PER_TOOL])


def scan(project_path: Path) -> ModuleRiskResult:
    phpcs_run, phpcs_issues = _run_phpcs(project_path)
    phpstan_run, phpstan_issues = _run_phpstan(project_path)
    rector_run, rector_issues = _run_rector(project_path)
    vendor_phpcs_run, vendor_packages, vendor_phpcs_issues = _run_vendor_phpcs(project_path)

    issue_count = (
        len(phpcs_issues) + len(phpstan_issues) + len(rector_issues) + len(vendor_phpcs_issues)
    )
    issues = (
        _cap(phpcs_issues) + _cap(phpstan_issues) + _cap(rector_issues) + _cap(vendor_phpcs_issues)
    )

    return ModuleRiskResult(
        phpcs=phpcs_run,
        phpstan=phpstan_run,
        rector=rector_run,
        vendor_phpcs=vendor_phpcs_run,
        vendor_packages=tuple(str(p.relative_to(project_path)) for p in vendor_packages),
        issue_count=issue_count,
        issues=issues,
    )
