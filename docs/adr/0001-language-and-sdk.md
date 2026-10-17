# ADR 0001: Python and the official MCP SDK

**Date:** 2026-10-15
**Status:** accepted

## Context

An MCP server for auditing Magento projects. The author has 14 years in PHP and
four months of full-time Symfony; learning Python since 2026-10-11. The choice
was between PHP and Python.

## Decision

**Python**, on the official `mcp` SDK (version 2.x).

## Rationale

- One artifact closes two portfolio gaps at once: no MCP server and nothing
  public in Python. Python keeps coming up as a requirement in AI-engineering
  job postings.
- The Python SDK is **Tier 1** in the official classification (alongside
  TypeScript, C#, Go, Rust and Ruby). The PHP SDK is Tier 3 and pre-1.0 — fewer
  examples, a less stable API.
- The domain stays Magento, so the artifact shows a new language and four years
  of domain knowledge on the platform at the same time.

## Consequences

- Learning overhead: the first stages will go slower than they would in PHP.
- **Hard requirement: the author must understand every line of this code.**
  The project is meant to be proof of skill in a job interview, not a printout
  from a generator.
- `composer.lock` is plain JSON, so not having PHP on the implementation side
  doesn't make anything harder.

## A trap worth remembering

In SDK `mcp` 2.x, the `FastMCP` class was renamed to `MCPServer`
(`from mcp.server.mcpserver import MCPServer`). Code and examples from 1.x
won't work. The API was checked against the installed version, not assumed
from memory — the same principle this server is meant to enforce on the model.
