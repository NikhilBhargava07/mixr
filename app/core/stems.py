"""Stem separation, wrapped for the app.

Demucs is slow (roughly real-time on CPU), so this runs in a background thread
and reports progress. The API polls; the UI shows a spinner. Results are cached
by file identity, so separating the same song twice is instant.
"""
import subprocess
import sys
import threading
from pathlib import Path

from . import audio

ROOT = Path(__file__).resolve().parent.parent.parent
STEM_ROOT = ROOT / "app" / "_stems"
STEM_ROOT.mkdir(parents=True, exist_ok=True)

STEM_NAMES = ["vocals", "drums", "bass", "other"]
STEM_COLORS = {"vocals": "#ff6b9d", "drums": "#ffa94d",
               "bass": "#845ef7", "other": "#38d9a9"}

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def stem_dir(src: Path) -> Path:
    return STEM_ROOT / audio._key(src)


def existing(src: Path):
    """Return {name: path} if this file has already been separated."""
    d = stem_dir(src)
    if not d.exists():
        return None
    found = {}
    for n in STEM_NAMES:
        p = d / f"{n}.wav"
        if p.exists():
            found[n] = p
    return found if len(found) == len(STEM_NAMES) else None


def _run(key: str, src: Path):
    try:
        d = stem_dir(src)
        d.mkdir(parents=True, exist_ok=True)
        wav = audio.to_wav(src)
        # demucs writes to <out>/htdemucs/<stem-of-filename>/*.wav
        subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs",
                        "-o", str(d), str(wav)], check=True, capture_output=True)
        produced = next((d / "htdemucs").iterdir())
        for n in STEM_NAMES:
            p = produced / f"{n}.wav"
            if p.exists():
                p.replace(d / f"{n}.wav")
        with _lock:
            _jobs[key] = {"state": "done", "progress": 1.0}
    except Exception as e:
        with _lock:
            _jobs[key] = {"state": "error", "error": str(e)}


def start(src: Path) -> dict:
    key = audio._key(src)
    if existing(src):
        return {"state": "done", "progress": 1.0, "cached": True}
    with _lock:
        job = _jobs.get(key)
        if job and job["state"] == "running":
            return job
        _jobs[key] = {"state": "running", "progress": 0.0}
    threading.Thread(target=_run, args=(key, src), daemon=True).start()
    return _jobs[key]


def status(src: Path) -> dict:
    if existing(src):
        return {"state": "done", "progress": 1.0}
    with _lock:
        return _jobs.get(audio._key(src), {"state": "idle", "progress": 0.0})
