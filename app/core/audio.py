"""Thin wrappers over the analysis code we already have.

Nothing new is invented here — this is the adapter layer between the HTTP API
and the working code in analysis/ and engine/. Keeping it thin on purpose: if
a measurement is wrong, it should be wrong in ONE place (the original module),
not duplicated here.
"""
import hashlib
import json
import subprocess
import threading
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "app" / "_cache"
CACHE.mkdir(parents=True, exist_ok=True)

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _key(path: Path) -> str:
    """Cache key: path + mtime + size, so edits invalidate automatically."""
    st = path.stat()
    return hashlib.sha1(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:16]


def to_wav(src: Path) -> Path:
    """Everything downstream expects 44.1k WAV. afconvert ships with macOS."""
    if src.suffix.lower() == ".wav":
        return src
    out = CACHE / f"{_key(src)}.wav"
    if not out.exists():
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", "-c", "2",
                        str(src), str(out)], check=True, capture_output=True)
    return out


# The cache holds only things that can be rebuilt: format conversions, warp
# renders, waveform pictures, analysis results. Nothing here is user work —
# projects live in app/_projects, stems in app/_stems, mixes in mixes/. So it
# is always safe to delete; the only cost is rebuilding.
CACHE_LIMIT = 2_000_000_000        # ~2 GB, then the oldest renders go


def cache_stats() -> dict:
    files = [f for f in CACHE.glob("*") if f.is_file()]
    by = {}
    for f in files:
        kind = ("warp render" if f.name.startswith(("warp_", "win_"))
                else "converted audio" if f.suffix == ".wav"
                else "waveform" if f.name.startswith("wave_")
                else "analysis")
        e = by.setdefault(kind, {"files": 0, "bytes": 0})
        e["files"] += 1
        e["bytes"] += f.stat().st_size
    return {"bytes": sum(f.stat().st_size for f in files), "files": len(files),
            "limit": CACHE_LIMIT, "by_kind": by}


