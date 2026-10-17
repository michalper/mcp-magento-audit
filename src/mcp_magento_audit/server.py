"""MCP server — Magento project audit tools.

NOTE: in SDK `mcp` 2.x the class is called MCPServer (it was FastMCP in 1.x).
"""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .composer import ProjectError, load_project
from .fleet import overview as build_fleet_overview
from .module_risk import scan as scan_module_risk
from .outdated_packages import check as check_outdated
from .release_notes import release_notes_for_version
from .security_audit import audit as audit_security
from .updates import check
from .upgrade_plan import build as build_upgrade_plan

try:
    _VERSION = version("mcp-magento-audit")
except PackageNotFoundError:
    _VERSION = ""

server = MCPServer(
    name="mcp-magento-audit",
    version=_VERSION,
    instructions=(
        "Magento project audit: compatibility with a target PHP/Magento version, "
        "quality of custom modules, dependency security. "
        "Tools read the files of the project pointed to by the user — "
        "never guess the project's state, always call the tool."
    ),
)


@server.tool(
    description=(
        "Reads composer.json and composer.lock of the given Magento project and "
        "returns its state: Magento version, PHP requirement, package count and "
        "the list of packages abandoned by their authors."
    )
)
def project_status(path: str) -> dict[str, Any]:
    """Returns the basic state of the project at `path`."""
    try:
        project = load_project(path)
    except ProjectError as e:
        return {"error": str(e)}

    return {
        "path": str(project.path),
        "magento_version": project.magento_version,
        "php_requirement": project.project_php_requirement,
        "package_count": len(project.packages),
        "abandoned": [p.name for p in project.abandoned_packages],
    }


@server.tool(
    description=(
        "Checks the given Magento project against a target PHP and Magento version, "
        "with two independent signals: a per-package verdict ('ok', 'blocks' or "
        "'unknown') from declared composer.lock PHP requirements, and code_compatibility "
        "— whether the project's own code would actually need changes under the target "
        "PHP, via a Rector dry-run (declared requirements are often just '*', which alone "
        "gives a false sense of readiness). The PHP requirement for the target Magento "
        "version comes from a local cache, a live fetch, or an offline fallback table, in "
        "that order — the result says which one was used."
    )
)
def check_updates(path: str, target_php: str, target_magento: str) -> dict[str, Any]:
    """Checks `path` against `target_php` and `target_magento`."""
    try:
        project = load_project(path)
    except ProjectError as e:
        return {"error": str(e)}

    result = check(project, target_php=target_php, target_magento=target_magento)

    return asdict(result)


@server.tool(
    description=(
        "Scans the given Magento project's custom code for coding-standard violations, "
        "static-analysis issues and dead-code/quality suggestions by shelling out to the "
        "project's own vendor/bin/phpcs, vendor/bin/phpstan and vendor/bin/rector. phpcs: "
        "if the project has its own phpcs.xml(.dist), that configuration is used as-is; "
        "otherwise falls back to the Magento2 standard on app/code. phpstan and rector: "
        "only run if the project has its own phpstan.neon(.dist)/rector.php — unlike phpcs "
        "there is no safe generic fallback (no paths/level/extensions/rule sets to guess), "
        "so they're skipped rather than guessing. rector's findings are reported as "
        "severity=warning (suggestions, not pass/fail violations). A fourth, separate check "
        "(vendor_phpcs) scans third-party vendor/ Magento modules (type magento2-module in "
        "composer.lock, excluding magento/* core) with the bare Magento2 standard — the "
        "scanned package list is in vendor_packages, and those issues carry scope='vendor' "
        "(vs 'app_code' for the rest) so callers can tell code they can fix from code they "
        "can't. A fifth check (object_manager_misuse) is a plain regex scan over app/code's "
        "own .php/.phtml files for ObjectManager::getInstance() — not a phpcs sniff: "
        "magento-coding-standard's only built-in check for this fires solely inside .phtml "
        "templates, not in Model/Block/Helper classes where bypassing constructor DI is "
        "arguably more harmful. A sixth check (core_overrides) flags app/code classes that "
        "redeclare a class already present in vendor/magento/* under the exact same fully "
        "qualified name (a copy-pasted core file, not a legitimate di.xml preference/plugin) "
        "— severity=error, so unlike the previous two it does become an upgrade_plan blocker, "
        "since that silently blocks safely updating the vendor copy it shadows. A seventh "
        "check (dangling_references) flags app/code's own di.xml (preference/plugin), "
        "events.xml (observer), crontab.xml (job), layout XML (block/uiComponent), "
        "indexer.xml and schema.graphqls (@resolver) naming a PHP class that doesn't "
        "resolve to any known class or virtualType — a stale reference left behind by a "
        "rename or removal, invisible to phpcs/phpstan/rector since none of them analyze "
        "XML. severity=warning, not an upgrade_plan blocker. Each tool reports scanned=false "
        "with a reason when it can't run, instead of staying silent."
    )
)
def module_risk(path: str) -> dict[str, Any]:
    """Scans the custom code of the project at `path` for rule violations."""
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        return {"error": f"{project_path} is not a directory"}

    return asdict(scan_module_risk(project_path))


