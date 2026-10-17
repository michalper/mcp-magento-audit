"""MCP server — Magento project audit tools.

NOTE: in SDK `mcp` 2.x the class is called MCPServer (it was FastMCP in 1.x).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer

from .composer import ProjectError, load_project
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


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
