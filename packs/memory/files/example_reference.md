---
name: context7-mcp
description: When you're about to quote library or framework syntax (APIs, SDK calls, config, CLI flags).
type: reference
---

Don't quote library syntax from memory -- it drifts between versions and you'll
state a signature that no longer exists. Fetch current docs first (e.g. via the
context7 MCP), then quote what you just read.

This is a `reference` memory: it points at WHERE the answer lives, rather than
encoding a behaviour rule. The one-line body plus the `description` trigger is
enough -- the value is being *reachable* at the right moment, not being long.

Related: [[feedback_verify_against_source]]
