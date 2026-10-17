# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) (pre-1.0:
a minor bump means new features, a patch means fixes only — no stability
guarantee yet on the exact JSON shape of tool results).

## [0.2.0] - 2026-10-17

### Added
- `security_audit`: every installed package in `composer.lock` (core, third-party
  `vendor/`, dev dependencies — not just `app/code`) checked against known advisories
  via `composer audit`. Wired into `upgrade_plan` as blockers.
- `outdated_packages`: every installed package checked against `composer outdated` for
  a newer available version — a staleness signal independent of CVEs or target-version
  compatibility. Informational in `upgrade_plan`, not a blocker.
- `fleet_overview`: triages many project directories at once against a target
  PHP/Magento version ("which of these N stores can be upgraded today").
- `module_risk`: `vendor_phpcs` — scans third-party (non-`magento/*`) `vendor/`
  packages of type `magento2-module` with `phpcs` for coding-standard issues.
  Vendor-scope issues are informational only, excluded from `upgrade_plan`'s blockers.
- `module_risk`: `object_manager_misuse` — flags `ObjectManager::getInstance()` calls
  in `app/code`'s `.php`/`.phtml` files (not limited to `.phtml`, unlike the Magento
  coding standard's own sniff).
- `module_risk`: `core_overrides` — flags `app/code` classes that redeclare a
  `vendor/magento/*` class under the same fully-qualified name (a copy-pasted core
  file). `severity="error"`, so this becomes an `upgrade_plan` blocker.
- `scripts/bump_version.py` to script the version-bump process across
  `pyproject.toml` and `server.json` together.
- Widened the `ruff` ruleset with `RUF` and `PERF`.

### Fixed
- `Project.magento_version` returned `null` for Magento-core-monorepo-style
  checkouts (no `magento/product-*-edition` dependency); now falls back to the
  project's own `composer.json` name/version for `magento/magento2ce`/`magento2ee`.
- Path traversal in `vendor_phpcs`'s module discovery: a crafted package name in
  `composer.lock` (e.g. containing `..`) could resolve outside `vendor/` and get
  scanned, leaking directory-existence/lint output for an attacker-chosen path.
- `core_overrides` false positives: PHP anonymous-class syntax
  (`new class extends Foo`) and class names mentioned only in a comment or string
  literal were mistaken for real declarations.
- Lost-update race in `cache.py` under concurrent callers: `fleet_overview`'s
  thread pool could race `php_requirement_for_magento`'s/`release_notes_for_version`'s
  read-modify-write of the same cache file, silently dropping one side's update.
  Fixed with a per-file lock.
- `composer.py` only caught `FileNotFoundError`, not other `OSError`s (e.g.
  `PermissionError`), when loading a project — could crash `fleet_overview`'s
  whole batch instead of reporting just the one bad project.
- Deduplicated near-identical composer-shelling logic between `security_audit`
  and `outdated_packages` into a shared `_process.run_composer_json()` helper.
- `module_risk`'s 6 checks (`phpcs`/`phpstan`/`rector`/`vendor_phpcs`/
  `object_manager_misuse`/`core_overrides`) now run concurrently instead of
  strictly sequentially.

### Declined
Three `module_risk` detection ideas were investigated and declined after checking
them empirically against a real Magento core checkout, each with too high a
false-positive rate to be worth building: admin-controller `_isAllowed()` checks,
empty-catch/discouraged-debug-call checks (mostly already covered by `phpcs`), and
`module.xml` `<sequence>` completeness checks. See `ROADMAP.md` for the evidence.

## [0.1.1] - 2026-10-17

Adds the `mcp-name` ownership marker to the README for MCP Registry publishing.
No functional changes.

## [0.1.0] - 2026-10-17

First published release. All five planned MCP tools are working: `project_status`,
`check_updates`, `module_risk`, `fetch_release_notes`, `upgrade_plan`.
