# Roadmap

## Tools

All five planned tools (`project_status`, `check_updates`, `module_risk`,
`fetch_release_notes`, `upgrade_plan`) are done.

- [x] Rector-based dead-code/quality checks in `module_risk` (the project's own
      `rector.php`, as-is — not the PHP-version compatibility check, which
      is a separate, synthetic-config signal in `check_updates`).

## Distribution

- [ ] Publish to PyPI as `mcp-magento-audit`, then register it on the official MCP
      Registry (`registry.modelcontextprotocol.io`) via `mcp-publisher` — process and
      `server.json` shape already checked, see commit history. Deliberately not done yet;
      revisit once the project is past "early stage".

## Housekeeping

- [x] Polish the README further: badges (license, Python version, ruff, last commit) and
      a trimmed `upgrade_plan` example transcript.
- [x] Add `CONTRIBUTING.md`.
- [x] Add `SECURITY.md`.
- [x] Test coverage measurement (`pytest-cov`) — wired into `pyproject.toml` and CI.
- [x] Security linter (`bandit`) — wired into `pyproject.toml` and CI, reviewed findings
      annotated with `# nosec`.
- [x] Dependency vulnerability scan (`pip-audit`) — wired into CI (network-dependent,
      deliberately not in pre-commit).
- [x] `pre-commit` config — local hooks for ruff/mypy/bandit/pytest, installed via
      `pre-commit install`.
- [ ] Consider widening the ruff ruleset (`RUF`, `PERF`) once the codebase is bigger.
