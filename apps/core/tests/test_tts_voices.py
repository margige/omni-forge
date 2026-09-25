"""TTS voice-selection tests: script detection must pick a working voice per language."""

import pytest

from forge_core.backends.tts import detect_lang, pick_voice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello, how are you?", "en"),
        ("你好，这个项目支持多语言。", "zh"),
        ("こんにちは、日本語で話せます。", "ja"),
        ("안녕하세요, 한국어를 지원합니다.", "ko"),
        ("omni-forge 123", "en"),
    ],
)
def test_detect_lang(text: str, expected: str) -> None:
    assert detect_lang(text) == expected


@pytest.mark.parametrize(
    ("text", "voice"),
    [
        ("Hello there", "en-US-AriaNeural"),
        ("天气真不错", "zh-CN-XiaoxiaoNeural"),
        ("天気がいいですね", "ja-JP-NanamiNeural"),
        ("날씨가 좋네요", "ko-KR-SunHiNeural"),
    ],
)
def test_pick_voice_matches_script(text: str, voice: str) -> None:
    assert pick_voice(text, None, "en-US-AriaNeural") == voice


def test_pick_voice_respects_explicit_request() -> None:
    assert pick_voice("こんにちは", "zh-CN-XiaoxiaoNeural", "en-US-AriaNeural") == "zh-CN-XiaoxiaoNeural"