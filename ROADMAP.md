# Roadmap

## Tools

All seven planned tools (`project_status`, `check_updates`, `module_risk`,
`security_audit`, `outdated_packages`, `fetch_release_notes`, `upgrade_plan`) are done.

- [x] Rector-based dead-code/quality checks in `module_risk` (the project's own
      `rector.php`, as-is — not the PHP-version compatibility check, which
      is a separate, synthetic-config signal in `check_updates`).
- [x] `security_audit`: `composer audit` across every installed package
      (`vendor/`, not just `app/code`), wired as blockers into `upgrade_plan`.
- [x] `module_risk`: scan third-party `vendor/` packages of type
      `magento2-module` (not just core `magento/*`) with `phpcs` for
      coding-standard issues (`vendor_phpcs`) — `security_audit` only covers
      known CVEs, not style/legacy-API violations. phpstan/rector
      deliberately not extended to vendor/ (noisy without the project's own
      bootstrap, and not actionable on someone else's code either way).
      Vendor-scope issues are informational only — excluded from
      `upgrade_plan`'s blockers, since they're not the project's own code to fix.
- [x] `outdated_packages`: shells out to the built-in `composer outdated
      --format=json` (same pattern as `security_audit`, shares
      `_process.find_composer`) to report which installed packages have a
      newer version available — a staleness/tech-debt signal independent of
      CVEs (`security_audit`) and target-version compatibility
      (`check_updates`). Informational in `upgrade_plan`, not a blocker.
- [ ] Multi-project aggregation: a tool that runs the existing per-project
      checks across many project directories at once and aggregates the
      results (e.g. "which of these N stores can be upgraded today") — the
      third differentiator the README already advertises over plain
      `composer audit`, but no tool implements it yet.
- [ ] `module_risk`: surface Object Manager misuse explicitly — the Magento2
      phpcs standard already flags direct `ObjectManager::getInstance()` calls
      (sniff `Magento2.Classes.ObjectManager`) as part of the existing scan,
      but it's buried among generic phpcs issues; worth calling out as its
      own category in the result instead of leaving the caller to notice it.
- [ ] `module_risk`: detect core overrides — `app/code` classes that
      redeclare a class that already exists in `vendor/magento/*` (copy-paste
      of a core file under the same namespace/class name), which silently
      blocks safe upgrades. Unlike Object Manager misuse this isn't a phpcs
      sniff — needs its own check cross-referencing class names declared in
      `app/code` against `vendor/magento/*`, as opposed to legitimate `di.xml`
      preferences/plugins, which don't duplicate the class itself.

## Distribution

- [x] Published to PyPI as `mcp-magento-audit` (0.1.1) and registered on the official MCP
      Registry (`registry.modelcontextprotocol.io`, `io.github.michalper/mcp-magento-audit`,
      status `active`).
- [ ] `server.json`/`pyproject.toml` version bump process for future releases — not yet
      scripted, done by hand so far.

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
