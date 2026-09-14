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
    env = np.ones(n, dtype=np.float32)
    fi, fo = int(fade_in * sr), int(fade_out * sr)
    if fi > 0:
        fi = min(fi, n)
        env[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
    if fo > 0:
        fo = min(fo, n)
        env[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
    return env


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
        # constant-power pan: keeps perceived loudness steady across the field
        l_gain = np.sqrt(0.5 * (1.0 - tr.pan))
        r_gain = np.sqrt(0.5 * (1.0 + tr.pan))
        for c in tr.clips:
            if c.length <= 0:
                continue
            path = resolve(c.source, c.file)
            y, _ = librosa.load(path, sr=sr, mono=False,
                                offset=max(0.0, c.offset), duration=c.length)
            if y.ndim == 1:
                y = np.stack([y, y])

            if abs(c.stretch - 1.0) > 1e-6 or abs(c.pitch) > 1e-6:
                y = _warp(y, sr, c.stretch, c.pitch)

            m = y.shape[1]
            y = y * _fade(m, c.fade_in, c.fade_out, sr)
            y = y * (c.gain * tr.volume)
            y[0] *= l_gain
            y[1] *= r_gain

            s = int(c.start * sr)
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


def _warp(y, sr, stretch, semitones):
    """Rubber Band when available (DAW-grade), phase vocoder as fallback."""
    try:
        import pyrubberband as pyrb
        out = y
        if abs(stretch - 1.0) > 1e-6:
            out = np.stack([pyrb.time_stretch(ch, sr, 1.0 / stretch) for ch in out])
        if abs(semitones) > 1e-6:
            out = np.stack([pyrb.pitch_shift(ch, sr, semitones) for ch in out])
        return out.astype(np.float32)
    except Exception:
        out = y
        if abs(stretch - 1.0) > 1e-6:
            out = np.stack([librosa.effects.time_stretch(np.ascontiguousarray(ch),
                                                         rate=1.0 / stretch) for ch in out])
        if abs(semitones) > 1e-6:
            out = np.stack([librosa.effects.pitch_shift(np.ascontiguousarray(ch),
                                                        sr=sr, n_steps=semitones) for ch in out])
        return out.astype(np.float32)


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
