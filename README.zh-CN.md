# omni-forge

> **免费优先、本地优先的 opencode 多模态生成栈。**
> 文本 · 图像 · 视频 · 语音 · 视觉 · 搜索 —— 自动在多个免费额度之间完成切换，
> 当一个模型的免费额度用完时，下一个会无缝接力。

简体中文 | [English](README.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md)

omni-forge 把一批优秀的开源项目整合成**一个友好的应用**外加原生的
**opencode 集成包**。你的编辑器只需指向一个本地端点，就可以忘掉速率限制、额度和
API Key。

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

## 为什么

单提供商 CLI 在免费额度耗尽的瞬间就「死了」。omni-forge 把「免费」当作**一个池子**
而不是单账号：它把每个请求路由到第一个健康的免费提供商，为已耗尽的提供商进入冷却，
云端全部枯竭时回退到本地模型。调用方永远只看到一个模型名：`forge-chat`。

> 编辑器得到的永远只有 `forge-chat` 一个模型；路由器按「最高优先级健康提供商 →
> 冷却 → 下一个 → 本地兜底」的顺序工作。

## 快速开始

```bash
# 1. 安装（Windows: installers\install.ps1，其它: installers\install.sh）
#    创建 .venv、构建 router+core、复制配置模板
./installers/install.sh

# 2. 把你拥有的各 API Key（全部可选）填入 .env 与 providers.yaml

# 3. 启动两个服务
. .venv/bin/activate
python -m uvicorn forge_router.main:app --port 4010 &
python -m uvicorn forge_core.main:app --port 4020 &

# 4. 检查健康状态与免费额度
curl http://127.0.0.1:4010/forge/quota
curl http://127.0.0.1:4020/forge/health
```

也可以一条命令拉起 router、core、Ollama、SearXNG 与 Open WebUI：

```bash
docker compose up -d          # + `--profile local` 启用 ollama，`--profile gpu` 启用 comfyui
open http://127.0.0.1:4010/forge/   # 内置面板与快速生成器（支持 中文/English/日本語/한국어）
```

安装 `bun` 后，`apps/cli` 提供 `forge up|down|status|doctor|quota|gen|mcp`。
CLI 消息会根据 `FORGE_LANG`（或 `LANG` / `LC_ALL`）自动显示中文/英文/日文/韩文。

## 在 opencode 中使用

把 `packages/opencode-pack/` 复制到你的项目里，然后注册配置：

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

配置注册了 `omni-forge` 提供商和 `forge` MCP 服务器（工具面由 MCP 提供 ——
opencode 的配置 schema 没有 `tool` 键，所以工具以真正的 MCP 工具形式提供）。
你在 opencode 里原生获得：

| 工具 | 作用 |
| --- | --- |
| `forge_image` | 文本 → 图像（ComfyUI 本地，Pollinations 免费兜底） |
| `forge_video` | 文本 → 视频（Wan 2.1） |
| `forge_tts` | 文本 → 语音（Piper / edge-tts，免费，自动按中/英/日/韩文选音色） |
| `forge_asr` | 音频 → 文本（Whisper） |
| `forge_vision` | 图像 → 描述（经 `forge-chat` VLM） |
| `forge_search` | 网页搜索（SearXNG）+ 页面抓取 |
| `forge_quota` | 实时免费额度面板 |

……以及 skills（`media-forge`、`voice-forge`、`research-forge`）、agents、斜杠命令
和监视额度池的 `quota-toast` 插件。安装说明见 `packages/opencode-pack/README.md`。

## 仓库结构

```
apps/router      Python  FastAPI 免费额度切换网关（核心）
apps/core        Python  FastAPI 多模态生成服务
apps/mcp         Node    将 Forge 工具暴露为 MCP 的服务器
apps/cli         Bun     `forge` 命令行
apps/ui          static 内置额度面板（/forge/）
packages/opencode-pack   opencode 集成包：provider + MCP 配置 + skills + agents + commands + plugin
docker-compose.yml       一条命令拉起整套栈
installers/              install.sh / install.ps1
```

## 文档

- [`docs/architecture.md`](docs/architecture.md) — 路由器与核心如何协作
- [`docs/free-providers.md`](docs/free-providers.md) — 免费池、额度与注意事项
- [`docs/multilingual.md`](docs/multilingual.md) — 中文 / English / 日本語 / 한국어 支持说明
- [`docs/roadmap.md`](docs/roadmap.md) — M0 → M4

## 许可证

Apache-2.0。第三方组件保留各自的许可证 —— 参见 [`NOTICE`](NOTICE)。

> ⚠️ 部分免费档的服务条款不鼓励自动化多 Key 轮换。omni-forge 默认提供单 Key 切换；
> Key 池为可选项，且使用责任自负。