---
name: research-forge
description: Search the web through the local omni-forge core (SearXNG or DuckDuckGo fallback) and combine with vision queries on images. Use when the user asks to look something up, research a topic, or check a claim.
---

# Research Forge

Web search plus image interrogation through the omni-forge core.

## Prerequisites
- `forge core` running.
- Search works out of the box via DuckDuckGo HTML; for self-hosted privacy use SearXNG and set `SEARXNG_BASE_URL`.

## Steps
1. Call `forge_search` with the query. If the first result set is thin, rephrase or narrow the query once before giving up.
2. Optional `force` re-run with `limit` raised to 10 for wider coverage.
3. If the user drops an image and asks questions about it, call the MCP `forge_vision` tool with the image path and their question.
4. Synthesize findings into a short briefing with sources as links — never present a snippet as your own conclusion.

## Notes
- `forge_quota` (or `forge status`) tells you which provider is currently serving chat — useful when results seem stale.