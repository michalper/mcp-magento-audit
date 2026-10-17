"""Shared helpers for shelling out to a project's own dev tools."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXEC_PREFIX_ENV_VAR = "MCP_MAGENTO_AUDIT_EXEC_PREFIX"


def exec_prefix() -> list[str]:
    """The optional command every subprocess call here is wrapped in — e.g.
    `ddev exec --` or `docker compose exec -T app` — for a project whose
    PHP/Composer only exist inside a dev container, not on the host this MCP
    server itself runs on. Read fresh on each call rather than cached at
    import time, so it can change between calls in the same process (tests
    set/unset it per-case; a long-running server picks up a changed env
    without a restart). Empty (no wrapping — today's behavior) when unset."""
    return shlex.split(os.environ.get(EXEC_PREFIX_ENV_VAR, ""))


def _relativize(arg: str, cwd: Path) -> str:
    """An absolute host path is meaningless inside a container wrapped
    command points at — but since dev containers bind-mount the project
    directory as a subtree (same relative layout, different root), the same
    path *relative* to the project root resolves correctly there. Only
    rewrites arguments that are themselves an absolute path under `cwd`
    (e.g. `vendor/bin/phpcs`, `app/code`); a flag like `--report=json` or an
    absolute path outside the project (e.g. a host-PATH-resolved binary)
    passes through unchanged."""
    path = Path(arg)
    if not path.is_absolute():
        return arg
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return arg


def run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    prefix = exec_prefix()
    if prefix:
        args = [_relativize(arg, cwd) for arg in args]
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        [*prefix, *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def find_composer(project_path: Path) -> Path | None:
    """Resolves the `composer` CLI itself — unlike `vendor/bin/phpcs` and
    friends, it isn't a dev dependency declared in the project (it's the tool
    that installed `composer.lock` in the first place), so it's resolved from
    a `composer.phar` in the project root or from PATH, not `vendor/bin/`.

    Under an exec prefix, a host-PATH-resolved absolute path (e.g.
    `/opt/homebrew/bin/composer`) is meaningless inside the container and
    isn't under `project_path` for `run()`'s own relativizing to fix — so
    this falls back to the bare command name instead, trusting the
    container's own PATH to resolve it (the same trust this project already
    places in the exec prefix itself being correctly configured)."""
    phar = project_path / "composer.phar"
    if phar.is_file():
        return phar
    if exec_prefix():
        return Path("composer")
    on_path = shutil.which("composer")
    return Path(on_path) if on_path else None


def run_composer_json[T](
    project_path: Path,
    *,
    subcommand: str,
    extra_args: list[str],
    runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]],
    parse: Callable[[str], T],
) -> tuple[T | None, str | None]:
    """Resolves `composer`, runs `subcommand` with `extra_args`, and parses
    its stdout as a JSON report via `parse`. Returns `(parsed, None)` on
    success or `(None, reason)` on any failure (composer not found, the
    subprocess itself failing to run, or an invalid report) — shared by
    `security_audit.audit` and `outdated_packages.check`, whose only real
    difference is the subcommand, the parse function, and the result
    dataclass's field names."""
    composer_path = find_composer(project_path)
    if composer_path is None:
        return None, (
            "composer not found on PATH and no composer.phar in project — "
            "install it: https://getcomposer.org/download/"
        )

    args = [str(composer_path), subcommand, *extra_args]
    try:
        result = runner(args, project_path)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"could not run composer {subcommand}: {e}"

    try:
        return parse(result.stdout), None
    except (json.JSONDecodeError, AttributeError):
        detail = result.stderr.strip() or result.stdout.strip()
        return None, f"composer {subcommand} did not return a valid report: {detail}"


def extract_json(text: str) -> Any:
    """Parses the first JSON object embedded in `text`, skipping any leading
    noise a CLI tool wrote to stdout before its machine-readable report —
    e.g. phpcs prints its own sniff deprecation notices ("DEPRECATED:
    Scanning CSS/JS files...") before the JSON when a project's ruleset
    still has CSS sniffs enabled; phpstan prints a "Note: Using
    configuration file ..." line in some setups. Confirmed against a real
    phpcs run on a real Magento module's phpcs.xml.dist, not assumed."""
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found in output", text, 0)
    return json.loads(text[start:])
