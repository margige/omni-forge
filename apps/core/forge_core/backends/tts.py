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

#: Default edge-tts voice per script kind.
_CJK_VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}

#: All available neural voices grouped by language.
ALL_VOICES: dict[str, list[str]] = {
    "zh": [
        "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural",
        "zh-CN-YunyangNeural", "zh-CN-XiaoyiNeural",
        "zh-CN-YunxiaNeural",
    ],
    "en": [
        "en-US-AriaNeural", "en-US-JennyNeural",
        "en-US-ChristopherNeural", "en-GB-RyanNeural",
        "en-GB-SoniaNeural", "en-US-StudioNeural",
        "en-AvaMultilingualNeural",
    ],
    "ja": ["ja-JP-NanamiNeural", "ja-JP-EmuNeural"],
    "ko": ["ko-KR-SunHiNeural", "ko-KR-InNeural"],
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


def _emotion_tags(sentence: str) -> tuple[str, str]:
    """Return (emphasis_level, extra_prosody) for a sentence based on punctuation.

    Exclamations get strong emphasis; questions get moderate emphasis
    with rising pitch; declarative sentences get none.
    """
    stripped = sentence.strip()
    if stripped.endswith("!"):
        return ("strong", 'pitch="+4%" rate="-5%" volume="+10%"')
    if stripped.endswith("?"):
        return ("moderate", 'pitch="+6%" rate="medium"')
    return ("", "")


def to_ssml(text: str, voice: str) -> str:
    """Convert plain text to expressive SSML.

    Each sentence is wrapped in `<prosody>` with punctuation-tuned
    pitch/rate/volume and `<emphasis>` for emotional weight. Paragraphs
    (blank-line separated) get a longer pause. `boundary='SentenceBoundary'`
    on the Communicate call adds natural sentence-level cadence.
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
            emphasis, extra = _emotion_tags(sent)
            pitch = f"+{1 + (2 if i % 3 == 0 else 0):+.0f}%"
            if emphasis:
                prosodies.append(
                    f'<prosody {extra}><emphasis level="{emphasis}">{sent}</emphasis></prosody>'
                )
            else:
                prosodies.append(
                    f'<prosody pitch="{pitch}">{sent}</prosody>'
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
        communicate = edge_tts.Communicate(
            ssml, voice,
            rate="-5%", volume="+0%", pitch="+0Hz",
            boundary="SentenceBoundary",
        )
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
