"""parakeet-mlx adapter without the model, mlx, or a Mac.

The real ``from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")`` load and a spoken Russian
utterance have to be checked on the Mac (Apple Silicon). These tests cover the text the
pipeline would hand to the agent, and that an utterance is decoded through the stream API.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from local_voice.engines.parakeet_mlx import (
    ParakeetMLXEngine,
    clean_transcript,
    decode_utterance,
    write_wav,
)


def test_clean_transcript_keeps_russian_and_drops_a_language_tag():
    assert clean_transcript("  <|ru|>  Привет,   как дела? ") == "Привет, как дела?"
    assert clean_transcript("hello   world") == "hello world"
    assert clean_transcript("") == ""
    assert clean_transcript("<|en|>Yes.\nNext.") == "Yes. Next."


class _Stream:
    def __init__(self, text: str):
        self.text = text
        self.audio = None
        self.context = None

    def transcribe_stream(self, context_size):
        self.context = context_size
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def add_audio(self, audio):
        self.audio = audio

    @property
    def result(self):
        return SimpleNamespace(text=self.text)


def test_transcribe_uses_the_stream_and_keeps_cyrillic():
    engine = ParakeetMLXEngine({"model": "mlx-community/parakeet-tdt-0.6b-v3", "context_left": 128, "context_right": 64})
    engine.model = _Stream("<|ru|> один два три")
    engine._to_mlx = lambda audio: audio
    audio = np.zeros(160, dtype=np.float32)
    assert engine.transcribe(audio) == "один два три"
    assert engine.model.context == (128, 64)
    assert np.array_equal(engine.model.audio, audio)


def test_empty_audio_is_not_decoded():
    engine = ParakeetMLXEngine({"model": "mlx-community/parakeet-tdt-0.6b-v3"})
    engine.model = _Stream("should not be used")
    assert engine.transcribe(np.zeros(0, dtype=np.float32)) == ""


class _FileModel:
    def __init__(self):
        self.path = None

    def transcribe(self, path: str):
        self.path = path
        return SimpleNamespace(text="файл прочитан")


def test_file_fallback_writes_a_wav_and_keeps_russian(tmp_path):
    model = _FileModel()
    audio = np.linspace(-0.2, 0.2, 160, dtype=np.float32)
    text = decode_utterance(model, audio, sample_rate=16000, context=(256, 256), to_mlx=lambda a: a)
    assert text == "файл прочитан"
    assert model.path.endswith("utt.wav")
    wav = tmp_path / "roundtrip.wav"
    write_wav(wav, audio, 16000)
    assert wav.stat().st_size > 44
