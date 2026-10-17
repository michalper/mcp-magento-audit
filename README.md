# mcp-magento-audit

<!-- mcp-name: io.github.michalper/mcp-magento-audit -->

[![CI](https://github.com/michalper/mcp-magento-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/michalper/mcp-magento-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Last commit](https://img.shields.io/github/last-commit/michalper/mcp-magento-audit)](https://github.com/michalper/mcp-magento-audit/commits/master)

An [MCP](https://modelcontextprotocol.io) server giving an AI agent tools to assess a
Magento 2 / Adobe Commerce project along three axes: **compatibility with a target PHP
and Magento version**, **quality of custom modules**, and **dependency security**.

It answers the question that never stops coming up in Magento agencies:
*"can we bump this client to a newer version, what's blocking it, and where do we start?"*

> **Status: early stage.** Built on evenings/weekends. All five planned tools
> (`project_status`, `check_updates`, `module_risk`, `fetch_release_notes`,
> `upgrade_plan`) are working. See `ROADMAP.md` for what's next.

## How this differs from `composer audit`

`composer audit` and `composer outdated` are built into Composer and do their job well.
This server targets three things they don't give you:

1. **They don't see `app/code`.** Custom modules don't exist on Packagist, so they get
   zero coverage from vulnerability databases — and that's exactly the code agencies write.
2. **They don't combine axes.** Nobody gets one answer: *this module blocks the upgrade,
   has an open CVE, is abandoned by its author, and has the worst complexity in the
   project — fix this one first.*
3. **They don't aggregate across projects.** "Which of our twenty stores can be upgraded
   today" requires stitching results together from many directories by hand.

**What this server doesn't pretend to be:** there's no clean dataset of "module X works
with Magento 2.4.8". Results are derived from declarations in `composer.json`, a code
scan, and the vendor's own release notes — this is a decision-support tool, not an
oracle. Upgrading a production store still requires testing, not just a report.

## Install

```bash
git clone https://github.com/michalper/mcp-magento-audit.git
cd mcp-magento-audit
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Connecting to Claude Code

```json
{
  "mcpServers": {
    "magento-audit": {
      "command": "/path/to/mcp-magento-audit/.venv/bin/mcp-magento-audit"
    }
  }
}
```

## Example

An agent calling `upgrade_plan` against a store that has one abandoned, PHP-7-only
package and no `phpstan.neon` of its own (trimmed — the real result also includes
`release_notes`, and the full `update_check`/`module_risk` results each blocker was
derived from):

```json
{
  "ready": false,
  "unverified": [
    "phpstan: no phpstan.neon(.dist) in project — skipping static analysis"
  ],
  "blockers": [
    {
      "source": "composer",
      "description": "legacy/module",
      "detail": "^7.4 does not cover PHP 8.3"
    }
  ]
}
```

`ready` is false because of a real blocker, not a guess; `unverified` says phpstan never
ran at all, so a clean result elsewhere isn't mistaken for "everything was checked".

## Tools

| Tool | Status | Description |
|---|---|---|
| `project_status` | **working** | Magento version, PHP requirement, package count, abandoned packages |
| `check_updates` | **working** | per-package verdict against a target PHP/Magento version, plus a Rector-based check of whether the code itself would need changes |
| `module_risk` | **working** | scans code via `phpcs` (Magento2 coding standard), the project's own `phpstan`, and the project's own `rector.php` (dead code/quality) |
| `fetch_release_notes` | **working** | release notes from `magento/magento2` GitHub Releases, **without answering from the model's memory** |
| `upgrade_plan` | **working** | combines the other tools into a list of concrete blockers, with `ready=true` only once it's empty |

## Development

```bash
.venv/bin/python -m pytest --cov        # tests + coverage
.venv/bin/ruff check .                  # lint
.venv/bin/mypy src                      # types
.venv/bin/bandit -c pyproject.toml -r src   # security
.venv/bin/pip-audit                     # dependency vulnerabilities
```

Run `.venv/bin/pre-commit install` once to run all of the above (except
`pip-audit`, which needs network access and stays CI-only) on every commit.

Architectural decisions are recorded in `docs/adr/`.

## License

MIT
