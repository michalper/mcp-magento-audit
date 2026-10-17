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

A fifth check (`object_manager_misuse`) is a plain-Python regex scan over
`app/code`'s own `.php`/`.phtml` files for `ObjectManager::getInstance()` —
not a phpcs sniff. Confirmed directly against `magento/magento-coding-standard`'s
own source (`Magento2/Sniffs/Templates/ObjectManagerSniff.php`): the standard's
*only* built-in check for this is `Magento2.Templates.ObjectManagerUsageFound`,
and it only fires inside `.phtml` templates — direct ObjectManager usage in a
Model/Block/Helper class (arguably the more harmful case, since it bypasses
constructor DI in business logic, not just a template) isn't covered by phpcs
at all. No subprocess involved, so there's no "tool not found" failure mode —
`scanned=false` only if `app/code` itself couldn't be read.

A sixth check (`core_overrides`) flags `app/code` classes that redeclare a
class already present in `vendor/magento/*` under the exact same fully
qualified name — a copy-pasted core file, not a legitimate `di.xml`
`preference`/plugin (those reference the original class, they don't
duplicate it). It's `severity="error"`, so — unlike the two checks above,
both `warning` — it *does* become an `upgrade_plan` blocker: a literal
core-class duplicate silently blocks safely updating the vendor copy it
shadows. Indexes every class in `vendor/magento/*` once by bare class name
(an O(1) dict lookup per app/code candidate, not a filesystem walk per
candidate) before comparing FQCNs. `scanned=false` only if there's no
`vendor/magento` at all — can't rule out an override without a reference
copy of core to compare against.

