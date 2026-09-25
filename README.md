# omni-forge

> **Free-first, local-first multimodal generation for opencode.**
> Text · Image · Video · Speech · Vision · Search — with automatic failover across free tiers,
> so when one model's free quota runs out, the next one picks up seamlessly.

omni-forge turns a pile of excellent open-source projects into **one friendly app** plus a
native **opencode integration pack**. Point your editor at a single local endpoint and forget
about rate limits, quotas and API keys.

```
        friendly UI (Open WebUI / built-in dashboard)
                          │  OpenAI-compatible
                          ▼
        ┌───────────────────────────────────────┐
        │  Forge Router  :4010                   │  free-tier failover · key pools
        │  gemini → groq → cerebras → nim → ...  │  cooldowns · usage ledger
        └───────────────┬───────────────────────┘
                        │ always falls back to
                        ▼
        local: Ollama · llama.cpp · LocalAI      (unlimited, offline)

        Forge Core :4020  ── image (ComfyUI) · video (Wan) · tts (Piper/edge-tts)
                          · asr (Whisper) · search (SearXNG)
```

## Why

Single-provider CLIs die the moment a free quota is exhausted. omni-forge treats *"free"* as a
**pool**, not a single account: it routes each request to the first healthy free provider, cools
down the ones that are exhausted, and falls back to local models when everything cloud-side is
dry. The caller only ever sees one model name: `forge-chat`.

## Quick start

```bash
# 1. install (Windows: installers\install.ps1, else installers\install.sh)
#    creates .venv, builds router+core, copies config templates
./installers/install.sh

# 2. add the API keys you have (all optional) to .env and providers.yaml

# 3. start the two services
. .venv/bin/activate
python -m uvicorn forge_router.main:app --port 4010 &
python -m uvicorn forge_core.main:app --port 4020 &

# 4. check health + free-tier quota
curl http://127.0.0.1:4010/forge/quota
curl http://127.0.0.1:4020/forge/health
```

Alternatively one command brings up router, core, Ollama, SearXNG and Open WebUI:

```bash
docker compose up -d          # + `--profile local` for ollama, `--profile gpu` for comfyui
open http://127.0.0.1:4010/forge/   # built-in dashboard & quick generator
```

With `bun` installed, `apps/cli` provides `forge up|down|status|doctor|quota|gen|mcp`.

## Use it from opencode

Copy `packages/opencode-pack/` into your project, then register the config:

```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "omni-forge": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "omni-forge (free router)",
      "options": { "baseURL": "http://127.0.0.1:4010/v1" },
      "models": { "forge-chat": { "name": "Forge Chat (auto-failover)" } }
    }
  },
  "mcp": { "forge": { "type": "local", "command": ["forge", "mcp"] } }
}
```

The config registers the `omni-forge` provider plus the `forge` MCP server
(which provides the tool surface — opencode's config schema has no `tool` key,
so tools ship as real MCP tools). You get, natively inside opencode:

| tool | does |
| --- | --- |
| `forge_image` | text → image (ComfyUI local, Pollinations free fallback) |
| `forge_video` | text → video (Wan 2.1) |
| `forge_tts` | text → speech (Piper / edge-tts, free) |
| `forge_asr` | audio → text (Whisper) |
| `forge_vision` | image → description (via `forge-chat` VLM) |
| `forge_search` | web search (SearXNG) + page scrape |
| `forge_quota` | live free-quota dashboard |

…plus skills (`media-forge`, `voice-forge`, `research-forge`), agents, slash
commands and a `quota-toast` plugin that watches the pool. See
`packages/opencode-pack/README.md` for install notes.

## Repository layout

```
apps/router      Python  FastAPI free-tier failover gateway (the hard part)
apps/core        Python  FastAPI multimodal generation service
apps/mcp         Node    MCP server exposing Forge tools
apps/cli         Bun     `forge` command-line
apps/ui          static  built-in quota dashboard
packages/opencode-pack   opencode pack: provider + MCP config + skills + agents + commands + plugin
docker-compose.yml       one-command stack
installers/              install.sh / install.ps1
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — how the router and core fit together
- [`docs/free-providers.md`](docs/free-providers.md) — the free-tier pool, quotas and caveats
- [`docs/roadmap.md`](docs/roadmap.md) — M0 → M4

## License

Apache-2.0. Third-party components keep their own licenses — see [`NOTICE`](NOTICE).

> ⚠️ Some free tiers' terms of service discourage automated multi-key rotation. omni-forge ships
> single-key failover by default; key pools are opt-in and your responsibility.
