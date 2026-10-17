"""Scan a project's custom code for Magento rule violations.

Shells out to the audited project's own tools instead of reimplementing
deprecated-API detection or type analysis:

- `vendor/bin/phpcs` with the `Magento2` coding standard (from
  `magento/magento-coding-standard`) — legacy API usage, PHP-compatibility
  and security sniffs.
- `vendor/bin/phpstan` (typically with `bitexpert/phpstan-magento`) — type
  errors and misuse of Magento's DI/plugin/interceptor magic that phpcs's
  pattern-based sniffs can't see.

Both are only run against the project's *own* configuration
(`phpcs.xml`/`phpcs.xml.dist`, `phpstan.neon`/`.dist`) when present, instead
of forcing ours — agencies commonly tune these (excluded sniffs, baselines,
a narrower scan scope). phpcs has an official bare `--standard=Magento2`
fallback for projects without their own config; phpstan has no equivalent
(no `paths`/level/extensions to guess), so it is skipped entirely without
one, rather than guessing.

`issue_count` on the result is always the true total found by each tool;
the `issues` list itself is capped per tool (`MAX_STORED_ISSUES_PER_TOOL`) so
one badly-neglected module can't blow up the result size while still
letting the caller see how much worse it actually is than what's shown.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._process import run as _run_process

STANDARD = "Magento2"
FALLBACK_TARGET = "app/code"
TIMEOUT_SECONDS = 120
MAX_STORED_ISSUES_PER_TOOL = 50
PHPCS_CONFIG_FILE_NAMES = ("phpcs.xml", "phpcs.xml.dist")
PHPSTAN_CONFIG_FILE_NAMES = ("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon")


@dataclass(frozen=True)
class Issue:
    tool: str  # "phpcs" | "phpstan"
    file: str
    line: int
    severity: str  # "error" | "warning"
    source: str
    message: str


@dataclass(frozen=True)
class ToolRun:
    scanned: bool
    reason: str | None
    target: str


@dataclass(frozen=True)
class ModuleRiskResult:
    phpcs: ToolRun
    phpstan: ToolRun
    issue_count: int
    issues: tuple[Issue, ...]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, TIMEOUT_SECONDS)


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


def _parse_phpcs_report(stdout: str, project_path: Path) -> tuple[Issue, ...]:
    report: Any = json.loads(stdout)
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
                )
            )
    return tuple(issues)


def _parse_phpstan_report(stdout: str, project_path: Path) -> tuple[Issue, ...]:
    report: Any = json.loads(stdout)
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


def _execute(
    *,
    binary_path: Path,
    binary_label: str,
    install_hint: str,
    args: list[str],
    project_path: Path,
    target: str,
    parse: Callable[[str, Path], tuple[Issue, ...]],
) -> tuple[ToolRun, tuple[Issue, ...]]:
    if not binary_path.is_file():
        location = binary_path.relative_to(project_path)
        reason = f"{binary_label} not found at {location} — install it with `{install_hint}`"
        return ToolRun(scanned=False, reason=reason, target=target), ()

    try:
        result = _run(args, project_path)
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
        args=[str(phpstan_path), "analyse", "--no-progress", "--error-format=json"],
        project_path=project_path,
        target=config.name,
        parse=_parse_phpstan_report,
    )


def _cap(issues: tuple[Issue, ...]) -> tuple[Issue, ...]:
    """Caps the stored issues, keeping errors over warnings when truncating
    (insertion order alone could bury a real error behind earlier warnings)."""
    prioritized = sorted(issues, key=lambda i: i.severity != "error")
    return tuple(prioritized[:MAX_STORED_ISSUES_PER_TOOL])


def scan(project_path: Path) -> ModuleRiskResult:
    phpcs_run, phpcs_issues = _run_phpcs(project_path)
    phpstan_run, phpstan_issues = _run_phpstan(project_path)

    issue_count = len(phpcs_issues) + len(phpstan_issues)
    issues = _cap(phpcs_issues) + _cap(phpstan_issues)

    return ModuleRiskResult(
        phpcs=phpcs_run, phpstan=phpstan_run, issue_count=issue_count, issues=issues
    )
