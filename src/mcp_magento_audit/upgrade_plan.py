"""Aggregate check_updates + module_risk + fetch_release_notes into one plan.

The verdict is a list of concrete blockers with a reason each, not a single
score — easier to act on ("fix this file", "this package blocks it") than a
number, and it doesn't hide which signal actually fired.
"""

from __future__ import annotations

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
    by_file: dict[str, list[str]] = {}
    for change in update_check.code_compatibility.changes:
        by_file.setdefault(change.file, []).append(change.rector_rule)

    return [
        Blocker(source="code_compatibility", description=file, detail=", ".join(sorted(set(rules))))
        for file, rules in by_file.items()
    ]


def _quality_blockers(risk: ModuleRiskResult) -> list[Blocker]:
    return [
        Blocker(source=issue.tool, description=f"{issue.file}:{issue.line}", detail=issue.message)
        for issue in risk.issues
        if issue.severity == "error"
    ]


def build(project: Project, target_php: str, target_magento: str) -> UpgradePlan:
    update_check = check_updates(project, target_php=target_php, target_magento=target_magento)
    risk = scan_module_risk(project.path)
    notes = release_notes_for_version(target_magento)

    blockers = [
        *_composer_blockers(update_check),
        *_code_compatibility_blockers(update_check),
        *_quality_blockers(risk),
    ]

    return UpgradePlan(
        target_php=target_php,
        target_magento=target_magento,
        ready=len(blockers) == 0,
        blockers=tuple(blockers),
        release_notes=notes,
        update_check=update_check,
        module_risk=risk,
    )
