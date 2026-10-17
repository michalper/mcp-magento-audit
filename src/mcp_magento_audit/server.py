"""MCP server — Magento project audit tools.

NOTE: in SDK `mcp` 2.x the class is called MCPServer (it was FastMCP in 1.x).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .composer import ProjectError, load_project
from .module_risk import scan as scan_module_risk
from .updates import check

server = MCPServer(
    name="mcp-magento-audit",
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
        "Checks every package of the given Magento project against a target PHP "
        "and Magento version, and returns a per-package verdict ('ok', 'blocks' or "
        "'unknown') plus a summary. The PHP requirement for the target Magento "
        "version comes from a local cache, a live fetch, or an offline fallback "
        "table, in that order — the result says which one was used."
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
        "Scans the given Magento project's custom code for coding-standard violations "
        "and static-analysis issues by shelling out to the project's own vendor/bin/phpcs "
        "and vendor/bin/phpstan. phpcs: if the project has its own phpcs.xml(.dist), that "
        "configuration is used as-is; otherwise falls back to the Magento2 standard on "
        "app/code. phpstan: only run if the project has its own phpstan.neon(.dist) — "
        "unlike phpcs there is no safe generic fallback (no paths/level/extensions to "
        "guess), so it is skipped rather than guessing. Each tool reports scanned=false "
        "with a reason when it can't run, instead of staying silent."
    )
)
def module_risk(path: str) -> dict[str, Any]:
    """Scans the custom code of the project at `path` for rule violations."""
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        return {"error": f"{project_path} is not a directory"}

    return asdict(scan_module_risk(project_path))


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
