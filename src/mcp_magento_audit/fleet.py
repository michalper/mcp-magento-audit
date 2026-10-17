"""Aggregate a lightweight upgrade-readiness triage across many projects.

The question agencies actually ask isn't "is this one store ready" — it's
"which of our twenty stores can be upgraded today, and which need work
first". Answering that over N projects with the full `upgrade_plan` (which
also runs `module_risk`'s phpcs/phpstan/rector and `security_audit`'s/
`outdated_packages`' network-bound `composer` calls) doesn't scale: those are
each seconds-to-minutes per project, multiplied by a fleet.

This instead runs only `check_updates` per project — the composer-constraint
and (if the project has its own `rector.php`) code_compatibility signals,
both already fast for the common case (no project-specific config found is a
no-op, not a slow fallback scan). That's enough for a first triage: "ready to
look at closer" vs "already know it blocks". It is deliberately *not* the
same `ready` as `upgrade_plan` — a project reported not-blocked here can
still have module_risk/security_audit findings that `upgrade_plan` would
catch. Call `upgrade_plan` per project afterward for the full picture.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .composer import ProjectError, load_project
from .updates import check as check_updates
from .upgrade_plan import Blocker, code_compatibility_blockers, composer_blockers

MAX_WORKERS = 8


@dataclass(frozen=True)
class ProjectOverview:
    path: str
    error: str | None
    magento_version: str | None
    php_requirement: str | None
    package_count: int
    abandoned_count: int
    composer_summary: dict[str, int]
    blocked: bool
    blockers: tuple[Blocker, ...]


@dataclass(frozen=True)
class FleetOverview:
    target_php: str
    target_magento: str
    total: int
    loaded: int
    errored: int
    blocked: int
    not_blocked: int
    projects: tuple[ProjectOverview, ...]


def _empty_overview(path: str, reason: str) -> ProjectOverview:
    return ProjectOverview(
        path=path,
        error=reason,
        magento_version=None,
        php_requirement=None,
        package_count=0,
        abandoned_count=0,
        composer_summary={},
        blocked=False,
        blockers=(),
    )


def _one(path: str, target_php: str, target_magento: str) -> ProjectOverview:
    try:
        project = load_project(path)
    except ProjectError as e:
        return _empty_overview(path, str(e))

    update_check = check_updates(project, target_php=target_php, target_magento=target_magento)
    blockers = tuple(
        [*composer_blockers(update_check), *code_compatibility_blockers(update_check)]
    )

    return ProjectOverview(
        path=str(project.path),
        error=None,
        magento_version=project.magento_version,
        php_requirement=project.project_php_requirement,
        package_count=len(project.packages),
        abandoned_count=len(project.abandoned_packages),
        composer_summary=update_check.summary,
        blocked=len(blockers) > 0,
        blockers=blockers,
    )


def overview(paths: Sequence[str], target_php: str, target_magento: str) -> FleetOverview:
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(len(paths), 1))) as executor:
        projects = tuple(
            executor.map(lambda p: _one(p, target_php, target_magento), paths)
        )

    loaded = [p for p in projects if p.error is None]
    errored = [p for p in projects if p.error is not None]
    blocked = [p for p in loaded if p.blocked]

    return FleetOverview(
        target_php=target_php,
        target_magento=target_magento,
        total=len(projects),
        loaded=len(loaded),
        errored=len(errored),
        blocked=len(blocked),
        not_blocked=len(loaded) - len(blocked),
        projects=projects,
    )
