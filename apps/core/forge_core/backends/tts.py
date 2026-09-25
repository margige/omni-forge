"""Text-to-speech backends.

`edge-tts` is free and needs no key — the default. `piper` is fully offline.
Both write a file and return its URL.
"""

from __future__ import annotations

import asyncio
import re
import shutil

from ..config import CoreConfig
from ..util import media_url, save_bytes
from .base import Backend

#: Default edge-tts voice per script kind; picking a mismatched voice garbles CJK.
_CJK_VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}

#: Split on sentence-ending punctuation (keeping the delimiter attached).
_SENTENCE_RE = re.compile(r'(?<=[。！？.!?])\s*')
#: Two or more newlines mark a paragraph boundary.
_PARAGRAPH_RE = re.compile(r'\n{2,}')


def detect_lang(text: str) -> str:
    """Best-effort script detection.

    Kana wins => ja (hangul => ko) because they are unambiguous to their
    languages; Han ideographs alone => zh; otherwise English.
    """
    has_kana = has_hangul = has_han = False
    for ch in text:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            has_kana = True
        elif 0xAC00 <= code <= 0xD7A3:
            has_hangul = True
        elif 0x4E00 <= code <= 0x9FFF:
            has_han = True
    if has_kana:
        return "ja"
    if has_hangul:
        return "ko"
    if has_han:
        return "zh"
    return "en"


def pick_voice(text: str, requested: str | None, default_en: str) -> str:
    """Explicit voice wins; otherwise match a default edge-tts voice to the text's script."""
    if requested:
        return requested
    return _CJK_VOICES.get(detect_lang(text), default_en)


def _xml_lang(voice: str) -> str:
    """Extract language-region from a voice name, e.g. zh-CN-XiaoxiaoNeural -> zh-CN."""
    parts = voice.split("-")
    return f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else voice


def _prosody_for(sentence: str) -> tuple[str, str, str]:
    """Return (pitch, rate, volume) attributes for a sentence based on its ending."""
    stripped = sentence.strip()
    if stripped.endswith("?"):
        return ("+6%", "medium", "+0%")
    if stripped.endswith("!"):
        return ("+4%", "-6%", "+12%")
    # Declarative: subtle natural variation based on sentence index handled by caller
    return ("+1%", "medium", "+0%")


def to_ssml(text: str, voice: str) -> str:
    """Convert plain text to expressive SSML.

    Sentences are wrapped in `<prosody>` tags tuned by their punctuation
    (rising pitch for questions, louder/faster for exclamations). Paragraphs
    (separated by blank lines) receive a longer pause. All input is streamed
    by edge-tts regardless of length.
    """
    lang = _xml_lang(voice)
    paragraphs = _PARAGRAPH_RE.split(text.strip())
    para_blocks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = [s.strip() for s in _SENTENCE_RE.split(para) if s.strip()]
        if not sentences:
            continue
        prosodies = []
        for i, sent in enumerate(sentences):
            pitch_base, rate_base, vol_base = _prosody_for(sent)
            # Add subtle index-based variation so adjacent sentences don't sound identical
            pitch_val = float(pitch_base.replace("%", "")) + (2 if i % 2 == 0 else -1)
            vol_val = float(vol_base.replace("+", "").replace("%", ""))
            if vol_base != "+0%":
                vol_str = f"+{vol_val:.0f}%"
            else:
                vol_str = f"+{1 if i % 2 == 0 else 0}%"
            prosodies.append(
                f'<prosody pitch="{pitch_val:+.0f}%" rate="{rate_base}" volume="{vol_str}">{sent}</prosody>'
            )
        para_blocks.append('<break time="400ms"/>'.join(prosodies))
    body = '<break time="900ms"/>'.join(para_blocks)
    return (
        f'<speak version="1.0" '
        f'xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{lang}">'
        f'<voice name="{voice}">'
        f'{body}</voice></speak>'
    )


class EdgeTTSBackend(Backend):
    name = "edge-tts"
    capability = "tts"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    async def run(self, *, text: str, voice: str | None = None, **_: object) -> dict:
        import edge_tts

        voice = pick_voice(text, voice, self.config.edge_voice)
        ssml = to_ssml(text, voice)
        audio = b""
        communicate = edge_tts.Communicate(ssml, voice, rate="-5%", volume="+0%")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        path = save_bytes(self.config.output_dir, audio, ".mp3", "speech")
        return {"backend": self.name, "path": str(path), "url": media_url(path), "voice": voice}


class PiperBackend(Backend):
    name = "piper"
    capability = "tts"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        return bool(self.config.piper_model) and shutil.which(self.config.piper_bin) is not None

    async def run(self, *, text: str, **_: object) -> dict:
        model = self.config.piper_model
        assert model and self.config.piper_bin
        proc = await asyncio.create_subprocess_exec(
            self.config.piper_bin,
            "--model",
            model,
            "--output_file",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"piper failed: {stderr.decode('utf-8', 'replace')}")
        path = save_bytes(self.config.output_dir, stdout, ".wav", "speech")
        return {"backend": self.name, "path": str(path), "url": media_url(path), "voice": model}
