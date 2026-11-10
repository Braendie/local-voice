"""Small PCM helpers for ONNX and torch voices. No MLX, no audio library."""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear resample to the pipeline rate (24 kHz). Piper medium voices are 22050 Hz."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0 or src_rate == dst_rate:
        return audio
    n = int(round(audio.size * dst_rate / src_rate))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(new, old, audio).astype(np.float32)


def iter_chunks(audio: np.ndarray, sample_rate: int, chunk_ms: int = 120) -> Iterator[np.ndarray]:
    """Slices so a barge-in can stop between them. One long buffer would play out first."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    step = max(1, int(sample_rate * max(chunk_ms, 1) / 1000))
    for i in range(0, audio.size, step):
        yield np.ascontiguousarray(audio[i:i + step])
