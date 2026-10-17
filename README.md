# mcp-magento-audit

[![CI](https://github.com/michalper/mcp-magento-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/michalper/mcp-magento-audit/actions/workflows/ci.yml)

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

## Tools

| Tool | Status | Description |
|---|---|---|
| `project_status` | **working** | Magento version, PHP requirement, package count, abandoned packages |
| `check_updates` | **working** | per-package verdict against a target PHP/Magento version, plus a Rector-based check of whether the code itself would need changes |
| `module_risk` | **working** | scans code via `phpcs` (Magento2 coding standard) and the project's own `phpstan` for deprecated API usage and type errors |
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
