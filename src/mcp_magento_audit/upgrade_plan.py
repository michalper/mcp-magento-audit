"""Aggregate check_updates + module_risk + security_audit + outdated_packages
+ fetch_release_notes into one plan.

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
from .outdated_packages import OutdatedPackagesResult
from .outdated_packages import check as check_outdated
from .release_notes import ReleaseNotes, release_notes_for_version
from .security_audit import SecurityAuditResult
from .security_audit import audit as audit_security
from .updates import UpdateCheck
from .updates import check as check_updates


@dataclass(frozen=True)
class Blocker:
    source: str  # "composer" | "code_compatibility" | "phpcs" | "phpstan" | "security"
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
    security_audit: SecurityAuditResult
    outdated_packages: OutdatedPackagesResult


def composer_blockers(update_check: UpdateCheck) -> list[Blocker]:
    """Public: also reused by `fleet.py` for its lightweight, per-project
    triage (composer+code_compatibility only, no module_risk/security_audit
    — those are too slow to run across a whole fleet of projects at once)."""
    return [
        Blocker(source="composer", description=v.package, detail=v.reason)
        for v in update_check.packages
        if v.verdict == "blocks"
    ]


def code_compatibility_blockers(update_check: UpdateCheck) -> list[Blocker]:
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
    # vendor-scope issues (third-party code) are deliberately excluded: they
    # aren't something the project's own team can fix, so they don't block
    # *this* upgrade the way an app/code error does — they're still visible
    # in module_risk.issues for anyone deciding whether to keep that vendor.
    return [
        Blocker(source=issue.tool, description=f"{issue.file}:{issue.line}", detail=issue.message)
        for issue in risk.issues
        if issue.severity == "error" and issue.scope == "app_code"
    ]


def _security_blockers(security: SecurityAuditResult) -> list[Blocker]:
    return [
        Blocker(
            source="security",
            description=advisory.package,
            detail=f"{advisory.cve or advisory.advisory_id}: {advisory.title}",
        )
        for advisory in security.advisories
    ]


def _unverified_signals(
    update_check: UpdateCheck,
    risk: ModuleRiskResult,
    security: SecurityAuditResult,
    outdated: OutdatedPackagesResult,
) -> list[str]:
    unverified = []
    compat = update_check.code_compatibility
    if not compat.checked:
        unverified.append(f"code_compatibility: {compat.reason}")
    if not risk.phpcs.scanned:
        unverified.append(f"phpcs: {risk.phpcs.reason}")
    if not risk.phpstan.scanned:
        unverified.append(f"phpstan: {risk.phpstan.reason}")
    if not risk.rector.scanned:
        unverified.append(f"rector: {risk.rector.reason}")
    if not risk.vendor_phpcs.scanned:
        unverified.append(f"vendor_phpcs: {risk.vendor_phpcs.reason}")
    if not risk.object_manager_misuse.scanned:
        unverified.append(f"object_manager_misuse: {risk.object_manager_misuse.reason}")
    if not risk.core_overrides.scanned:
        unverified.append(f"core_overrides: {risk.core_overrides.reason}")
    if not security.scanned:
        unverified.append(f"security_audit: {security.reason}")
    if not outdated.scanned:
        unverified.append(f"outdated_packages: {outdated.reason}")
    return unverified


def build(project: Project, target_php: str, target_magento: str) -> UpgradePlan:
    with ThreadPoolExecutor(max_workers=5) as executor:
        update_check_future = executor.submit(
            check_updates, project, target_php=target_php, target_magento=target_magento
        )
        risk_future = executor.submit(scan_module_risk, project.path)
        notes_future = executor.submit(release_notes_for_version, target_magento)
        security_future = executor.submit(audit_security, project.path)
        outdated_future = executor.submit(check_outdated, project.path)

        update_check = update_check_future.result()
        risk = risk_future.result()
        notes = notes_future.result()
        security = security_future.result()
        outdated = outdated_future.result()

    blockers = [
        *composer_blockers(update_check),
        *code_compatibility_blockers(update_check),
        *_quality_blockers(risk),
        *_security_blockers(security),
    ]
    unverified = _unverified_signals(update_check, risk, security, outdated)

    return UpgradePlan(
        target_php=target_php,
        target_magento=target_magento,
        ready=len(blockers) == 0,
        blockers=tuple(blockers),
        unverified=tuple(unverified),
        release_notes=notes,
        update_check=update_check,
        module_risk=risk,
        security_audit=security,
        outdated_packages=outdated,
    )
