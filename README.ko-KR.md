# omni-forge

> **무료 우선, 로컬 우선의 opencode 멀티모달 생성 스택입니다.**
> 텍스트 · 이미지 · 비디오 · 음성 · 비전 · 검색 — 여러 무료 티어를 자동으로 페일오버하여
> 어떤 모델의 무료 할당량이 소진되면 다음 모델이 자연스럽게 이어받습니다.

한국어 | [English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

omni-forge는 훌륭한 오픈소스 프로젝트들을 **하나의 친숙한 앱**과 네이티브 **opencode
통합 팩**으로 묶습니다. 편집기를 단일 로컬 엔드포인트에 연결하기만 하면 속도 제한,
할당량, API 키를 신경 쓸 필요가 없습니다.

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

## 왜

단일 프로바이더 CLI는 무료 할당량이 소진되는 순간 멈춥니다. omni-forge는 '무료'를 단일
계정이 아니라 **풀(pool)**로 취급합니다. 각 요청을 가장 먼저 정상인 무료 프로바이더로
라우팅하고, 소진된 프로바이더는 쿨다운시키며, 클라우드가 모두 마르면 로컬 모델로
폴백합니다. 호출 측이 보는 모델명은 언제나 하나: `forge-chat`입니다.

> 편집기에는 항상 `forge-chat` 모델 하나만 보입니다. 라우터가 '최우선순위 정상
> 프로바이더 → 쿨다운 → 다음 → 로컬' 순서로 처리합니다.

## 빠른 시작

```bash
# 1. 설치 (Windows: installers\install.ps1, 그 외: installers\install.sh)
#    .venv 생성, router+core 빌드, 설정 템플릿 복사
./installers/install.sh

# 2. 보유한 API 키(전부 선택 사항)를 .env와 providers.yaml에 추가

# 3. 두 서비스 시작
. .venv/bin/activate
python -m uvicorn forge_router.main:app --port 4010 &
python -m uvicorn forge_core.main:app --port 4020 &

# 4. 상태와 무료 할당량 확인
curl http://127.0.0.1:4010/forge/quota
curl http://127.0.0.1:4020/forge/health
```

한 번의 명령으로 router·core·Ollama·SearXNG·Open WebUI를 함께 띄우려면:

```bash
docker compose up -d          # + `--profile local`로 ollama, `--profile gpu`로 comfyui
open http://127.0.0.1:4010/forge/   # 내장 패널 & 빠른 생성기 (中文/English/日本語/한국어 지원)
```

`bun`을 설치하면 `apps/cli`에서 `forge up|down|status|doctor|quota|gen|mcp`를 쓸 수
있습니다. CLI 메시지는 `FORGE_LANG`(또는 `LANG`/`LC_ALL`)에 따라 한국어·영어·중국어·
일본어로 표시됩니다.

## opencode에서 사용

`packages/opencode-pack/`을 프로젝트로 복사한 뒤 설정을 등록합니다:

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

이 설정으로 `omni-forge` 프로바이더와 `forge` MCP 서버가 등록됩니다(도구는 MCP가
제공합니다 — opencode 설정 스키마에는 `tool` 키가 없어 실제 MCP 도구로 제공합니다).
opencode 안에서 네이티브로 쓸 수 있습니다:

| 도구 | 기능 |
| --- | --- |
| `forge_image` | 텍스트 → 이미지 (ComfyUI 로컬, Pollinations 무료 폴백) |
| `forge_video` | 텍스트 → 비디오 (Wan 2.1) |
| `forge_tts` | 텍스트 → 음성 (Piper / edge-tts, 무료, 중/영/일/한 자동 음성 선택) |
| `forge_asr` | 음성 → 텍스트 (Whisper) |
| `forge_vision` | 이미지 → 설명 (`forge-chat` VLM) |
| `forge_search` | 웹 검색 (SearXNG) + 페이지 스크랩 |
| `forge_quota` | 실시간 무료 할당량 패널 |

……그리고 skills(`media-forge`, `voice-forge`, `research-forge`), agents, 슬래시
명령, 풀을 감시하는 `quota-toast` 플러그인. 설치 방법은
`packages/opencode-pack/README.md`를 참조하세요.

## 저장소 구성

```
apps/router      Python  FastAPI 무료 티어 페일오버 게이트웨이 (핵심)
apps/core        Python  FastAPI 멀티모달 생성 서비스
apps/mcp         Node    Forge 도구를 MCP로 노출하는 서버
apps/cli         Bun     `forge` 커맨드라인
apps/ui          static  내장 할당량 패널 (/forge/)
packages/opencode-pack   opencode 팩: provider + MCP 설정 + skills + agents + commands + plugin
docker-compose.yml       한 번에 올리는 스택
installers/              install.sh / install.ps1
```

## 문서

- [`docs/architecture.md`](docs/architecture.md) — 라우터와 코어의 연동 방식
- [`docs/free-providers.md`](docs/free-providers.md) — 무료 풀·할당량·유의사항
- [`docs/multilingual.md`](docs/multilingual.md) — 中文 / English / 日本語 / 한국어 지원 설명
- [`docs/roadmap.md`](docs/roadmap.md) — M0 → M4

## 라이선스

Apache-2.0. 서드파티 컴포넌트는 각자의 라이선스를 유지합니다 — [`NOTICE`](NOTICE) 참조.

> ⚠️ 일부 무료 티어의 이용약관은 자동 다중 키 로테이션을 권장하지 않습니다. omni-forge는
> 기본적으로 단일 키 페일오버를 제공하며, 키 풀은 옵트인이며 사용자 책임입니다.