# Roadmap

## Tools

All eight planned tools (`get_project_status`, `check_updates`, `scan_module_risk`,
`audit_security`, `check_outdated_packages`, `fetch_release_notes`, `build_upgrade_plan`,
`build_fleet_overview`) are done.

- [x] Rector-based dead-code/quality checks in `scan_module_risk` (the project's own
      `rector.php`, as-is — not the PHP-version compatibility check, which
      is a separate, synthetic-config signal in `check_updates`).
- [x] `audit_security`: `composer audit` across every installed package
      (`vendor/`, not just `app/code`), wired as blockers into `build_upgrade_plan`.
- [x] `scan_module_risk`: scan third-party `vendor/` packages of type
      `magento2-module` (not just core `magento/*`) with `phpcs` for
      coding-standard issues (`vendor_phpcs`) — `audit_security` only covers
      known CVEs, not style/legacy-API violations. phpstan/rector
      deliberately not extended to vendor/ (noisy without the project's own
      bootstrap, and not actionable on someone else's code either way).
      Vendor-scope issues are informational only — excluded from
      `build_upgrade_plan`'s blockers, since they're not the project's own code to fix.
- [x] `check_outdated_packages`: shells out to the built-in `composer outdated
      --format=json` (same pattern as `audit_security`, shares
      `_process.find_composer`) to report which installed packages have a
      newer version available — a staleness/tech-debt signal independent of
      CVEs (`audit_security`) and target-version compatibility
      (`check_updates`). Informational in `build_upgrade_plan`, not a blocker.
- [x] `build_fleet_overview`: triages many project directories at once ("which of
      these N stores can be upgraded today") — the third differentiator the
      README advertises over plain `composer audit`. Deliberately lightweight
      (only `check_updates` per project, not the full `build_upgrade_plan`):
      scan_module_risk's phpcs/phpstan/rector and audit_security's/
      check_outdated_packages' composer calls are each seconds-to-minutes and
      don't scale across a fleet in one call. A project that fails to load
      is reported with its own error rather than failing the whole batch.
- [x] `scan_module_risk`: `object_manager_misuse` — a plain regex scan over
      `app/code`'s `.php`/`.phtml` files for `ObjectManager::getInstance()`.
      Correction after checking `magento/magento-coding-standard`'s own
      source: there is no `Magento2.Classes.ObjectManager` sniff (an
      assumption from an earlier roadmap entry, not verified at the time).
      The standard's only built-in check for this,
      `Magento2.Templates.ObjectManagerUsageFound`, fires solely inside
      `.phtml` templates — not in Model/Block/Helper classes, arguably the
      more harmful case since it bypasses constructor DI in business logic.
      No subprocess, so no "tool not found" failure mode.
- [x] `scan_module_risk`: `core_overrides` — flags `app/code` classes that
      redeclare a class already present in `vendor/magento/*` under the
      exact same fully qualified name (a copy-pasted core file, not a
      legitimate `di.xml` preference/plugin, which reference the original
      class rather than duplicate it). `severity="error"`, so — unlike
      `object_manager_misuse` — it *does* become a `build_upgrade_plan` blocker.
      Indexes every class in `vendor/magento/*` once by bare class name (an
      O(1) dict lookup per `app/code` candidate, not a filesystem walk per
      candidate — confirmed fast against a real ~8500-class core tree,
      ~1.3s). `scanned=false` only if there's no `vendor/magento` at all.
- [x] ~~`scan_module_risk`: flag admin controller actions missing `_isAllowed()`
      (or an always-`true` stub)~~ — **declined** after checking against a
      real Magento core checkout, *before* writing any code: (1) `return
      true;` in `_isAllowed()` is a legitimate pattern core itself uses
      (`Backend/Controller/Adminhtml/{Auth,Index,Denied/Index}.php`,
      `Captcha/.../Refresh.php` — login/denied/captcha pages must be
      reachable pre-ACL-check, not just a bug pattern); (2) "no own
      `ADMIN_RESOURCE`/`_isAllowed()` in this file" has a ~72% false-positive
      rate on core itself (570/795 concrete admin controllers) — Magento's
      idiomatic pattern is declaring `ADMIN_RESOURCE` once on a shared base
      action class and letting leaf actions (`Save.php`, `Delete.php`, ...)
      inherit it, which a per-file check can't distinguish from "forgot to
      set it" without resolving the class hierarchy. Same category as the
      N+1-query/service-contracts items below: needs real
      semantic/inheritance analysis, not file-local pattern matching, so too
      false-positive-prone at the level this project operates. (Also: this
      pattern is admin-only — checked `Customer/Controller/{Account,Address,
      Section,Ajax}` directly, no `_isAllowed()`/ACL equivalent exists for
      the customer/frontend area at all, so the original item's mention of
      "customer-area action classes" was itself a wrong assumption.)
- [x] ~~`scan_module_risk`: flag empty `catch (...) {}` blocks and discouraged
      debug calls (`var_dump`/`print_r`/`echo`/`die`)~~ — checked against
      `magento/magento-coding-standard`'s own source before writing any code:
      2 of 3 sub-items are **already fully covered** by the `phpcs` scan
      `scan_module_risk` already runs, so building them again would be pure
      duplication: empty catch blocks → `Magento2.CodeAnalysis.EmptyBlock`
      (core itself suppresses it with `phpcs:ignore` in 23 places — proof the
      sniff fires), `var_dump`/`print_r` → `Magento2.Functions.
      DiscouragedFunction`. The one gap phpcs structurally doesn't cover —
      bare `die`/`exit`/`echo` as language constructs, not function calls —
      turned out too low-value to justify a new custom check on its own:
      7 and 1 occurrence respectively in the *entire* core codebase. Declined
      rather than building a checker for a signal that rare. Deliberately not
      pursuing N+1-query detection or "service contracts vs. direct
      collection access" either — those need real dataflow analysis, not
      AST/pattern matching, and would be too false-positive-prone at the
      level this project operates.
- [x] `scan_module_risk`: `dangling_references` — flags `app/code`'s own `di.xml`
      (`preference`/`plugin`), `events.xml` (`observer`), `crontab.xml`
      (`job`), layout XML (`block`/`uiComponent`), `indexer.xml`, and
      `schema.graphqls` (`@resolver`) naming a PHP class that doesn't
      resolve to any known class/interface or `virtualType` — invisible to
      phpcs/phpstan/rector, none of which analyze XML. Verified empirically
      against a real Magento core checkout (~5100 references checked across
      di.xml/events.xml/crontab.xml/layout/indexer.xml/schema.graphqls,
      true noise rate ≈0% — the only hits were 2-3 likely-genuine-but-
      harmless typos already present in core's own di.xml, reproduced
      independently with the actual shipped implementation, not just the
      verification script). `severity="warning"`, not a `build_upgrade_plan`
      blocker — not confident enough yet in a zero-false-positive rate on
      arbitrary agency code (unlike core's own, heavily-reviewed XML) to
      block an upgrade on it. Handles PHP's generated `\Proxy`/`\Interceptor`
      suffixes and `virtualType` aliases as valid resolution targets, and
      skips bare non-namespaced tokens (structurally not a possible Magento
      FQCN — seen even in core's own di.xml as an inert placeholder). Pure
      Python, no subprocess.
- [x] `release_notes.py`'s GitHub API call now sends `Authorization: Bearer`
      when `GITHUB_TOKEN`/`GH_TOKEN` is set in the environment — raises the
      60/hour unauthenticated rate limit to 5000/hour. Documented in README.
- [x] Documented in README that every subprocess-based check (`scan_module_risk`'s
      phpcs/phpstan/rector, `code_compatibility`, `audit_security`,
      `check_outdated_packages`) needs PHP/Composer reachable from wherever this
      MCP server itself runs — a real gap for projects developed exclusively
      inside Docker/DDEV/Warden/Lando, where `scanned=false` can otherwise
      read as "found nothing" rather than "couldn't check".
- [x] `MCP_MAGENTO_AUDIT_EXEC_PREFIX` env var wraps every subprocess call in
      `_process.run()` — closes the Docker/DDEV gap above more completely
      than documentation alone. Turned out to need only one central change,
      not one per call site, since every one of the 4 modules
      (`scan_module_risk`, `php_compatibility`, `audit_security`,
      `check_outdated_packages`) already funneled through this single shared
      `run()`. Two things beyond just prepending the prefix were needed for
      it to actually work against the common case (DDEV): (1) host-absolute
      paths like `vendor/bin/phpcs` are meaningless inside a container, so
      `run()` rewrites any argv path that's absolute *and* under `cwd` to be
      relative to it first — this relies on the project directory being
      bind-mounted with the same relative layout, true for DDEV/Warden/Lando's
      usual setup; (2) `find_composer()`'s `shutil.which("composer")` result
      is a host PATH lookup, not project-relative, so under a prefix it falls
      back to the bare name `composer` instead, trusting the container's own
      PATH. Both only activate when the env var is set — zero behavior change
      otherwise, confirmed by the full existing test suite passing unchanged.
- [x] ~~`scan_module_risk`: flag `module.xml` `<sequence>` entries missing for
      modules a module's own code actually uses~~ — **declined** after
      checking against `Magento_Sales` (core's own flagship module, heavily
      tested, definitely working correctly in production): it references
      classes from 21 other modules via plain `use` statements, but its own
      `module.xml` `<sequence>` declares only 5 of them — an 81%
      "false-positive" rate using the naive heuristic (every referenced
      module needs a sequence entry). The real rule is narrower and more
      semantic than that: `<sequence>` governs the processing order of
      `di.xml`/`events.xml`/layout merging/setup scripts between modules —
      not class-level PHP dependencies, which are resolved by Composer's
      autoloader independently of Magento's module sequence entirely. Same
      conclusion as the `_isAllowed()` item: needs real domain understanding
      of *when* sequence actually matters, not reference-counting, so too
      false-positive-prone at the level this project operates.

## Distribution

- [x] Published to PyPI as `mcp-magento-audit` (0.1.1) and registered on the official MCP
      Registry (`registry.modelcontextprotocol.io`, `io.github.michalper/mcp-magento-audit`,
      status `active`).
- [x] `scripts/bump_version.py` updates the version in `pyproject.toml` and
      `server.json` (3 fields across 2 files) together — only edits files,
      doesn't tag/push/publish, those stay deliberate manual steps (see
      `CONTRIBUTING.md`).

## Housekeeping

- [x] Polish the README further: badges (license, Python version, ruff, last commit) and
      a trimmed `build_upgrade_plan` example transcript.
- [x] Add `CONTRIBUTING.md`.
- [x] Add `SECURITY.md`.
- [x] Test coverage measurement (`pytest-cov`) — wired into `pyproject.toml` and CI.
- [x] Security linter (`bandit`) — wired into `pyproject.toml` and CI, reviewed findings
      annotated with `# nosec`.
- [x] Dependency vulnerability scan (`pip-audit`) — wired into CI (network-dependent,
      deliberately not in pre-commit).
- [x] `pre-commit` config — local hooks for ruff/mypy/bandit/pytest, installed via
      `pre-commit install`.
- [x] Widened the ruff ruleset with `RUF` and `PERF` — fixed the 10 findings
      this surfaced (5 `PERF401` manual-loop-to-comprehension, 3 stale
      `noqa` directives for rules no longer selected, 2 `RUF043` ambiguous
      `pytest.raises(match=...)` patterns needing `re.escape`).
