# Multilingual support — 中文 · English · 日本語 · 한국어

omni-forge speaks four languages end to end. Nothing is decrypt-dependent on a
client locale; each surface picks the language it can see.

| surface | how the language is chosen |
| --- | --- |
| Dashboard UI (`/forge/`) | in-page switcher (top-right) for 中文 / English / 日本語 / 한국어; defaults from your browser language, remembered in `localStorage` |
| CLI (`forge …`) | `FORGE_LANG` env var wins, else `LANG` / `LC_ALL`; `zh*` → 中文, `ja*` → 日本語, `ko*`/`kr*` → 한국어, anything else → English |
| TTS (`/v1/tts`) | auto-detects the **script** of the input text and picks a matching free `edge-tts` voice, so Chinese/Japanese/Korean text is not garbled by an English voice; an explicit `voice` always wins |
| API models & quota | machine-readable JSON keys stay English (stable contract for SDKs) |
| Docs & README | `README.md` (EN) + `README.zh-CN.md` + `README.ja-JP.md` + `README.ko-KR.md`, linked from the top of each |

## Script detection for TTS

When no `voice` is supplied, the core inspects the text and picks a default voice:

- hiragana/katakana present → `ja-JP-NanamiNeural`
- hangul present → `ko-KR-SunHiNeural`
- Han ideographs (no kana/hangul) → `zh-CN-XiaoxiaoNeural`
- otherwise → `FORGE_EDGE_VOICE` (default `en-US-AriaNeural`)

```bash
curl -X POST http://127.0.0.1:4020/v1/tts -H "content-type: application/json" \
  -d '{"text": "안녕하세요, 오늘 날씨가 좋네요"}'   # → ko-KR-SunHiNeural, Korean speech
```

Explicit selection still works and is always honoured:

```bash
curl -X POST http://127.0.0.1:4020/v1/tts -H "content-type: application/json" \
  -d '{"text": "こんにちは", "voice": "ja-JP-NanamiNeural"}'
```

## CLI example

```bash
FORGE_LANG=zh forge quota      # 中文
FORGE_LANG=ja forge status     # 日本語
LANG=ko_KR.UTF-8 forge doctor  # 한국어 via locale
```

## Note on encoding

Everything is UTF-8 end to end (HTTP JSON, files, subprocess stdin/out). Edge
cases worth knowing: `piper` voices are per-model single-language, so auto
selection only applies to the `edge-tts` backend; for offline CJK TTS install a
matching `piper` model and pass `voice=<model>` explicitly.