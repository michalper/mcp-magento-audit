# Security Policy

## Supported Versions

Early-stage project, single `master` branch, no tagged releases yet — only the latest
commit is supported.

## Automated Scanning

`bandit` (static security analysis) and `pip-audit` (dependency vulnerabilities) run in CI
on every push (`.github/workflows/ci.yml`). This is a code-review aid, not a substitute for
a manual security review.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.

Instead, email **michal.per@outlook.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce.

You should receive a response within a few business days.
