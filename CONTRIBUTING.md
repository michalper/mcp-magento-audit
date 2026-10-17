# Contributing to mcp-magento-audit

Thanks for considering a contribution. This is an early-stage, solo side project — see
`docs/adr/` for the reasoning behind its bigger decisions before proposing to change them.

## Setting up a dev environment

```bash
git clone https://github.com/michalper/mcp-magento-audit.git
cd mcp-magento-audit
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
```

`pre-commit install` wires up ruff/mypy/bandit/pytest to run on every commit (see
`.pre-commit-config.yaml`) — the same checks CI runs, so a failing commit locally means CI
would have failed too.

## Code style and checks

```bash
.venv/bin/python -m pytest --cov        # tests + coverage
.venv/bin/ruff check .                   # lint
.venv/bin/mypy src                       # types (strict)
.venv/bin/bandit -c pyproject.toml -r src   # security
.venv/bin/pip-audit                      # dependency vulnerabilities (network, CI-only)
```

All of these run in CI (`.github/workflows/ci.yml`) on every push; a change that fails any
of them won't merge.

- **No comments explaining *what* the code does** — a well-named identifier already does
  that. A comment is only for the *why*: a hidden constraint, a workaround for a specific
  bug, a non-obvious invariant.
- **Don't guess an external tool's behavior from memory.** This project's own ADRs and
  commit history document checking real CLI output/API responses instead of assuming them
  (see ADR-era notes on the `mcp` SDK, and the Rector/phpcs/phpstan integrations) — follow
  the same standard for anything new that shells out or calls an external API.
- **Keep PRs scoped to one thing.** A bug fix, one new tool, one refactor — not a mix.

## Adding a new MCP tool

Look at an existing one first (`module_risk.py` + its registration in `server.py` is a good
template: a pure-logic module with its own dataclasses, wired into a thin `@server.tool`
function that only maps `ProjectError` → `{"error": ...}`). Keep domain logic out of
`server.py` — it should only resolve/validate the path and call into the module.

## Releasing a new version

Add a `## [X.Y.Z] - YYYY-MM-DD` entry to `CHANGELOG.md` summarizing what changed since
the last release (Keep a Changelog style: Added/Fixed/Changed/Declined).

`scripts/bump_version.py` updates the version in `pyproject.toml` and `server.json` (three
fields across two files, previously kept in sync by hand) — it only edits files, it doesn't
tag, push, or publish:

```bash
.venv/bin/python scripts/bump_version.py patch   # or minor / major / an explicit X.Y.Z
git add pyproject.toml server.json CHANGELOG.md
git commit -m "Bump to <version>"
git tag v<version> && git push origin master v<version>
gh release create v<version> --generate-notes    # triggers PyPI publish via CI (Trusted Publishing)
mcp-publisher publish                            # re-publish server.json to the MCP Registry
```

## Reporting issues

Open a GitHub issue with what you expected, what happened instead, and enough to reproduce
it. For a security issue, please don't open a public issue — see [SECURITY.md](SECURITY.md)
instead.

## License

By contributing, you agree your contribution is licensed under this project's
[MIT license](LICENSE).
