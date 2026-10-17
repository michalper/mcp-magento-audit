"""Whether a project's own code would need changes to run under a target PHP
version — via a Rector dry-run, not a guess from declared composer constraints.

Unlike phpcs/phpstan in `module_risk`, this can't reuse the project's own
`rector.php`: that config already targets whatever PHP version its author
picked, not the hypothetical `target_php` this check is asked about. So it
writes its own throwaway config instead, scoped to exactly one
`withPhpSets(phpXY: true)` call.

CLI contract (`vendor/bin/rector process --dry-run --output-format=json`),
the exact JSON shape, and `withPhpSets()`'s named-boolean parameters were all
confirmed against a real Rector 2.7 install and the rectorphp/rector-src
source, not assumed from memory.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._process import extract_json as _extract_json
from ._process import run as _run_process

TIMEOUT_SECONDS = 180

# RectorConfigBuilder::withPhpSets()'s named-boolean parameters (php53..php86).
SUPPORTED_TARGETS = (
    "5.3", "5.4", "5.5", "5.6",
    "7.0", "7.1", "7.2", "7.3", "7.4",
    "8.0", "8.1", "8.2", "8.3", "8.4", "8.5", "8.6",
)


@dataclass(frozen=True)
class PhpCompatibilityChange:
    file: str
    line: int
    rector_rule: str


@dataclass(frozen=True)
class PhpCompatibilityResult:
    checked: bool
    reason: str | None
    target_php: str
    changed_file_count: int
    changed_files: tuple[str, ...]
    changes: tuple[PhpCompatibilityChange, ...]


def _empty(checked: bool, reason: str | None, target_php: str) -> PhpCompatibilityResult:
    return PhpCompatibilityResult(
        checked=checked,
        reason=reason,
        target_php=target_php,
        changed_file_count=0,
        changed_files=(),
        changes=(),
    )


def _php_set_flag(target_php: str) -> str | None:
    """Maps e.g. '8.3' or '8.3.1' to 'php83' — Rector's sets are per
    major.minor, so a patch version (the documented, valid form of
    `target_php` elsewhere, see composer_semver.satisfies) is truncated to
    its first two components rather than rejected outright."""
    parts = target_php.strip().split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    major_minor = f"{parts[0]}.{parts[1]}"
    if major_minor not in SUPPORTED_TARGETS:
        return None
    return "php" + major_minor.replace(".", "")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run_process(args, cwd, TIMEOUT_SECONDS)


def _php_single_quoted(value: str) -> str:
    """Escapes a value for interpolation into a single-quoted PHP string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _write_config(config_path: Path, target_dir: Path, php_set_flag: str) -> None:
    path_literal = _php_single_quoted(str(target_dir))
    config_path.write_text(
        "<?php\n"
        "declare(strict_types=1);\n"
        "use Rector\\Config\\RectorConfig;\n"
        "return RectorConfig::configure()\n"
        f"    ->withPaths(['{path_literal}'])\n"
        f"    ->withPhpSets({php_set_flag}: true);\n",
        encoding="utf-8",
    )


def _parse_report(stdout: str) -> tuple[tuple[str, ...], tuple[PhpCompatibilityChange, ...]]:
    report: Any = _extract_json(stdout)

    # The authoritative, complete list of changed files — Rector always
    # populates this for every file it touched, regardless of whether a
    # per-line diff/changes breakdown is also available for it.
    changed_files = tuple(str(f) for f in report.get("changed_files") or [])

    changes: list[PhpCompatibilityChange] = []
    for file_diff in report.get("file_diffs") or []:
        file_path = str(file_diff.get("file", ""))
        for change in file_diff.get("changes") or []:
            changes.append(
                PhpCompatibilityChange(
                    file=file_path,
                    line=int(change.get("line") or 0),
                    rector_rule=str(change.get("rector", "")),
                )
            )
    return changed_files, tuple(changes)


def check(project_path: Path, target_php: str) -> PhpCompatibilityResult:
    php_set_flag = _php_set_flag(target_php)
    if php_set_flag is None:
        reason = f"PHP {target_php} is not a version Rector has a rule set for"
        return _empty(checked=False, reason=reason, target_php=target_php)

    target_dir = project_path / "app" / "code"
    if not target_dir.is_dir():
        return _empty(checked=True, reason=None, target_php=target_php)

    rector_path = project_path / "vendor" / "bin" / "rector"
    if not rector_path.is_file():
        reason = (
            "rector not found at vendor/bin/rector — install it with "
            "`composer require --dev rector/rector`"
        )
        return _empty(checked=False, reason=reason, target_php=target_php)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "rector.php"
            _write_config(config_path, target_dir, php_set_flag)

            args = [
                str(rector_path),
                "process",
                "--dry-run",
                "--no-progress-bar",
                "--output-format=json",
                f"--config={config_path}",
            ]
            result = _run(args, project_path)
    except OSError as e:
        return _empty(checked=False, reason=f"could not run rector: {e}", target_php=target_php)
    except subprocess.TimeoutExpired as e:
        return _empty(checked=False, reason=f"could not run rector: {e}", target_php=target_php)

    try:
        changed_files, changes = _parse_report(result.stdout)
    except (json.JSONDecodeError, AttributeError):
        detail = result.stderr.strip() or result.stdout.strip()
        reason = f"rector did not return a valid report: {detail}"
        return _empty(checked=False, reason=reason, target_php=target_php)

    return PhpCompatibilityResult(
        checked=True,
        reason=None,
        target_php=target_php,
        changed_file_count=len(changed_files),
        changed_files=changed_files,
        changes=changes,
    )
