"""Find segment boundaries in a full set when you know HOW MANY segments there are.

Normally segmenting a 9-minute multi-style mix is under-determined. But the
SoundCloud details give us the exact COUNT and ORDER of segments, which turns
this into a constrained problem: find the N-1 strongest structural boundaries
and assign the known labels by position.

Boundary evidence combined here:
  - novelty in beat-synced chroma + MFCC (timbre/harmony change)
  - energy troughs (the dancer's hint: "segments change where the mix drops
    out / changes vibes")
  - tempo discontinuity

Usage: boundaries.py <wav_name> <n_segments> [label1,label2,...]
"""
import sys
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "workdir" / "wav"
SR = 22050
HOP = 512


def find(name, n_seg, labels=None, min_gap=25.0):
    y, sr = librosa.load(WAV / f"{name}.wav", sr=SR, mono=True)
    dur = len(y) / sr

    # --- timbre/harmony novelty -------------------------------------------
    # Frame-to-frame distance in beat-synced feature space. (An earlier version
    # used timelag_filter on a recurrence matrix and blew up on shape; this is
    # simpler and does the same job.)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=13)
    feat = np.vstack([librosa.util.normalize(chroma, axis=0),
                      librosa.util.normalize(mfcc, axis=0)])
    sm = np.convolve(np.ones(1), np.ones(1))          # (no-op, keeps shape logic clear)
    W = 43                                            # ~1s either side
    fs = np.apply_along_axis(
        lambda r: np.convolve(r, np.ones(W) / W, mode="same"), 1, feat)
    d = np.linalg.norm(np.diff(fs, axis=1), axis=0)
    nov = np.pad(d, (1, 0), mode="edge")
    nov = nov / (nov.max() + 1e-9)

    # --- energy trough evidence -------------------------------------------
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_s = np.convolve(rms, np.ones(40) / 40, mode="same")
    trough = 1.0 - rms_s / (rms_s.max() + 1e-9)

    # --- tempo discontinuity ----------------------------------------------
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tg = librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=HOP,
                               aggregate=None, std_bpm=4.0)
    tg = np.pad(tg, (0, max(0, len(rms) - len(tg))), mode="edge")[:len(rms)]
    dtempo = np.abs(np.diff(np.pad(tg, (1, 0), mode="edge")))
    dtempo = dtempo / (dtempo.max() + 1e-9)

    L = min(len(nov), len(trough), len(dtempo))
    score = 0.5 * nov[:L] + 0.32 * trough[:L] + 0.18 * dtempo[:L]
    score = np.convolve(score, np.ones(9) / 9, mode="same")
    times = librosa.frames_to_time(np.arange(L), sr=sr, hop_length=HOP)

    # --- pick N-1 peaks, enforcing a minimum spacing ----------------------
    order = np.argsort(score)[::-1]
    picked = []
    for i in order:
        t = times[i]
        if t < min_gap or t > dur - min_gap:
            continue
        if all(abs(t - p) > min_gap for p in picked):
            picked.append(t)
        if len(picked) == n_seg - 1:
            break
    picked.sort()

    edges = [0.0] + picked + [dur]
    print(f"=== {name}   {dur/60:.0f}:{dur%60:04.1f}   {n_seg} segments\n")
    out = []
    for i in range(len(edges) - 1):
        s, e = edges[i], edges[i + 1]
        seg = y[int(s * sr):int(e * sr)]
        try:
            _, b = librosa.beat.beat_track(y=seg, sr=sr, hop_length=256, start_bpm=95, trim=False)
            bt = librosa.frames_to_time(b, sr=sr, hop_length=256)
            d = np.diff(bt); med = np.median(d)
            bt = bt[np.concatenate([[True], np.abs(d - med) < 0.25 * med])]
            slope, _ = np.polyfit(np.arange(len(bt)), bt, 1)
            bpm = 60 / slope
            while bpm > 130: bpm /= 2
            while bpm < 70: bpm *= 2
        except Exception:
            bpm = float("nan")
        r = float(np.sqrt((seg ** 2).mean()))
        lab = labels[i] if labels and i < len(labels) else f"seg{i+1}"
        print(f"  {int(s//60)}:{s%60:04.1f} - {int(e//60)}:{e%60:04.1f}  "
              f"({e-s:5.1f}s)  {bpm:6.2f} BPM  rms {r:.3f}   {lab}")
        out.append({"start": round(s, 1), "end": round(e, 1), "bpm": round(bpm, 2), "label": lab})
    return out


if __name__ == "__main__":
    name, n = sys.argv[1], int(sys.argv[2])
    labels = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    find(name, n, labels)
