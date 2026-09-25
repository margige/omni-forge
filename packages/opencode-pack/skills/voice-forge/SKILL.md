---
name: voice-forge
description: Synthesize speech and transcribe audio with the local omni-forge core. Use when the user asks to speak text aloud, make a voiceover, or transcribe an audio file.
---

# Voice Forge

Text-to-speech and speech-to-text through the omni-forge core.

## Prerequisites
- `forge core` running.
- TTS: works out of the box via `edge-tts` (no key). For fully offline speech set `FORGE_PIPER_MODEL` + `piper` on PATH.
- ASR: `whisper` CLI (`openai-whisper` or `faster-whisper`) on PATH.

## Steps
1. **TTS**: call `forge_tts` with `text` and optional `voice` (e.g. `zh-CN-XiaoxiaoNeural`, `en-US-AriaNeural`). Returns an mp3 URL.
2. **ASR**: call the MCP tool `forge_asr` with an audio file path. Returns the transcript.

## Notes
- Keep text under ~400 words per clip for reliable edge-tts output.
- Voiceover for a video: generate the script → one `forge_tts` call per line or paragraph, then join the mp3 files.