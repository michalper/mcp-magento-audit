# Roadmap

## Tools

All eight planned tools (`project_status`, `check_updates`, `module_risk`,
`security_audit`, `outdated_packages`, `fetch_release_notes`, `upgrade_plan`,
`fleet_overview`) are done.

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
- [x] `fleet_overview`: triages many project directories at once ("which of
      these N stores can be upgraded today") — the third differentiator the
      README advertises over plain `composer audit`. Deliberately lightweight
      (only `check_updates` per project, not the full `upgrade_plan`):
      module_risk's phpcs/phpstan/rector and security_audit's/
      outdated_packages' composer calls are each seconds-to-minutes and
      don't scale across a fleet in one call. A project that fails to load
      is reported with its own error rather than failing the whole batch.
- [x] `module_risk`: `object_manager_misuse` — a plain regex scan over
      `app/code`'s `.php`/`.phtml` files for `ObjectManager::getInstance()`.
      Correction after checking `magento/magento-coding-standard`'s own
      source: there is no `Magento2.Classes.ObjectManager` sniff (an
      assumption from an earlier roadmap entry, not verified at the time).
      The standard's only built-in check for this,
      `Magento2.Templates.ObjectManagerUsageFound`, fires solely inside
      `.phtml` templates — not in Model/Block/Helper classes, arguably the
      more harmful case since it bypasses constructor DI in business logic.
      No subprocess, so no "tool not found" failure mode.
- [x] `module_risk`: `core_overrides` — flags `app/code` classes that
      redeclare a class already present in `vendor/magento/*` under the
      exact same fully qualified name (a copy-pasted core file, not a
      legitimate `di.xml` preference/plugin, which reference the original
      class rather than duplicate it). `severity="error"`, so — unlike
      `object_manager_misuse` — it *does* become an `upgrade_plan` blocker.
      Indexes every class in `vendor/magento/*` once by bare class name (an
      O(1) dict lookup per `app/code` candidate, not a filesystem walk per
      candidate — confirmed fast against a real ~8500-class core tree,
      ~1.3s). `scanned=false` only if there's no `vendor/magento` at all.
- [ ] `module_risk`: flag admin/customer controller actions missing
      `_isAllowed()` (or an always-`true` stub) — not a phpcs sniff, needs
      its own AST-ish check over `app/code`'s `Controller/Adminhtml` and
      customer-area action classes. Deliberately not pursuing N+1-query
      detection or "service contracts vs. direct collection access" —
      those need real dataflow analysis, not AST/pattern matching, and would
      be too false-positive-prone at the level this project operates.
- [ ] `module_risk`: flag empty `catch (...) {}` blocks and discouraged debug
      calls (`var_dump`/`print_r`/`echo`/`die` left in production code) —
      cheap, low-noise AST checks.
- [ ] `module_risk`: flag `module.xml` `<sequence>` entries missing for
      modules a module's own code actually depends on (DI-injected classes,
      referenced layout handles/blocks) — the classic Magento
      load-order-dependent bug. Bigger lift: needs mapping class/layout
      references back to the owning module.

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
