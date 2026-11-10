#!/usr/bin/env python3
"""Download Piper voices into the directory config.yaml names (default ../state/voices/piper).

    python tools/download_piper_voices.py
    python tools/download_piper_voices.py ru_RU-denis-medium

Files come from https://huggingface.co/rhasspy/piper-voices. Needs a network.
espeak-ng must be installed before synthesis (``brew install espeak-ng`` on the Mac).
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from local_voice.engines.piper_tts import VOICES, voice_files, voice_url  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "state" / "voices" / "piper"
DEFAULT_NAMES = ("ru_RU-irina-medium", "ru_RU-denis-medium", "en_US-lessac-medium")


def download(name: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in ("onnx", "onnx.json"):
        target = dest / f"{name}.{suffix}"
        if target.is_file() and target.stat().st_size > 0:
            print(f"have {target.name}")
            continue
        url = voice_url(name, suffix)
        print(f"get {url}")
        urllib.request.urlretrieve(url, target)
    voice_files(dest, name)
    print(f"ok {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("voices", nargs="*", default=list(DEFAULT_NAMES))
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    unknown = [n for n in args.voices if n not in VOICES]
    if unknown:
        raise SystemExit(f"unknown voice {unknown[0]!r}; known: {', '.join(sorted(VOICES))}")
    for name in args.voices:
        download(name, args.dir)


if __name__ == "__main__":
    main()
