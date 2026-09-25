# Free tiers you can wire in (single key = one provider each)

Set one or more in your `.env`. The router figures out who is live and rotates
on quota exhaustion. All of these speak the OpenAI-compatible format the router
expects.

## Cloud

| provider | env var | model | notes |
|---|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` | broad free quota; `rpd` cap set in config |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | very fast inference; `rpm` cap |
| Cerebras | `CEREBRAS_API_KEY` | `llama3.3-70b` | wafer-scale, fast |
| NVIDIA NIM | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` | generous free credits |
| Mistral | `MISTRAL_API_KEY` | `mistral-small-latest` | |
| OpenRouter | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct:free` | ":free" models route round-robin |
| GitHub Models | `GITHUB_MODELS_TOKEN` | `gpt-4o-mini` | free GitHub token (scope: Models) |
| Hugging Face | `HF_TOKEN` | `meta-llama/Llama-3.3-70B-Instruct` | |
| Together | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo-Free` | |

## Local / no-key

| backend | config | role |
|---|---|---|
| Ollama | `OLLAMA_BASE_URL` (`http://127.0.0.1:11434/v1`) | final safety net, fully offline |
| LocalAI | `LOCALAI_BASE_URL` (`http://127.0.0.1:8080/v1`) + optional key | final safety net |
| Pollinations (image) | none | keyless, zero-config image fallback |
| edge-tts | none | keyless cloud TTS |
| Piper (tts) | `FORGE_PIPER_MODEL` | fully offline TTS |
| Whisper (asr) | `whisper` on PATH | local transcription |
| SearXNG (search) | `SEARXNG_BASE_URL` | self-hosted private search |
| DuckDuckGo (search) | none | keyless search fallback |

## About multiple keys

Single key per provider is the default: it keeps your account clearly visible
and stays inside every provider's ToS. The router's **failover** already makes
a pile of different free accounts transparently interchangeable. Only add
multiple keys **for the same provider** if you have read that provider's terms
and confirmed it is permitted — that is why the key pool in the ledger is
optional and off by default.

## Typical "zero spend" setup

```
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
GEMINI_API_KEY=...
GROQ_API_KEY=...
# leave the rest empty
```

Daily usage will drain Gemini → Groq → Ollama (or Ollama → Gemini → Groq if you
set the priorities in `providers.yaml` the other way). Image = Pollinations.
Speech = edge-tts. All free, all functional from the first `install.ps1`.