`issue_count` on the result is always the true total found by each tool;
the `issues` list itself is capped per tool (`MAX_STORED_ISSUES_PER_TOOL`) so
one badly-neglected module can't blow up the result size while still
letting the caller see how much worse it actually is than what's shown.
"""

from __future__ import annotations

import functools
import json
import re
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
OBJECT_MANAGER_PATTERN = re.compile(r"\bObjectManager\s*::\s*getInstance\s*\(")
OBJECT_MANAGER_FILE_EXTENSIONS = (".php", ".phtml")
CLASS_DECLARATION_PATTERN = re.compile(r"\b(?:class|interface|trait)\s+(\w+)")
NAMESPACE_DECLARATION_PATTERN = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.MULTILINE)


@dataclass(frozen=True)
class Issue:
    tool: str  # "phpcs" | "phpstan" | "rector" | "object_manager"
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
    object_manager_misuse: ToolRun
    core_overrides: ToolRun
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


def _scan_object_manager_misuse(project_path: Path) -> tuple[ToolRun, tuple[Issue, ...]]:
    target_dir = project_path / "app" / "code"
    if not target_dir.is_dir():
        return ToolRun(scanned=True, reason=None, target=FALLBACK_TARGET), ()

    issues: list[Issue] = []
    try:
        files = [
            f
            for ext in OBJECT_MANAGER_FILE_EXTENSIONS
            for f in target_dir.rglob(f"*{ext}")
            if f.is_file()
        ]
        for file_path in files:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            for match in OBJECT_MANAGER_PATTERN.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                issues.append(
                    Issue(
                        tool="object_manager",
                        file=_relative(str(file_path), project_path),
                        line=line,
                        severity="warning",
                        source="ObjectManagerUsageFound",
                        message=(
                            "Direct ObjectManager::getInstance() call bypasses dependency "
                            "injection — inject the needed class via the constructor instead."
                        ),
                        scope="app_code",
                    )
                )
    except OSError as e:
        reason = f"could not scan {FALLBACK_TARGET}: {e}"
        return ToolRun(scanned=False, reason=reason, target=""), ()

    return ToolRun(scanned=True, reason=None, target=FALLBACK_TARGET), tuple(issues)


def _declared_classes(file_path: Path) -> list[tuple[str, str]]:
    """Returns (fqcn, class_name) pairs declared in a PHP file — one
    namespace per file is assumed (Magento's own PSR-4 convention), applied
    to every class/interface/trait keyword found in it."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    namespace_match = NAMESPACE_DECLARATION_PATTERN.search(text)
    namespace = namespace_match.group(1) if namespace_match else ""
    declared = []
    for match in CLASS_DECLARATION_PATTERN.finditer(text):
        name = match.group(1)
        fqcn = f"{namespace}\\{name}" if namespace else name
        declared.append((fqcn, name))
    return declared


def _index_classes_by_name(root: Path) -> dict[str, list[tuple[str, Path]]]:
    """One pass over every `.php` file under `root`, indexed by bare class
    name — so looking up whether a given app/code class exists in core is an
    O(1) dict lookup instead of a filesystem walk per candidate."""
    index: dict[str, list[tuple[str, Path]]] = {}
    for php_file in root.rglob("*.php"):
        if not php_file.is_file():
            continue
        for fqcn, name in _declared_classes(php_file):
            index.setdefault(name, []).append((fqcn, php_file))
    return index


def _scan_core_overrides(project_path: Path) -> tuple[ToolRun, tuple[Issue, ...]]:
    app_code_dir = project_path / "app" / "code"
    vendor_magento_dir = project_path / "vendor" / "magento"

    if not app_code_dir.is_dir():
        return ToolRun(scanned=True, reason=None, target=FALLBACK_TARGET), ()
    if not vendor_magento_dir.is_dir():
        reason = "no vendor/magento — can't tell whether app/code redeclares a core class"
        return ToolRun(scanned=False, reason=reason, target=""), ()

    issues: list[Issue] = []
    try:
        vendor_index = _index_classes_by_name(vendor_magento_dir)
        for app_file in app_code_dir.rglob("*.php"):
            if not app_file.is_file():
                continue
            for fqcn, name in _declared_classes(app_file):
                for vendor_fqcn, vendor_file in vendor_index.get(name, ()):
                    if vendor_fqcn != fqcn:
                        continue
                    issues.append(
                        Issue(
                            tool="core_override",
                            file=_relative(str(app_file), project_path),
                            line=1,
                            severity="error",
                            source=fqcn,
                            message=(
                                f"{fqcn} redeclares a class that already exists in "
                                f"{_relative(str(vendor_file), project_path)} — silently "
                                "blocks safe updates to that core file; use a plugin or "
                                "di.xml preference instead of copy-pasting it."
                            ),
                            scope="app_code",
                        )
                    )
    except OSError as e:
        reason = f"could not scan for core overrides: {e}"
        return ToolRun(scanned=False, reason=reason, target=""), ()

    return ToolRun(scanned=True, reason=None, target="app/code vs vendor/magento"), tuple(issues)


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
    object_manager_run, object_manager_issues = _scan_object_manager_misuse(project_path)
    core_overrides_run, core_overrides_issues = _scan_core_overrides(project_path)

    issue_count = (
        len(phpcs_issues)
        + len(phpstan_issues)
        + len(rector_issues)
        + len(vendor_phpcs_issues)
        + len(object_manager_issues)
        + len(core_overrides_issues)
    )
    issues = (
        _cap(phpcs_issues)
        + _cap(phpstan_issues)
        + _cap(rector_issues)
        + _cap(vendor_phpcs_issues)
        + _cap(object_manager_issues)
        + _cap(core_overrides_issues)
    )

    return ModuleRiskResult(
        phpcs=phpcs_run,
        phpstan=phpstan_run,
        rector=rector_run,
        vendor_phpcs=vendor_phpcs_run,
        vendor_packages=tuple(str(p.relative_to(project_path)) for p in vendor_packages),
        object_manager_misuse=object_manager_run,
        core_overrides=core_overrides_run,
        issue_count=issue_count,
        issues=issues,
    )