@server.tool(
    description=(
        "Checks every installed package in the given Magento project's composer.lock — "
        "core Magento, third-party vendor/ extensions, dev dependencies, not just custom "
        "app/code — against known security advisories via `composer audit`. Returns "
        "scanned=false with a reason (e.g. no composer.lock, composer not found) rather "
        "than silently reporting zero advisories when the check never ran."
    )
)
def security_audit(path: str) -> dict[str, Any]:
    """Checks the installed packages of the project at `path` for known advisories."""
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        return {"error": f"{project_path} is not a directory"}

    return asdict(audit_security(project_path))


@server.tool(
    description=(
        "Checks every installed package in the given Magento project's composer.lock "
        "against `composer outdated` to report which ones have a newer version available "
        "— independent of security_audit (known CVEs) and check_updates (compatibility with "
        "a target PHP/Magento version): a package can be behind on releases with neither of "
        "those issues, and that's still tech debt worth surfacing. Each package's own "
        "latest-status (e.g. semver-safe-update vs update-possible) is included as reported "
        "by Composer. Returns scanned=false with a reason (e.g. no composer.lock, composer "
        "not found) rather than silently reporting zero outdated packages."
    )
)
def outdated_packages(path: str) -> dict[str, Any]:
    """Checks the installed packages of the project at `path` for available updates."""
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        return {"error": f"{project_path} is not a directory"}

    return asdict(check_outdated(project_path))


@server.tool(
    description=(
        "Fetches Magento's own release notes for a given version from the "
        "magento/magento2 GitHub repo's Releases API — never reconstructs them from "
        "training data. Returns found=false with a reason when nothing could be "
        "fetched, rather than guessing what a release might have contained."
    )
)
def fetch_release_notes(version: str) -> dict[str, Any]:
    """Fetches release notes for Magento `version` (e.g. '2.4.7')."""
    return asdict(release_notes_for_version(version))


@server.tool(
    description=(
        "Builds an upgrade plan for the given Magento project against a target PHP and "
        "Magento version by combining check_updates, module_risk, security_audit, "
        "outdated_packages and fetch_release_notes. The verdict is a list of concrete "
        "blockers (composer constraints, code that Rector flags as needing changes, "
        "phpcs/phpstan errors in the project's own app/code, security advisories against "
        "installed packages), each with its own reason — not a single abstract score. "
        "outdated_packages and vendor/-scope module_risk issues are informational only "
        "(included in the full result, not in blockers): being behind on releases, or a "
        "third-party module's own code quality, don't block *this* upgrade the way an "
        "app/code error or a composer constraint does. ready=true only when the blockers "
        "list is empty, but check 'unverified' too: it lists any signal that couldn't run "
        "at all (e.g. phpstan/rector not installed, or composer missing for "
        "security_audit/outdated_packages), which ready=true does not account for."
    )
)
def upgrade_plan(path: str, target_php: str, target_magento: str) -> dict[str, Any]:
    """Builds an upgrade plan for `path` against `target_php` and `target_magento`."""
    try:
        project = load_project(path)
    except ProjectError as e:
        return {"error": str(e)}

    return asdict(build_upgrade_plan(project, target_php=target_php, target_magento=target_magento))


@server.tool(
    description=(
        "Triages many Magento projects at once against a target PHP/Magento version — "
        "'which of these N stores can be upgraded today'. Runs only check_updates per "
        "project (composer-constraint verdicts, plus code_compatibility if the project has "
        "its own rector.php) — deliberately not the full upgrade_plan, since module_risk's "
        "phpcs/phpstan/rector and security_audit's/outdated_packages' composer calls are "
        "each seconds-to-minutes and don't scale across a whole fleet in one call. A project "
        "reported blocked=false here can still have module_risk/security_audit findings that "
        "upgrade_plan would catch — call upgrade_plan per project afterward for the full "
        "picture. A project that fails to load (bad path, missing composer files) is "
        "reported with its own error instead of failing the whole batch."
    )
)
def fleet_overview(paths: list[str], target_php: str, target_magento: str) -> dict[str, Any]:
    """Triages the projects at `paths` against `target_php` and `target_magento`."""
    return asdict(build_fleet_overview(paths, target_php=target_php, target_magento=target_magento))


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
