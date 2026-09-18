"""Offline render — turn the project into an audio file.

Playback in the browser and rendering here must agree, so this deliberately
mirrors the Web Audio graph in app.js:

    source slice -> clip gain -> fades -> track volume -> pan -> sum

The difference is that playback schedules nodes in real time, while this walks
every clip once and sums into one big array. Same maths, different plumbing.
"""
import threading
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa

from . import audio

ROOT = Path(__file__).resolve().parent.parent.parent
# Exports land in mixes/ — that folder IS the "Mixes" category in the sidebar,
# so anything you bounce shows up there immediately. renders/ stays for the
# older research bounces and is not browsable.
OUT = ROOT / "mixes"
OUT.mkdir(exist_ok=True)

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _fade(n: int, fade_in: float, fade_out: float, sr: int) -> np.ndarray:
    """Equal-power-ish linear fades. Even 5ms removes the click you get from
    cutting audio mid-waveform."""
    # Exactly the ramp Web Audio's linearRampToValueAtTime draws, sample by
    # sample, so the fades you hear while mixing are the fades that export.
    # (The preview used to skip fades entirely.)
    env = np.ones(n, dtype=np.float32)
    fi, fo = int(round(fade_in * sr)), int(round(fade_out * sr))
    if fi > 0:
        fi = min(fi, n)
        env[:fi] = np.minimum(env[:fi], np.arange(fi, dtype=np.float32) / fi)
    if fo > 0:
        fo = min(fo, n)
        env[n - fo:] = np.minimum(env[n - fo:], 1.0 - np.arange(fo, dtype=np.float32) / fo)
    return env


def _pan(y: np.ndarray, pan: float) -> np.ndarray:
    """Exactly what the browser's StereoPannerNode does to a stereo signal
    (Web Audio spec, "StereoPannerNode" processing). At pan 0 it is a
    pass-through. The constant-power law this replaced pulled every centred
    track down 3 dB, so exports came out quieter than what you mixed to."""
    if abs(pan) < 1e-6:
        return y
    L, R = y[0], y[1]
    if pan <= 0:
        x = (pan + 1.0) * np.pi / 2               # pan left: fold R into L
        return np.stack([L + R * np.cos(x), R * np.sin(x)])
    x = pan * np.pi / 2                           # pan right: fold L into R
    return np.stack([L * np.cos(x), R + L * np.sin(x)])


def _read_clip(path, into: float, length: float, sr: int):
    """A clip's samples, starting at the SAME whole sample the browser uses.

    Both sides round a clip's position to the nearest sample. Before, the
    export truncated while the browser handed Web Audio a fractional offset —
    up to a sample apart. Inaudible, but it meant "identical" was only true
    when offsets happened to land on whole samples.
    """
    info = sf.info(str(path))
    if info.samplerate != sr:                      # needs resampling; can't be sample-exact
        y, _ = librosa.load(path, sr=sr, mono=False, offset=max(0.0, into), duration=length)
        return y if y.ndim == 2 else np.stack([y, y])
    start = max(0, int(round(into * sr)))
    y, _ = sf.read(str(path), start=start, frames=int(round(length * sr)),
                   always_2d=True, dtype="float32")
    y = y.T
    return y if y.shape[0] == 2 else np.repeat(y[:1], 2, axis=0)


def render_project(project, resolve, sr: int = 44100, normalize: bool = True,
                   progress=None) -> np.ndarray:
    """resolve(source, file) -> Path, injected so this module doesn't need to
    know about the server's folder layout."""
    dur = project.duration
    if dur <= 0:
        raise ValueError("nothing to render — the project is empty")
    n = int(dur * sr) + sr                       # +1s tail for fades/reverb
    mix = np.zeros((2, n), dtype=np.float32)

    tracks = project.audible_tracks()            # applies solo-beats-mute
    total = sum(len(t.clips) for t in tracks) or 1
    done = 0

    for tr in tracks:
        for c in tr.clips:
            if c.length <= 0:
                continue
            # Read the same (possibly warped) file the browser plays, with
            # offset/length measured on it — so export matches preview exactly.
            path, base = audio.clip_audio(resolve(c.source, c.file), c.warp, c.pitch,
                                          c.warp_mode, c.offset, c.length, tr.effects)
            y = _read_clip(path, c.offset - base, c.length, sr)

            m = y.shape[1]
            y = y * _fade(m, c.fade_in, c.fade_out, sr)
            y = y * (c.gain * tr.volume)
            y = _pan(y, tr.pan)

            s = int(round(c.start * sr))
            e = min(n, s + m)
            if s < n and e > s:
                mix[:, s:e] += y[:, : e - s]

            done += 1
            if progress:
                progress(done / total)

    if normalize:
        peak = float(np.max(np.abs(mix)))
        if peak > 1.0:
            mix *= 0.98 / peak                   # only pull down if clipping
    return mix


def start(project, resolve, name: str, fmt: str = "wav") -> str:
    """Kick off a render on a background thread; returns a job id to poll."""
    job = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job] = {"state": "running", "progress": 0.0}

    def run():
        try:
            def prog(p):
                with _lock:
                    _jobs[job]["progress"] = round(p, 3)
            mix = render_project(project, resolve, progress=prog)
            safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip() or "mixr"
            path = OUT / f"{safe}.wav"
            sf.write(path, mix.T, 44100, subtype="PCM_16")
            if fmt == "m4a":
                import subprocess
                m4a = path.with_suffix(".m4a")
                subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "256000",
                                str(path), str(m4a)], check=True, capture_output=True)
                path = m4a
            with _lock:
                _jobs[job] = {"state": "done", "progress": 1.0,
                              "file": path.name, "seconds": mix.shape[1] / 44100}
        except Exception as e:
            with _lock:
                _jobs[job] = {"state": "error", "error": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return job


def status(job: str) -> dict:
    with _lock:
        return _jobs.get(job, {"state": "unknown"})
