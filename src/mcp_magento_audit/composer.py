"""Read Magento project state from Composer files.

Pure Composer layer — deliberately free of anything Magento-specific, so it
could later be split out into a tool for any PHP project.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProjectError(Exception):
    """The project does not exist or does not look like a Composer project."""


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    requires: dict[str, str] = field(default_factory=dict)
    abandoned: bool = False

    @property
    def php_requirement(self) -> str | None:
        return self.requires.get("php")


@dataclass(frozen=True)
class Project:
    path: Path
    packages: tuple[Package, ...]
    project_php_requirement: str | None

    @property
    def magento_version(self) -> str | None:
        """Version taken from the Magento product package, if the project has one."""
        candidates = ("magento/product-community-edition", "magento/product-enterprise-edition")
        for candidate in candidates:
            for p in self.packages:
                if p.name == candidate:
                    return p.version
        return None

    @property
    def abandoned_packages(self) -> tuple[Package, ...]:
        return tuple(p for p in self.packages if p.abandoned)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ProjectError(f"{path.name} does not contain a JSON object")
        return data
    except FileNotFoundError as e:
        raise ProjectError(f"missing file {path.name} in {path.parent}") from e
    except json.JSONDecodeError as e:
        raise ProjectError(f"{path.name} is not valid JSON: {e}") from e


def load_project(directory: str | Path) -> Project:
    """Loads composer.json and composer.lock from a project directory."""
    dir_path = Path(directory).expanduser().resolve()
    if not dir_path.is_dir():
        raise ProjectError(f"{dir_path} is not a directory")

    composer = _load_json(dir_path / "composer.json")
    lock = _load_json(dir_path / "composer.lock")

    abandoned = set(lock.get("abandoned") or {})

    packages: list[Package] = []
    for group in ("packages", "packages-dev"):
        for entry in lock.get(group) or []:
            name = entry.get("name", "")
            packages.append(
                Package(
                    name=name,
                    version=entry.get("version", "?"),
                    requires={k: str(v) for k, v in (entry.get("require") or {}).items()},
                    abandoned=name in abandoned or bool(entry.get("abandoned")),
                )
            )

    return Project(
        path=dir_path,
        packages=tuple(packages),
        project_php_requirement=(composer.get("require") or {}).get("php"),
    )