def prune_cache(limit: int = None, now: float = None) -> int:
    """Drop the least recently used files until the cache fits. Returns bytes freed.

    Files touched in the last minute are left alone: a render may still be
    writing them, or a clip may be about to play them.
    """
    import time
    limit = CACHE_LIMIT if limit is None else limit
    now = time.time() if now is None else now
    files = sorted((f for f in CACHE.glob("*") if f.is_file()),
                   key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    freed = 0
    for f in files:
        if total - freed <= limit:
            break
        if now - f.stat().st_mtime < 60:
            continue
        size = f.stat().st_size
        try:
            f.unlink()
            freed += size
        except OSError:
            pass
    return freed


def clear_cache(kind: str = "renders") -> int:
    """Delete cached audio. 'renders' keeps analysis and waveforms (cheap to
    keep, slow to recompute); 'all' empties the lot."""
    freed = 0
    for f in CACHE.glob("*"):
        if not f.is_file():
            continue
        if kind == "renders" and not (f.name.startswith(("warp_", "win_")) or f.suffix == ".wav"):
            continue
        size = f.stat().st_size
        try:
            f.unlink()
            freed += size
        except OSError:
            pass
    return freed


# One lock per warp output: the browser asks for a stretched clip's waveform
# and its audio at nearly the same moment, and both would otherwise launch
# Rubber Band and write the same file.
_warp_locks: dict[str, threading.Lock] = {}
_warp_guard = threading.Lock()


def warped(path: Path, pins=(), pitch: float = 0.0, mode: str = "beats") -> Path:
    """The whole file, warped by a pin map and/or pitch-shifted, as a cached WAV.

    Preview and export both read this exact file, so what you hear in the
    browser is sample-for-sample what gets rendered.

    Engine choice was measured on a click track (tests/warp_accuracy.py):
      beats  R2, --crisp 6   hits land within ~3 ms of where the pins put them
      tones  R2, default     smoother on sustained sound, but hits land ~16 ms
                             EARLY — a flam-sized error on drums
    R3 (--fine) sounds finer but ignores --timemap entirely, so it's unusable.
    """
    from . import warp as W
    pins = list(pins)
    if not pins and abs(pitch) < 1e-6:
        return to_wav(path)
    if mode not in W.MODES:
        raise ValueError(f"unknown warp mode {mode!r}")
    src = to_wav(path)
    out = CACHE / f"warp_{_key(path)}_{W.signature(pins, pitch, mode)}.wav"
    with _warp_guard:
        lock = _warp_locks.setdefault(out.name, threading.Lock())
    with lock:
        if not out.exists():
            import soundfile as sf
            info = sf.info(str(src))
            cmd = ["rubberband", "-q", "-p", f"{pitch:.3f}"]
            if mode == "beats":
                cmd += ["-c", "6"]
            else:
                cmd += ["-F"]                      # keep vocal formants when repitching
            tmp = out.with_name(out.stem + ".part.wav")
            if pins:
                frames, end = W.rubberband_map(pins, info.duration, info.samplerate)
                mapfile = out.with_name(out.stem + ".map.txt")
                mapfile.write_text("".join(f"{a} {b}\n" for a, b in frames))
                cmd += ["-D", f"{end:.6f}", "-M", str(mapfile)]
            subprocess.run(cmd + [str(src), str(tmp)], check=True, capture_output=True)
            tmp.replace(out)
            prune_cache()
    return out


def warped_window(path: Path, pins=(), pitch: float = 0.0, mode: str = "beats",
                  offset: float = 0.0, length: float = 0.0):
    """Warp only the stretch of a file that a clip actually plays.

    Returns (wav path, base) where `base` is the warped-file time the returned
    audio starts at — the caller subtracts it to find where a clip's offset
    lands inside this file.

    Preview and export both come through here with the same clip numbers, so
    they get the same cached file and stay sample-for-sample identical. The
    slice is padded well beyond the clip, so Rubber Band's edge behaviour never
    lands inside the audio you actually hear.
    """
    from . import warp as W
    pins = list(pins)
    src = to_wav(path)
    info = sf.info(str(src))
    if not pins and abs(pitch) < 1e-6:
        return src, 0.0

    d0, d1 = W.window_for(offset, length)
    s0 = max(0.0, W.dst_to_src(pins, d0))
    s1 = min(info.duration, W.dst_to_src(pins, d1))
    if s1 - s0 >= info.duration - 1e-6:                  # the whole file anyway
        return warped(path, pins, pitch, mode), 0.0

    sig = W.signature(pins, pitch, mode)
    out = CACHE / f"win_{_key(path)}_{sig}_{s0:.3f}_{s1:.3f}.wav"
    base = W.src_to_dst(pins, s0)
    with _warp_guard:
        lock = _warp_locks.setdefault(out.name, threading.Lock())
    with lock:
        if out.exists():
            return out, base
        sub, _ = W.sub_map(pins, s0, s1)
        sr = info.samplerate
        y, _ = sf.read(str(src), start=int(s0 * sr), stop=int(s1 * sr), always_2d=True)
        slice_wav = out.with_name(out.stem + ".src.wav")
        sf.write(slice_wav, y, sr)
        mapfile = out.with_name(out.stem + ".map.txt")
        mapfile.write_text("".join(f"{round(a * sr)} {round(b * sr)}\n" for a, b in sub))
        cmd = ["rubberband", "-q", "-p", f"{pitch:.3f}"]
        cmd += ["-c", "6"] if mode == "beats" else ["-F"]
        tmp = out.with_name(out.stem + ".part.wav")
        subprocess.run(cmd + ["-D", f"{sub[-1][1]:.6f}", "-M", str(mapfile),
                              str(slice_wav), str(tmp)], check=True, capture_output=True)
        tmp.replace(out)
        slice_wav.unlink(missing_ok=True)
        mapfile.unlink(missing_ok=True)
        prune_cache()
    return out, base


def waveform(path: Path, buckets: int = 2000) -> dict:
    """Min/max envelope per bucket — what a DAW draws. Cheap and cacheable."""
    cache = CACHE / f"wave_{_key(path)}_{buckets}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    y, sr = librosa.load(to_wav(path), sr=8000, mono=True)
    n = len(y)
    edges = np.linspace(0, n, buckets + 1).astype(int)
    mins, maxs = [], []
    for i in range(buckets):
        seg = y[edges[i]:edges[i + 1]]
        if len(seg) == 0:
            mins.append(0.0); maxs.append(0.0)
        else:
            mins.append(float(seg.min())); maxs.append(float(seg.max()))
    data = {"duration": n / sr, "buckets": buckets, "min": mins, "max": maxs}
    cache.write_text(json.dumps(data))
    return data


def fit_tempo(y, sr, anchor=100.0):
    """Least-squares fit of beat times. Beats frame quantisation — this is the
    method validated against Smooth Criminal at 0.2% error."""
    _, b = librosa.beat.beat_track(y=y, sr=sr, hop_length=256, start_bpm=anchor, trim=False)
    bt = librosa.frames_to_time(b, sr=sr, hop_length=256)
    if len(bt) < 8:
        return None, None
    d = np.diff(bt)
    med = np.median(d)
    bt = bt[np.concatenate([[True], np.abs(d - med) < 0.25 * med])]
    slope, _ = np.polyfit(np.arange(len(bt)), bt, 1)
    return 60.0 / slope, bt


def estimate_key(y, sr):
    ch = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512).mean(axis=1)
    best = max(((np.corrcoef(np.roll(p, i), ch)[0, 1], f"{NOTES[i]} {n}")
                for i in range(12) for p, n in ((MAJOR, "major"), (MINOR, "minor"))),
               key=lambda x: x[0])
    return {"key": best[1], "confidence": round(float(best[0]), 3)}


def downbeats(path: Path):
    """beat_this transformer. Per-bar positions, so a fixed grid can't drift.
    Returns None if the model isn't available rather than failing the request."""
    cache = CACHE / f"db_{_key(path)}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        import os, certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        from beat_this.inference import File2Beats
        beats, dbs = File2Beats(device="cpu")(str(to_wav(path)))
        dbs = [float(x) for x in dbs]
        # beat_this emits occasional spurious downbeats (bars as short as 0.08s)
        clean = [dbs[0]] if dbs else []
        for x in dbs[1:]:
            if x - clean[-1] > 1.5:
                clean.append(x)
        out = {"beats": [float(x) for x in beats], "downbeats": clean}
    except Exception as e:
        out = {"beats": [], "downbeats": [], "error": str(e)}
    cache.write_text(json.dumps(out))
    return out


def analyze(path: Path) -> dict:
    cache = CACHE / f"an_{_key(path)}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    w = to_wav(path)
    y, sr = librosa.load(w, sr=22050, mono=True)
    bpm, _ = fit_tempo(y, sr)
    db = downbeats(path)
    bars = db.get("downbeats", [])
    bar_len = float(np.median(np.diff(bars))) if len(bars) > 2 else None
    out = {
        "name": path.name,
        "duration": len(y) / sr,
        "bpm": round(bpm, 2) if bpm else None,
        "bpm_from_downbeats": round(240.0 / bar_len, 2) if bar_len else None,
        "bar_length": round(bar_len, 4) if bar_len else None,
        "key": estimate_key(y, sr),
        "n_downbeats": len(bars),
        "downbeats": bars,
    }
    cache.write_text(json.dumps(out))
    return out
