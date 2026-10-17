"""Check each package in a project against a target PHP/Magento version."""

from __future__ import annotations

from dataclasses import dataclass

from .composer import Project
from .composer_semver import ConstraintError, satisfies
from .magento_versions import php_requirement_for_magento


@dataclass(frozen=True)
class PackageVerdict:
    package: str
    php_requirement: str | None
    verdict: str  # "ok" | "blocks" | "unknown"
    reason: str


@dataclass(frozen=True)
class UpdateCheck:
    project_magento_version: str | None
    target_magento: str
    target_php: str
    target_magento_php_requirement: str | None
    php_data_source: str
    packages: tuple[PackageVerdict, ...]
    summary: dict[str, int]


def _verdict_for_package(php_requirement: str | None, target_php: str) -> tuple[str, str]:
    if php_requirement is None:
        return "ok", "package does not declare a PHP requirement"
    try:
        ok = satisfies(php_requirement, target_php)
    except ConstraintError as e:
        return "unknown", f"cannot evaluate requirement {php_requirement!r}: {e}"
    if ok:
        return "ok", f"{php_requirement} covers PHP {target_php}"
    return "blocks", f"{php_requirement} does not cover PHP {target_php}"


def check(project: Project, target_php: str, target_magento: str) -> UpdateCheck:
    magento_php = php_requirement_for_magento(target_magento)

    verdicts: list[PackageVerdict] = []
    for package in project.packages:
        verdict, reason = _verdict_for_package(package.php_requirement, target_php)
        verdicts.append(
            PackageVerdict(
                package=package.name,
                php_requirement=package.php_requirement,
                verdict=verdict,
                reason=reason,
            )
        )

    summary = {"ok": 0, "blocks": 0, "unknown": 0}
    for v in verdicts:
        summary[v.verdict] += 1

    return UpdateCheck(
        project_magento_version=project.magento_version,
        target_magento=target_magento,
        target_php=target_php,
        target_magento_php_requirement=magento_php.php_requirement,
        php_data_source=magento_php.source,
        packages=tuple(verdicts),
        summary=summary,
    )
