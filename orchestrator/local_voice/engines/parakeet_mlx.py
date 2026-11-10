"""Parakeet TDT 0.6B v3 through parakeet-mlx (kind: segmented).

The model is multilingual and picks the language itself. Russian and English both come back as
text; nothing here forces a language id, because a forced English decode drops Russian.
parakeet-mlx 0.7 takes a whole utterance through ``transcribe_stream`` (an mlx array of float
samples at 16 kHz) and also ``transcribe(path)``. This adapter prefers the stream, which does
not need ffmpeg, and falls back to a temporary wav.

Needs Apple Silicon and the ``parakeet`` extra (``uv sync --extra parakeet``). Import of
``parakeet_mlx`` happens in ``load``, so unit tests can drive ``transcribe`` with a stand-in.
The first real load, a Russian clip, and latency still have to be checked on the Mac.
"""
from __future__ import annotations

import re
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from .base import Transcriber

_TAG = re.compile(r"<\|[^|>]{0,40}\|>")


def clean_transcript(text: str) -> str:
    """One line of text. Whitespace is collapsed. Cyrillic is kept. A decoder language tag
    such as ``<|ru|>`` is dropped, the words are not."""
    return " ".join(_TAG.sub(" ", text or "").split())


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """16-bit mono wav. Used only by the file fallback, so the adapter does not need ffmpeg."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


class ParakeetMLXEngine(Transcriber):
    """One ``transcribe`` call per VAD utterance. ``sample_rate`` is 16 kHz, same as the pipeline."""

    sample_rate = 16000

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.model = None
        # Tests pass a stand-in so ``decode_utterance`` never imports mlx. None means use mlx.core.array.
        self._to_mlx = None

    def load(self) -> None:
        from parakeet_mlx import from_pretrained

        t0 = time.monotonic()
        self.model = from_pretrained(self.settings["model"])
        rate = int(getattr(getattr(self.model, "preprocessor_config", None), "sample_rate", self.sample_rate))
        if rate != self.sample_rate:
            raise RuntimeError(f"{self.settings['model']} wants {rate} Hz; the pipeline feeds {self.sample_rate} Hz")
        self.load_s = round(time.monotonic() - t0, 3)

    def warm(self) -> None:
        # The first decode compiles Metal kernels. A short sine wave pays that before anyone speaks.
        t = np.arange(self.sample_rate) / self.sample_rate
        self.transcribe((0.05 * np.sin(2 * np.pi * 200 * t)).astype(np.float32))

    def transcribe(self, audio: np.ndarray) -> str:
        audio = np.ascontiguousarray(audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return ""
        return clean_transcript(decode_utterance(
            self.model, audio, sample_rate=self.sample_rate,
            context=(int(self.settings.get("context_left", 256)), int(self.settings.get("context_right", 256))),
            to_mlx=self._to_mlx,
        ))


def decode_utterance(model, audio: np.ndarray, *, sample_rate: int, context: tuple[int, int],
                     to_mlx=None) -> str:
    """Text for one utterance. ``to_mlx`` defaults to ``mlx.core.array`` (Apple Silicon)."""
    stream = getattr(model, "transcribe_stream", None)
    if stream is not None:
        return _decode_stream(model, audio, context=context, to_mlx=to_mlx)
    if callable(getattr(model, "transcribe", None)):
        return _decode_file(model, audio, sample_rate=sample_rate)
    raise RuntimeError("parakeet-mlx model has neither transcribe_stream nor transcribe")


def _decode_stream(model, audio: np.ndarray, *, context: tuple[int, int], to_mlx) -> str:
    if to_mlx is None:
        import mlx.core as mx
        to_mlx = mx.array

        def clear() -> None:
            mx.clear_cache()
    else:
        def clear() -> None:
            return None
    with model.transcribe_stream(context_size=context) as transcriber:
        transcriber.add_audio(to_mlx(audio))
        text = str(getattr(transcriber.result, "text", "") or "")
    clear()
    return text


def _decode_file(model, audio: np.ndarray, *, sample_rate: int) -> str:
    with tempfile.TemporaryDirectory(prefix="parakeet-") as directory:
        path = Path(directory) / "utt.wav"
        write_wav(path, audio, sample_rate)
        result = model.transcribe(str(path))
    text = getattr(result, "text", result if isinstance(result, str) else "")
    return str(text or "")
