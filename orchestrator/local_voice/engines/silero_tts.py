"""Silero TTS v5 Russian, an optional backend next to Piper.

``model_id`` is the hub speaker id (``v5_ru`` by default; ``v5_6_ru`` is a newer drop-in).
``speaker`` is the person (``xenia``). The package is ``silero`` (``silero_tts``); if it is
not installed, ``torch.hub.load('snakers4/silero-models')`` is used. Both need a Mac (or any
machine with torch) and a download on first load. This module does not import torch until
``load``.

Silero v5 here is a Russian model. An English reply uses it too, unless ``en_model_id``
names a second model. Piper is the backend that has a real English voice.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np

from ..lang import pick_lang
from .base import Synthesizer
from .pcm import iter_chunks


def apply_tts(model: Any, text: str, speaker: str, sample_rate: int, *, stress: bool) -> np.ndarray:
    """``apply_tts``. v5 takes stress flags; an older model that rejects them is called without them."""
    kwargs: dict[str, Any] = {"text": text, "speaker": speaker, "sample_rate": sample_rate}
    if stress:
        kwargs.update(put_accent=True, put_yo=True, put_stress_homo=True, put_yo_homo=True)
    try:
        audio = model.apply_tts(**kwargs)
    except TypeError:
        if not stress:
            raise
        audio = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def load_silero(language: str, model_id: str, repo: str) -> Any:
    """The Silero model object. Tries the pip package, then torch.hub."""
    try:
        from silero import silero_tts
    except ImportError:
        silero_tts = None
    if silero_tts is not None:
        model, _example = silero_tts(language=language, speaker=model_id)
    else:
        import torch
        model, _example = torch.hub.load(repo_or_dir=repo, model="silero_tts", language=language,
                                          speaker=model_id, trust_repo=True)
    to = getattr(model, "to", None)
    if to is not None:
        model = to("cpu")
    return model


class SileroTTSEngine(Synthesizer):
    sample_rate = 24000

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.sample_rate = int(settings.get("sample_rate", 24000))
        self.model = None
        self.en_model = None
        self._langs = {"ru"}
        if str(settings.get("en_model_id") or "").strip():
            self._langs.add("en")
        self._lang = str(settings.get("default_lang") or "ru")

    def load(self) -> None:
        import time

        t0 = time.monotonic()
        repo = str(self.settings.get("repo") or "snakers4/silero-models")
        self.model = load_silero(str(self.settings.get("language") or "ru"),
                                 str(self.settings.get("model_id") or "v5_ru"), repo)
        en_id = str(self.settings.get("en_model_id") or "").strip()
        if en_id:
            self.en_model = load_silero(str(self.settings.get("en_language") or "en"), en_id, repo)
            self._langs.add("en")
        self.load_s = round(time.monotonic() - t0, 3)

    def choose_lang(self, text: str) -> str:
        self._lang = pick_lang(text, set(self._langs), self._lang, str(self.settings.get("default_lang") or "ru"))
        return self._lang

    def stream(self, text: str) -> Iterator[np.ndarray]:
        text = " ".join((text or "").split())
        if not text:
            return
        if self.model is None:
            raise RuntimeError("Silero is not loaded")
        lang = self.choose_lang(text)
        if lang == "en" and self.en_model is not None:
            model, speaker = self.en_model, str(self.settings.get("en_speaker") or self.settings.get("speaker") or "xenia")
        else:
            model, speaker = self.model, str(self.settings.get("speaker") or "xenia")
        audio = apply_tts(model, text, speaker, self.sample_rate, stress=bool(self.settings.get("stress", True)))
        yield from iter_chunks(audio, self.sample_rate, int(self.settings.get("chunk_ms", 120)))

    def describe(self) -> dict:
        out = super().describe()
        out.update({"model_id": self.settings.get("model_id", "v5_ru"), "speaker": self.settings.get("speaker", "xenia"),
                    "en_model_id": self.settings.get("en_model_id") or None, "lang": self._lang})
        return out
