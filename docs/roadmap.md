# Roadmap

Status: **M0 + M1 + M2 shipped** — free-tier failover router, multimodal core,
opencode integration pack, dashboard. Everything below is additive.

## M3 — agent-friendly workflows (next)

- [ ] `/forge/plan` endpoint: multi-turn pipeline (prompt → script → storyboard
      → assets → video → voiceover → final render) with a job graph, not just
      single calls.
- [ ] opencode **skills** that compose image + tts + video into finished clips
      (a "make me a 15s product teaser" one-shot).
- [ ] `forge pack` command: one-command install of `packages/opencode-pack`
      into the current opencode project.

## M4 — quota intelligence

- [ ] Static schedule: cheap daytime tiers, then let local Ollama take over
      after a daily spend cap (`FORGE_DAILY_BUDGET`).
- [ ] Key rotation via the ledger's key pool behind a flag.
- [ ] Watchdog: an MCP tool that texts/dashboards you when a provider's free
      quota resets.
- [ ] Usage forecast (requests/day extrapolation) surfaced in the dashboard.

## M5 — hardening

- [ ] Provider request/response compatibility matrix tests against live
      upstreams (run in CI on a schedule).
- [ ] Exact RPD/rate-limit headers parsed from upstream responses instead of
      generic 429 detection.
- [ ] Multi-node routing (the router is stateless except sqlite; add a shared
      ledger URI).
- [ ] OpenTelemetry traces across router → provider → core.

## M6 — media quality

- [ ] ComfyUI workflow library (`FORGE_COMFY_WORKFLOW` → per-style presets).
- [ ] Video upscaling / frame-interpolation stage after Wan render.
- [ ] Local embedding of a small `imagen`-class model behind `/v1/image` for
      fully offline generation.

## Never

- Cloud provider ToS-violating key pooling (default stays single-key).
- Auto-billing, any kind of card, or paid keys baked in by default.