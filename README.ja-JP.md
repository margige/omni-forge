# omni-forge

> **opencode 向けの、無料優先・ローカル優先のマルチモーダル生成スタックです。**
> テキスト · 画像 · 動画 · 音声 · 視覚 · 検索 —— 複数の無料枠を自動でフォールオーバーし、
> あるモデルの無料枠が尽きたら次のモデルがシームレスに引き継ぎます。

日本語 | [English](README.md) | [简体中文](README.zh-CN.md) | [한국어](README.ko-KR.md)

omni-forge は優れたオープンソース群を**ひとつの親しみやすいアプリ**にまとめ、さらに
ネイティブな **opencode 統合パック**を用意します。エディタを単一のローカルエンドポイント
に向けるだけで、レート制限・無料枠・API キーを忘れて構いません。

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

## なぜ

単一プロバイダーの CLI は無料枠が尽きた瞬間に動かなくなります。omni-forge は「無料」を
単一アカウントではなく**プール**として扱います。各リクエストを最初の健全な無料プロバイダー
へルーティングし、枯渇したプロバイダーはクールダウンし、クラウド側が全て枯渇したらローカル
モデルへフォールバックします。呼び出し側が目にするモデル名は常にひとつ：`forge-chat` です。

> エディタから見えるのは常に `forge-chat` の 1 モデル。ルーターが「最優先の健全な
> プロバイダー → クールダウン → 次 → ローカル」の順に処理します。

## クイックスタート

```bash
# 1. インストール（Windows: installers\install.ps1、それ以外: installers\install.sh）
#    .venv を作成し、router+core をビルドし、設定テンプレートをコピーします
./installers/install.sh

# 2. 手持ちの API キー（全て任意）を .env と providers.yaml に追加

# 3. 2 つのサービスを起動
. .venv/bin/activate
python -m uvicorn forge_router.main:app --port 4010 &
python -m uvicorn forge_core.main:app --port 4020 &

# 4. ヘルスと無料枠を確認
curl http://127.0.0.1:4010/forge/quota
curl http://127.0.0.1:4020/forge/health
```

あるいは docker compose で router・core・Ollama・SearXNG・Open WebUI をまとめて起動：

```bash
docker compose up -d          # + `--profile local` で ollama、`--profile gpu` で comfyui
open http://127.0.0.1:4010/forge/   # 内蔵パネル＆クイック生成（中文/English/日本語/한국어 対応）
```

`bun` を入れると、`apps/cli` が `forge up|down|status|doctor|quota|gen|mcp` を提供します。
CLI のメッセージは `FORGE_LANG`（または `LANG` / `LC_ALL`）に応じて
日本語・英語・中国語・韓国語で表示されます。

## opencode から使う

`packages/opencode-pack/` をプロジェクトへコピーし、設定を登録します：

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

この設定で `omni-forge` プロバイダーと `forge` MCP サーバーが登録されます（ツール面は
MCP が提供します —— opencode 設定スキーマには `tool` キーが無いため、ツールは本物の
MCP ツールとして提供します）。opencode 内でネイティブに使えます：

| ツール | 機能 |
| --- | --- |
| `forge_image` | テキスト → 画像（ComfyUI ローカル、Pollinations 無料フェイルオーバー） |
| `forge_video` | テキスト → 動画（Wan 2.1） |
| `forge_tts` | テキスト → 音声（Piper / edge-tts、無料、中英日韓の自動音声選択） |
| `forge_asr` | 音声 → テキスト（Whisper） |
| `forge_vision` | 画像 → 説明（`forge-chat` VLM） |
| `forge_search` | ウェブ検索（SearXNG）+ ページ取得 |
| `forge_quota` | 無料枠のリアルタイムパネル |

……さらに skills（`media-forge`、`voice-forge`、`research-forge`）、agents、スラッシュ
コマンド、プール監視 `quota-toast` プラグイン。導入は
`packages/opencode-pack/README.md` を参照してください。

## リポジトリ構成

```
apps/router      Python  FastAPI 無料枠フェイルオーバーゲートウェイ（要）
apps/core        Python  FastAPI マルチモーダル生成サービス
apps/mcp         Node    Forge ツールを MCP として公開するサーバー
apps/cli         Bun     `forge` コマンドライン
apps/ui          static  内蔵の無料枠パネル（/forge/）
packages/opencode-pack   opencode 統合パック：provider + MCP 設定 + skills + agents + commands + plugin
docker-compose.yml       一発起動のスタック
installers/              install.sh / install.ps1
```

## ドキュメント

- [`docs/architecture.md`](docs/architecture.md) — ルーターとコアの連携
- [`docs/free-providers.md`](docs/free-providers.md) — 無料プール・無料枠・注意点
- [`docs/multilingual.md`](docs/multilingual.md) — 中文 / English / 日本語 / 한국어 対応の説明
- [`docs/roadmap.md`](docs/roadmap.md) — M0 → M4

## ライセンス

Apache-2.0。サードパーティの各コンポーネントはそれぞれのライセンスを保持します —
[`NOTICE`](NOTICE) を参照。

> ⚠️ 一部の無料プランの利用規約は、自動での複数キー回転を推奨していません。omni-forge は
> 既定で単一キーのフォールオーバーを提供します。キープールはオプトインかつ自己責任です。