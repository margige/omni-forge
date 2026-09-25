# AGENTS.md — omni-forge

Guidance for coding agents working in this repository.

## What this repo is

omni-forge is a **free-first, local-first multimodal generation stack** for opencode:

- `apps/router` — a Python FastAPI gateway that routes OpenAI-compatible chat requests across a
  pool of free providers with failover, cooldown and a usage ledger. **This is the core of the
  project; treat it as production code.**
- `apps/core` — a Python FastAPI service exposing image/video/tts/asr/search over HTTP.
- `apps/mcp` — a Node MCP server that exposes Forge Core/Router as opencode tools.
- `apps/cli` — the `forge` TypeScript CLI (`up`, `down`, `status`, `doctor`, `quota`, `gen`, `mcp`).
- `packages/opencode-pack` — opencode pack (provider + MCP config, skills, agents, commands,
  one `quota-toast` plugin) that drops into an opencode project. The MCP server, not config
  `tool` keys, provides the tool surface.

## Conventions

- **Router and Core are Python 3.11+**, FastAPI + httpx, `sqlite3` from the stdlib. No ORM.
- **CLI, MCP and opencode-pack are TypeScript**, run with Bun, ESM only.
- Every provider adapter speaks the **OpenAI-compatible** wire format; that is the whole point of
  the router — one request shape, many backends.
- Do not hard-code secrets. Read them from the environment and skip providers whose key is absent.
- Keep the router dependency-light and deterministic; it is the piece users trust not to fail.

## Testing

```bash
# router
cd apps/router && python -m pytest

# core
cd apps/core && python -m pytest

# typescript
bun install && bun run typecheck
```

## Style

- No comments unless they explain *why*, not *what*.
- Type everything in TypeScript; use pydantic models / dataclasses in Python.
- Small functions. The router's selection logic (quota → priority → cooldown) must stay readable.
