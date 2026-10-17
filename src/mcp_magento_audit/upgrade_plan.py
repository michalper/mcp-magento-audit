"""Aggregate check_updates + module_risk + fetch_release_notes into one plan.

The verdict is a list of concrete blockers with a reason each, not a single
score — easier to act on ("fix this file", "this package blocks it") than a
number, and it doesn't hide which signal actually fired.

`ready` only reflects the signals that actually ran — see `unverified` for
any that didn't (e.g. rector/phpstan not installed), so a caller can't
mistake "nothing was flagged" for "everything was checked".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .composer import Project
from .module_risk import ModuleRiskResult
from .module_risk import scan as scan_module_risk
from .release_notes import ReleaseNotes, release_notes_for_version
from .updates import UpdateCheck
from .updates import check as check_updates


@dataclass(frozen=True)
class Blocker:
    source: str  # "composer" | "code_compatibility" | "phpcs" | "phpstan"
    description: str
    detail: str


@dataclass(frozen=True)
class UpgradePlan:
    target_php: str
    target_magento: str
    ready: bool
    blockers: tuple[Blocker, ...]
    unverified: tuple[str, ...]
    release_notes: ReleaseNotes
    update_check: UpdateCheck
    module_risk: ModuleRiskResult


def _composer_blockers(update_check: UpdateCheck) -> list[Blocker]:
    return [
        Blocker(source="composer", description=v.package, detail=v.reason)
        for v in update_check.packages
        if v.verdict == "blocks"
    ]


def _code_compatibility_blockers(update_check: UpdateCheck) -> list[Blocker]:
    compat = update_check.code_compatibility

    rules_by_file: dict[str, list[str]] = {}
    for change in compat.changes:
        rules_by_file.setdefault(change.file, []).append(change.rector_rule)

    blockers = []
    for file in compat.changed_files:
        rules = sorted(set(rules_by_file.get(file, [])))
        detail = ", ".join(rules) if rules else f"needs changes for PHP {compat.target_php}"
        blockers.append(Blocker(source="code_compatibility", description=file, detail=detail))
    return blockers


def _quality_blockers(risk: ModuleRiskResult) -> list[Blocker]:
    return [
        Blocker(source=issue.tool, description=f"{issue.file}:{issue.line}", detail=issue.message)
        for issue in risk.issues
        if issue.severity == "error"
    ]


def _unverified_signals(update_check: UpdateCheck, risk: ModuleRiskResult) -> list[str]:
    unverified = []
    compat = update_check.code_compatibility
    if not compat.checked:
        unverified.append(f"code_compatibility: {compat.reason}")
    if not risk.phpcs.scanned:
        unverified.append(f"phpcs: {risk.phpcs.reason}")
    if not risk.phpstan.scanned:
        unverified.append(f"phpstan: {risk.phpstan.reason}")
    return unverified


def build(project: Project, target_php: str, target_magento: str) -> UpgradePlan:
    with ThreadPoolExecutor(max_workers=3) as executor:
        update_check_future = executor.submit(
            check_updates, project, target_php=target_php, target_magento=target_magento
        )
        risk_future = executor.submit(scan_module_risk, project.path)
        notes_future = executor.submit(release_notes_for_version, target_magento)

        update_check = update_check_future.result()
        risk = risk_future.result()
        notes = notes_future.result()

    blockers = [
        *_composer_blockers(update_check),
        *_code_compatibility_blockers(update_check),
        *_quality_blockers(risk),
    ]
    unverified = _unverified_signals(update_check, risk)

    return UpgradePlan(
        target_php=target_php,
        target_magento=target_magento,
        ready=len(blockers) == 0,
        blockers=tuple(blockers),
        unverified=tuple(unverified),
        release_notes=notes,
        update_check=update_check,
        module_risk=risk,
    )
