#!/usr/bin/env python3
"""Bumps the version in pyproject.toml and server.json together.

These are two separate files with three total "version" fields
(pyproject.toml's own, server.json's top-level one, and server.json's
packages[0] one) that all have to match for a release to actually work —
the MCP Registry's server.json publish is validated against the PyPI
package's real published version. Previously done by hand (see the 0.1.1
bump commit); this only touches files, it doesn't tag, push, or publish —
those stay deliberate, separate steps.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
PYPROJECT_VERSION_PATTERN = re.compile(r'^version = "([^"]+)"', re.MULTILINE)
SERVER_JSON_VERSION_PATTERN = re.compile(r'"version": "[^"]+"')


class BumpError(Exception):
    """A bad argument or an unexpected file shape — not a crash."""


def current_version(pyproject_path: Path) -> str:
    match = PYPROJECT_VERSION_PATTERN.search(pyproject_path.read_text())
    if match is None:
        raise BumpError(f"could not find a version field in {pyproject_path}")
    return match.group(1)


def next_version(current: str, arg: str) -> str:
    if VERSION_PATTERN.match(arg):
        new_version = arg
    else:
        major, minor, patch = (int(p) for p in current.split("."))
        if arg == "major":
            new_version = f"{major + 1}.0.0"
        elif arg == "minor":
            new_version = f"{major}.{minor + 1}.0"
        elif arg == "patch":
            new_version = f"{major}.{minor}.{patch + 1}"
        else:
            raise BumpError(f"unknown bump type {arg!r} — use major, minor, patch, or X.Y.Z")

    if not VERSION_PATTERN.match(new_version):
        raise BumpError(f"{new_version!r} is not a valid X.Y.Z version")
    if new_version == current:
        raise BumpError(f"already at {current}")
    return new_version


def bump(pyproject_path: Path, server_json_path: Path, arg: str) -> tuple[str, str]:
    """Updates both files in place. Returns (old_version, new_version)."""
    current = current_version(pyproject_path)
    new_version = next_version(current, arg)

    pyproject_text, count = PYPROJECT_VERSION_PATTERN.subn(
        f'version = "{new_version}"', pyproject_path.read_text(), count=1
    )
    if count != 1:
        raise BumpError(f"could not update the version field in {pyproject_path}")

    server_json_text, count = SERVER_JSON_VERSION_PATTERN.subn(
        f'"version": "{new_version}"', server_json_path.read_text()
    )
    if count != 2:
        raise BumpError(
            f"expected exactly 2 \"version\" fields in {server_json_path}, updated {count} — "
            "check it by hand, the file's shape may have changed"
        )

    # Only write once both transforms succeeded — a partial failure must not
    # leave one file bumped and the other not.
    pyproject_path.write_text(pyproject_text)
    server_json_path.write_text(server_json_text)

    return current, new_version


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <major|minor|patch|X.Y.Z>")

    try:
        current, new_version = bump(PYPROJECT, SERVER_JSON, sys.argv[1])
    except BumpError as e:
        raise SystemExit(str(e)) from e

    print(f"{current} -> {new_version}")
    print(f"Updated: {PYPROJECT.name}, {SERVER_JSON.name} (both version fields)")
    print()
    print("Remaining manual steps:")
    print(f"  git add {PYPROJECT.name} {SERVER_JSON.name}")
    print(f'  git commit -m "Bump to {new_version}"')
    print(f"  git tag v{new_version} && git push origin master v{new_version}")
    print(f"  gh release create v{new_version} --generate-notes  # triggers PyPI publish via CI")
    print("  mcp-publisher publish  # re-publish server.json to the MCP Registry")


if __name__ == "__main__":
    main()
