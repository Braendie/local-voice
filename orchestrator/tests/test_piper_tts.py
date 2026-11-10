"""Piper and Silero adapters without ONNX, torch, or a Mac.

Hearing Irina, Denis, the English Piper voice, and Silero v5 still has to be done on the
Mac after the voice files (and, for Silero, the hub weights) are downloaded.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from local_voice.engines.pcm import iter_chunks, resample
from local_voice.engines.piper_tts import PiperTTSEngine, voice_files, voice_url
from local_voice.engines.silero_tts import SileroTTSEngine, apply_tts
from local_voice.lang import pick_lang, text_lang


def test_script_detects_russian_and_english():
    assert text_lang("Привет, как дела?") == "ru"
    assert text_lang("Hello there") == "en"
    assert text_lang("Привет hello") == "ru"          # six Cyrillic letters, five Latin
    assert text_lang("OK") == "en"
    assert text_lang("...") is None
    assert pick_lang("...", {"ru", "en"}, "en", "ru") == "en"


def test_voice_urls_point_at_the_piper_repo():
    assert voice_url("ru_RU-irina-medium").endswith(
        "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx")
    assert voice_url("ru_RU-denis-medium", "onnx.json").endswith(
        "ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx.json")
    assert voice_url("en_US-lessac-medium").endswith(
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx")
    with pytest.raises(KeyError, match="unknown Piper voice"):
        voice_url("not-a-voice")


def test_missing_voice_names_the_file(tmp_path):
    engine = PiperTTSEngine({"voice_dir": str(tmp_path), "voices": {"ru": "ru_RU-irina-medium", "en": "en_US-lessac-medium"}})
    with pytest.raises(FileNotFoundError, match="ru_RU-irina-medium"):
        engine.load()
    (tmp_path / "ru_RU-irina-medium.onnx").write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="onnx.json"):
        voice_files(engine.voice_dir, "ru_RU-irina-medium")


class _Voice:
    def __init__(self, rate: int, value: float):
        self.rate = rate
        self.value = value
        self.texts: list[str] = []

    def synthesize(self, text, syn_config=None, **kwargs):
        self.texts.append(text)
        n = int(self.rate * 0.05)
        yield SimpleNamespace(audio_float_array=np.full(n, self.value, np.float32), sample_rate=self.rate)


def _piper(tmp_path) -> tuple[PiperTTSEngine, _Voice, _Voice]:
    engine = PiperTTSEngine({
        "voice_dir": str(tmp_path),
        "voices": {"ru": "ru_RU-irina-medium", "en": "en_US-lessac-medium"},
        "default_lang": "ru", "sample_rate": 24000, "chunk_ms": 1000,
        "length_scale": 1.0,
    })
    ru, en = _Voice(22050, 0.25), _Voice(22050, -0.25)
    engine.voices = {"ru": ru, "en": en}
    return engine, ru, en


def test_a_russian_reply_uses_irina_and_english_uses_lessac(tmp_path):
    engine, ru, en = _piper(tmp_path)
    ru_audio = np.concatenate(list(engine.stream("Привет, это проверка.")))
    en_audio = np.concatenate(list(engine.stream("Hello, this is a check.")))
    assert ru.texts == ["Привет, это проверка."] and en.texts == ["Hello, this is a check."]
    assert ru_audio.mean() > 0 and en_audio.mean() < 0
    # 50 ms at 22050 Hz becomes 50 ms at 24000 Hz.
    assert abs(ru_audio.size - int(round(22050 * 0.05 * 24000 / 22050))) <= 1


def test_resample_and_chunks_cover_the_buffer():
    audio = np.arange(22050, dtype=np.float32)
    out = resample(audio, 22050, 24000)
    assert abs(out.size - 24000) <= 1
    assert resample(audio, 22050, 22050) is not None and resample(audio, 22050, 22050).size == audio.size
    parts = list(iter_chunks(np.arange(100, dtype=np.float32), 1000, chunk_ms=10))
    assert sum(p.size for p in parts) == 100 and parts[0].size == 10


class _Silero:
    def __init__(self):
        self.kwargs = None

    def apply_tts(self, **kwargs):
        self.kwargs = kwargs
        return np.ones(int(kwargs["sample_rate"] * 0.05), dtype=np.float32)


def test_silero_russian_uses_v5_speaker_and_english_falls_back(tmp_path):
    engine = SileroTTSEngine({"model_id": "v5_ru", "speaker": "xenia", "sample_rate": 24000, "default_lang": "ru"})
    engine.model = _Silero()
    audio = np.concatenate(list(engine.stream("Добрый день.")))
    assert audio.size == 1200
    assert engine.model.kwargs["speaker"] == "xenia"
    assert engine.model.kwargs["put_stress_homo"] is True
    list(engine.stream("Good afternoon."))
    assert engine.model.kwargs["text"] == "Good afternoon."   # no English model: the Russian voice speaks it


def test_silero_english_model_is_used_when_configured():
    engine = SileroTTSEngine({"model_id": "v5_ru", "speaker": "xenia", "en_model_id": "v3_en",
                              "en_speaker": "en_0", "sample_rate": 24000})
    engine.model = _Silero()
    engine.en_model = _Silero()
    engine._langs.add("en")
    list(engine.stream("Good afternoon."))
    assert engine.en_model.kwargs["speaker"] == "en_0"
    assert engine.model.kwargs is None


def test_apply_tts_drops_stress_flags_when_the_model_rejects_them():
    class Old:
        def apply_tts(self, text, speaker, sample_rate):
            return np.array([0.0, 1.0], dtype=np.float32)

    audio = apply_tts(Old(), "Привет", "xenia", 24000, stress=True)
    assert audio.tolist() == [0.0, 1.0]
