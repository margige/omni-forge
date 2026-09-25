# omni-forge architecture

```
                         ┌──────────────────────────────────────────┐
                         │  opencode (agent, skills, plugins, …)     │
                         │  ─ custom tools ─  ─ MCP "forge" ─        │
                         └───────────────┬───────────────────────────┘
                                         │ OpenAI-compatible POST /v1/chat/completions
                                         │ model: forge-chat
                                  ┌──────▼───────┐
                                  │  ROUTER :4010│  usage ledger (sqlite) · cooldowns
                                  │              │  failover: priority order, local last
                                  └──────┬───────┘
        cloud free tiers ────────────────┼─────────────────── local  ─┐
     gemini · groq · cerebras · nvidia · │  mistral · openrouter ·    │
     github-models · huggingface ·       │  together · ollama ·       │
     together                            │  localai                   │
                                         │
                                  ┌──────▼───────┐
                                  │  CORE :4020  │  /v1/image /tts /asr /vision /video /search
                                  └──────┬───────┘
        pollinations · comfyui · wan · edge-tts · piper · whisper · searxng · duckduckgo
```

## Router (`apps/router`, Python 3.11+, FastAPI + httpx + stdlib sqlite3)

One logical model, many backends. The whole project is the box labeled
"FAILOVER → ________ ".

- `config.py` — `ProviderConfig` / `RouterConfig`, loads `providers.yaml`
  (config lookup chain falls back to `.example`), resolves keys from env.
- `store.py` — `UsageLedger`: SQLite `usage` (requests/tokens/errors per day),
  `cooldowns`, optional key pool. All access is lock-guarded.
- `errors.py` — `is_quota_error` (402/429 + body markers), `NoProviderAvailable`.
- `providers.py` — `Provider`: chat URL, auth headers, sliding 60s rpm window,
  payload shaping and model mapping.
- `router.py` — `ForgeRouter._candidates()` = resolved ∧ not cooling ∧ rpm ⌣ ∧
  rpd day-room. `complete()` non-streaming failover; `open_stream()` confirms a
  200 with the upstream **before** any bytes are relayed. Exhaustion returns
  `_exhaustion_report()` so nobody has to guess.
- `main.py` — `/v1/chat/completions`, `/v1/models`, `/forge/{health,quota,providers}`,
  plus the `/forge/` dashboard (static). CORS open for local frontends.

Routing policy is *pay-as-you-go-by-default*: hit 429/402/"rate limit" → that
provider cools for `cooldown_seconds` (300) and the next tier handles the
request. When everything is exhausted you get a 503 **with** the reason. The
local Ollama/LocalAI tiers always sort last — the always-on safety net.

## Core (`apps/core`, Python 3.11+, FastAPI)

Multimodal HTTP surface with a tiny backend registry and per-endpoint failover
(`Registry` + `_run_chain`). Backends:

| capability | default | fallback/offline |
|---|---|---|
| image | pollinations (keyless) | comfyui (workflow template) |
| video | wan (async job, `FORGE_WAN_COMMAND`) | — |
| tts | edge-tts (keyless) | piper (fully offline) |
| asr | whisper CLI | — |
| search | searxng | duckduckgo (html/lite) |
| vision | router VLM via `forge-chat` | — |

Generated files land in `FORGE_OUTPUT_DIR` and are served at `/media/...`.

## opencode integration (`packages/opencode-pack`)

Copy into your opencode project (or `~/.config/opencode`):

- `opencode.jsonc` — registers the `omni-forge` provider (baseURL
  `http://127.0.0.1:4010/v1`, model `forge-chat`) and the `forge` MCP server
  (`forge mcp`). The tool surface (`forge_image`, `forge_tts`, `forge_search`,
  `forge_quota`, …) comes from that MCP server — opencode's schema has no
  top-level `tool` key, so tools are exposed as real MCP tools.
- `skills/{media,voice,research}-forge/SKILL.md` — turnkey workflows.
- `plugins/quota-toast.ts` — opencode plugin hook, verified against
  `@opencode-ai/plugin` types via `npm run typecheck`.
- `agents/*.md`, `commands/*.md` — drop-in agent/command definitions.

## CLI / MCP / UI

- `apps/cli` — `forge up|down|status|doctor|quota|gen <image|tts>|mcp`.
- `apps/mcp` — Node stdio MCP server with tools mirroring the core API.
- `apps/ui/dashboard` — hosted at `/forge/`, quota panel + quick generation.
- Open WebUI (docker-compose) is the friendly chat frontend.

## Deployment modes

1. **native**: `install.ps1` / `install.sh` → uvicorn (or `forge up` via pm2).
2. **docker compose**: `router`, `core`, `openwebui`, `searxng`
   (+ `ollama` with `--profile local`, `comfyui` with `--profile gpu`).