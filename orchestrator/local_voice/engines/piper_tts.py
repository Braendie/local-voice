"""Piper TTS. Russian and English are different voices; the voice follows the reply.

Default voices: ``ru_RU-irina-medium`` and ``en_US-lessac-medium``. ``ru_RU-denis-medium``
is the other Russian voice: set ``voices.ru`` to it. Voices are ONNX files under
``voice_dir`` (``<name>.onnx`` and ``<name>.onnx.json``), downloaded by
``tools/download_piper_voices.py``. Piper's medium voices are 22050 Hz; chunks are
resampled to the pipeline rate (24 kHz).

``piper-tts`` and espeak-ng are imported and required only in ``load``. Unit tests inject
a stand-in voice. Synthesis quality has to be heard on the Mac.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from ..config import expand
from ..lang import pick_lang
from .base import Synthesizer
from .pcm import iter_chunks, resample

# (language, locale, speaker, quality) inside rhasspy/piper-voices.
VOICE_REPO = "rhasspy/piper-voices"
VOICES = {
    "ru_RU-irina-medium": ("ru", "ru_RU", "irina", "medium"),
    "ru_RU-denis-medium": ("ru", "ru_RU", "denis", "medium"),
    "en_US-lessac-medium": ("en", "en_US", "lessac", "medium"),
}


def voice_repo_path(name: str, suffix: str = "onnx") -> str:
    """Path of one file inside the rhasspy/piper-voices repo. ``suffix`` is ``onnx`` or ``onnx.json``."""
    try:
        language, locale, speaker, quality = VOICES[name]
    except KeyError as e:
        known = ", ".join(sorted(VOICES))
        raise KeyError(f"unknown Piper voice {name!r} (known: {known})") from e
    return f"{language}/{locale}/{speaker}/{quality}/{name}.{suffix}"


def voice_url(name: str, suffix: str = "onnx") -> str:
    return f"https://huggingface.co/{VOICE_REPO}/resolve/main/{voice_repo_path(name, suffix)}"


def voice_files(voice_dir: Path, name: str) -> tuple[Path, Path]:
    """The onnx model and its json config. Raises FileNotFoundError naming the missing file."""
    model = voice_dir / f"{name}.onnx"
    config = voice_dir / f"{name}.onnx.json"
    missing = [p.name for p in (model, config) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Piper voice {name} is incomplete in {voice_dir} (missing {', '.join(missing)}). "
            f"Download with: python tools/download_piper_voices.py {name}")
    return model, config


def chunk_audio(chunk: Any) -> np.ndarray:
    """Float32 mono from a piper AudioChunk, a numpy array, or raw int16 bytes."""
    if isinstance(chunk, np.ndarray):
        return np.asarray(chunk, dtype=np.float32).reshape(-1)
    audio = getattr(chunk, "audio_float_array", None)
    if audio is not None:
        return np.asarray(audio, dtype=np.float32).reshape(-1)
    pcm = getattr(chunk, "audio_int16_bytes", None)
    if pcm is None and isinstance(chunk, (bytes, bytearray)):
        pcm = bytes(chunk)
    if pcm is not None:
        return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    raise TypeError(f"Piper returned {type(chunk).__name__}, which has no audio")


def synthesize(voice: Any, text: str, settings: dict):
    """``PiperVoice.synthesize``, new SynthesisConfig API or the older keyword arguments."""
    kwargs = {k: settings[k] for k in ("length_scale", "noise_scale", "noise_w_scale") if settings.get(k) is not None}
    try:
        from piper import SynthesisConfig
    except ImportError:
        SynthesisConfig = None
    if SynthesisConfig is not None and kwargs:
        config = SynthesisConfig(
            length_scale=kwargs.get("length_scale", 1.0),
            noise_scale=kwargs.get("noise_scale", 0.667),
            noise_w_scale=kwargs.get("noise_w_scale", 0.8),
        )
        try:
            return voice.synthesize(text, syn_config=config)
        except TypeError:
            pass
    legacy = {}
    if "length_scale" in kwargs:
        legacy["length_scale"] = kwargs["length_scale"]
    if "noise_scale" in kwargs:
        legacy["noise_scale"] = kwargs["noise_scale"]
    if "noise_w_scale" in kwargs:
        legacy["noise_w"] = kwargs["noise_w_scale"]
    return voice.synthesize(text, **legacy)


class PiperTTSEngine(Synthesizer):
    sample_rate = 24000

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.sample_rate = int(settings.get("sample_rate", 24000))
        self.voice_dir = expand(settings.get("voice_dir") or "../state/voices/piper")
        self._names = {str(k): str(v) for k, v in dict(settings.get("voices") or {
            "ru": "ru_RU-irina-medium", "en": "en_US-lessac-medium"}).items()}
        if not self._names:
            raise ValueError("piper voices is empty; set voices.ru and voices.en")
        self._lang = str(settings.get("default_lang") or "ru")
        self.voices: dict[str, Any] = {}
        self.native_rate: int | None = None

    def load(self) -> None:
        import time

        # Name a missing file before importing piper, so a fresh checkout fails with the download hint.
        paths = {lang: voice_files(self.voice_dir, name) for lang, name in self._names.items()}
        from piper import PiperVoice

        t0 = time.monotonic()
        loaded = {}
        for lang, (model, _config) in paths.items():
            loaded[lang] = PiperVoice.load(str(model))
        self.voices = loaded
        first = next(iter(loaded.values()))
        self.native_rate = int(getattr(getattr(first, "config", None), "sample_rate", 22050))
        self.load_s = round(time.monotonic() - t0, 3)

    def choose_lang(self, text: str) -> str:
        self._lang = pick_lang(text, set(self._names), self._lang, str(self.settings.get("default_lang") or "ru"))
        return self._lang

    def stream(self, text: str) -> Iterator[np.ndarray]:
        text = " ".join((text or "").split())
        if not text:
            return
        if not self.voices:
            raise RuntimeError("Piper voices are not loaded")
        lang = self.choose_lang(text)
        voice = self.voices[lang]
        step = int(self.settings.get("chunk_ms", 120))
        for chunk in synthesize(voice, text, self.settings):
            rate = int(getattr(chunk, "sample_rate", self.native_rate or self.sample_rate))
            yield from iter_chunks(resample(chunk_audio(chunk), rate, self.sample_rate), self.sample_rate, step)

    def describe(self) -> dict:
        out = super().describe()
        out.update({"voices": dict(self._names), "voice_dir": str(self.voice_dir),
                    "native_rate": self.native_rate, "lang": self._lang})
        return out
