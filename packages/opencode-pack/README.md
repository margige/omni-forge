# opencode-pack — omni-forge for opencode

Drop-in integration pack. Gives an opencode project the omni-forge router as a
model provider, the Forge Core as a tool surface, plus skills, agents, commands
and a monitoring plugin.

## Install

```
# 1. copy this pack into your project
cp -r packages/opencode-pack/* .opencode/        # opencode.jsonc -> opencode.json
cp packages/opencode-pack/opencode.jsonc opencode.json

# 2. put the forge CLI on PATH (https://github.com/.../omni-forge#cli)
forge doctor
```

You also need the router + core running (`forge up`, or the installers / docker
compose). See the repo README.

## What you get after restarting opencode

| piece | effect |
| --- | --- |
| `opencode.json` | adds the `omni-forge` provider (`forge-chat` model) + the `forge` MCP server |
| MCP tools | `forge_image`, `forge_video`, `forge_tts`, `forge_asr`, `forge_vision`, `forge_search`, `forge_quota` from the `forge` MCP server |
| skills | `media-forge`, `voice-forge`, `research-forge` |
| agents | `image-artist`, `video-director`, `voice-actor`, `researcher` |
| commands | `/image`, `/video`, `/tts`, `/quota` |
| plugin | `quota-toast` logs when the failover pool is degraded |

> opencode loads config at startup. Quit and restart opencode after installing.

## Why there is no `tool` section

Until now opencode validates its config against the published
`schema` (`https://opencode.ai/config.json`, `additionalProperties: false`).
There is **no top-level `tool` key**, so ad-hoc "custom remote tool" config is
not supported. The Forge tool surface therefore ships as a **real MCP server**
(`apps/mcp`), which is the schema-blessed way to add tools.

## plugin shape (why it looks this way)

Plugin modules must default-export a function conforming to
`@opencode-ai/plugin`'s `Plugin` type. There is no `plugin()` factory and no
`session.start` hook. `quota-toast.ts` uses `tool.execute.after` against the
real type surface; `npm run typecheck` in this folder verifies it against
`@opencode-ai/plugin@1.18.32`.