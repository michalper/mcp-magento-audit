# Roadmap

## Tools

- `upgrade_plan` — aggregates `check_updates` + `module_risk` + `fetch_release_notes` into
  one ordered plan with concrete blockers (in progress).
- Rector-based checks beyond PHP-version compatibility (dead code, Magento-specific rules)
  — deferred, see chat history / commit messages for the `withPhpSets()` design.

## Housekeeping

- [ ] Polish the README further: badges (license, Python version), maybe a short usage
      example/transcript of an agent calling a tool.
- [ ] Add `CONTRIBUTING.md` (none yet — `LICENSE` already exists, MIT).
- [ ] Add `SECURITY.md` (how to report a vulnerability).
- [ ] Python code-quality tooling gaps to fill:
  - No test coverage measurement (`pytest-cov` / `coverage.py`).
  - No security linter — `ruff`'s `S` (bandit-equivalent) ruleset isn't enabled yet,
    only `E, F, I, UP, B, SIM`.
  - No dependency vulnerability scan (`pip-audit` or similar) in CI.
  - No `pre-commit` config (ruff/mypy/pytest only run in CI today, not on commit).
  - Consider widening the ruff ruleset (`RUF`, `PERF`) once the codebase is bigger.
