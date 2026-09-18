"""How audio gets moved in time — the four warp modes.

All four follow the same warp map (app/core/warp.py); they differ in what
happens to the SOUND between pins. Measured on Mmhmm's stems (2026-09-18):

  crisp    Rubber Band R2, --crisp 6. Hits land within ~4 ms of their pins.
           Good general default — but it doubled an 808's attack time.
  tones    Rubber Band R2 default + formant preservation. Smoothest on
           sustained sound: kept the 808's attack sharp (3.7 ms) and suits
           vocals. Pulls hits ~16 ms early, so not for drums.
  slice    Ableton-style Beats: cut at every transient and play each hit at
           ORIGINAL speed, just moved to its new time. Hits are never
           stretched, so a kick keeps its punch. Use on drums.
  repitch  Resampling, like speeding up or slowing down a record: tempo and
           pitch move together. No stretch artifacts at all.

Each takes a (channels, samples) array covering a stretch of the source, a
warp map in that stretch's own time, and the output duration.
"""
from __future__ import annotations

import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf

from . import warp

MODES = ("crisp", "tones", "slice", "repitch")


def rubberband(y, sr, pins, out_dur, pitch=0.0, mode="crisp"):
    """Rubber Band with a time map (crisp or tones)."""
    with tempfile.TemporaryDirectory() as d:
        src, dst, mp = Path(d) / "in.wav", Path(d) / "out.wav", Path(d) / "map.txt"
        sf.write(src, y.T, sr)
        cmd = ["rubberband", "-q", "-p", f"{pitch:.3f}"]
        cmd += ["-c", "6"] if mode == "crisp" else ["-F"]
        if pins:
            frames, _ = warp.rubberband_map(pins, y.shape[1] / sr, sr)
            mp.write_text("".join(f"{a} {b}\n" for a, b in frames))
            cmd += ["-D", f"{out_dur:.6f}", "-M", str(mp)]
        subprocess.run(cmd + [str(src), str(dst)], check=True, capture_output=True)
        out, _ = sf.read(dst, always_2d=True)
    return _fit(out.T.astype(np.float32), int(round(out_dur * sr)))


def slice_mode(y, sr, pins, out_dur, min_gap=0.03, fade=0.004):
    """Cut at transients, play every slice unstretched at its new position.

    Slowing down leaves a short silence after each hit's natural tail;
    speeding up cuts a slice off before the next one starts. Either way the
    cut gets a 4 ms fade so it never clicks. Onsets are backtracked to the
    quiet just before each attack, so a slice never starts mid-hit.
    """
    n = y.shape[1]
    # (cut, anchor): cut in the quiet before a hit, anchor on the hit itself
    marks = [(0, 0)]
    for cut, hit in cut_points(y, sr):
        if cut - marks[-1][0] >= min_gap * sr:
            marks.append((cut, hit))

    # Where each slice STARTS in the output. The attack must land exactly on
    # map(attack); the quiet lead-in before it just comes along unstretched.
    # Placing by the cut instead would carry the unstretched lead-in's length
    # into the attack's position — up to 25 ms × (stretch - 1) of error.
    starts = [int(round(warp.src_to_dst(pins, hit / sr) * sr)) - (hit - cut)
              for cut, hit in marks]
    n_out = int(round(out_dur * sr))
    starts.append(n_out)
    ends = [c for c, _ in marks[1:]] + [n]

    out = np.zeros((y.shape[0], n_out), dtype=np.float32)
    f = int(fade * sr)
    for (a, _), b, s, s_next in zip(marks, ends, starts, starts[1:]):
        s = max(0, s)
        length = min(b - a, s_next - s, n_out - s)
        if length <= 0:
            continue
        piece = y[:, a:a + length].copy()
        k = min(f, length)
        piece[:, length - k:] *= np.linspace(1.0, 0.0, k, dtype=np.float32)
        out[:, s:s + length] += piece
    return out


def cut_points(y, sr, search=0.025):
    """(cut, attack) sample pairs: where to cut before each hit, and the hit.

    Onset detection works on ~3 ms frames and its backtracking can land a
    couple of ms AFTER an attack has begun. Cutting there leaves the first
    sliver of the hit in the previous slice, which then plays early — a flam.
    So each detected onset is walked back to the quietest point of the actual
    waveform (1 ms RMS) in the 25 ms before it.
    """
    import librosa
    mono = y.mean(axis=0)
    on = librosa.onset.onset_detect(y=mono, sr=sr, hop_length=128, units="samples")
    w = max(1, int(0.001 * sr))
    env = np.sqrt(np.convolve(mono ** 2, np.ones(w) / w, mode="same"))
    marks = []
    for o in on:
        lo = max(0, o - int(search * sr))
        seg = env[lo:o + 1]
        if len(seg):
            cut = lo + int(np.argmin(seg))
            # the attack: first sample after the cut that reaches 20% of the
            # hit's peak — steadier than the onset frame, and sample-accurate
            pk = env[cut:o + int(0.02 * sr)]
            hit = cut + int(np.argmax(pk >= 0.2 * pk.max())) if len(pk) else o
            marks.append((cut, hit))
    marks.sort()
    return [m for i, m in enumerate(marks) if i == 0 or m[0] != marks[i - 1][0]]


def repitch_mode(y, sr, pins, out_dur, pad=4096):
    """Resample each segment between pins to its new length.

    Every segment is resampled with a little context from its neighbours and
    then cropped, so the filter's edge effects land outside what's kept.
    """
    from scipy.signal import resample_poly
    n, n_out = y.shape[1], int(round(out_dur * sr))
    dur = n / sr
    cuts = [0.0] + [a for a, _ in pins if 0 < a < dur] + [dur]
    out = np.zeros((y.shape[0], n_out), dtype=np.float32)
    for a, b in zip(cuts, cuts[1:]):
        ia, ib = int(round(a * sr)), int(round(b * sr))
        oa = int(round(warp.src_to_dst(pins, a) * sr))
        ob = min(n_out, int(round(warp.src_to_dst(pins, b) * sr)))
        if ib <= ia or ob <= oa:
            continue
        lo, hi = max(0, ia - pad), min(n, ib + pad)
        ratio = (ob - oa) / (ib - ia)
        fr = Fraction(ratio).limit_denominator(4000)
        r = resample_poly(y[:, lo:hi], fr.numerator, fr.denominator, axis=1)
        start = int(round((ia - lo) * fr.numerator / fr.denominator))
        piece = _fit(r[:, start:], ob - oa)
        out[:, oa:ob] += piece
    return out


def render(y, sr, pins, out_dur, pitch=0.0, mode="crisp"):
    """Dispatch to a mode. Slice and repitch don't shift pitch on their own,
    so a transpose on top of them is one extra pitch-only Rubber Band pass."""
    if mode not in MODES:
        raise ValueError(f"unknown warp mode {mode!r}")
    if mode in ("crisp", "tones"):
        return rubberband(y, sr, pins, out_dur, pitch, mode)
    out = slice_mode(y, sr, pins, out_dur) if mode == "slice" else repitch_mode(y, sr, pins, out_dur)
    if abs(pitch) > 1e-6:
        out = rubberband(out, sr, [], out.shape[1] / sr, pitch, "tones")
    return out


def _fit(y, n):
    """Trim or zero-pad to exactly n samples — output length must be exact,
    or every later clip position drifts."""
    if y.shape[1] >= n:
        return y[:, :n]
    return np.pad(y, ((0, 0), (0, n - y.shape[1])))
