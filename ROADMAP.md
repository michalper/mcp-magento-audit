# Roadmap

## Tools

All five planned tools (`project_status`, `check_updates`, `module_risk`,
`fetch_release_notes`, `upgrade_plan`) are done.

- Rector-based checks beyond PHP-version compatibility (dead code, Magento-specific rules)
  — deferred, see commit history for the `withPhpSets()` design.

## Housekeeping

- [ ] Polish the README further: badges (license, Python version), maybe a short usage
      example/transcript of an agent calling a tool.
- [ ] Add `CONTRIBUTING.md` (none yet — `LICENSE` already exists, MIT).
- [ ] Add `SECURITY.md` (how to report a vulnerability).
- [x] Test coverage measurement (`pytest-cov`) — wired into `pyproject.toml` and CI.
- [x] Security linter (`bandit`) — wired into `pyproject.toml` and CI, reviewed findings
      annotated with `# nosec`.
- [x] Dependency vulnerability scan (`pip-audit`) — wired into CI (network-dependent,
      deliberately not in pre-commit).
- [x] `pre-commit` config — local hooks for ruff/mypy/bandit/pytest, installed via
      `pre-commit install`.
- [ ] Consider widening the ruff ruleset (`RUF`, `PERF`) once the codebase is bigger.
