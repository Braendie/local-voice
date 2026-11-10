"""Which language a line is in: Russian or English, judged by script.

A line with at least as many Cyrillic letters as Latin letters, and at least one
Cyrillic letter, is Russian. Digits and punctuation do not vote. A line with no
letters has no language (the caller keeps the previous one).
"""
from __future__ import annotations

import re

_CYR = re.compile("[А-Яа-яЁё]")
_LAT = re.compile("[A-Za-z]")


def text_lang(text: str) -> str | None:
    cyr = len(_CYR.findall(text or ""))
    lat = len(_LAT.findall(text or ""))
    if cyr == 0 and lat == 0:
        return None
    return "ru" if cyr >= lat else "en"


def pick_lang(text: str, available: set[str], current: str, default: str) -> str:
    """The voice to use. A detected language wins when that voice exists; otherwise the
    previous choice, then the default."""
    detected = text_lang(text)
    if detected in available:
        return detected
    if current in available:
        return current
    if default in available:
        return default
    if not available:
        raise KeyError("no voices configured")
    return sorted(available)[0]
