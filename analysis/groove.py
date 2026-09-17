"""Groove fingerprinting from Demucs drum stems.

For each segment's drum stem:
  - beat-tracks the original mix for a stable grid
  - detects drum onsets in three bands:
      low  (<160 Hz)   ~ dhol dagga / kick / 808
      mid  (160-2000)  ~ snare body, dhol tilli fundamental
      high (>2000)     ~ tilli attack, hats, claps
  - normalizes each onset to its position within the beat (0..1)
  - builds a per-band onset-position histogram = the groove fingerprint
  - estimates swing: mass near 0.5 (straight 8ths) vs 0.62-0.72 (swung/triplet)

Writes research/reports/groove_<name>.json and .png.
"""
import json
import sys
from pathlib import Path

import numpy as np
import librosa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
WAV_DIR = ROOT / "workdir" / "wav"
STEM_DIR = ROOT / "workdir" / "stems" / "htdemucs"
OUT_DIR = ROOT / "research" / "reports"

SR = 22050
HOP = 256  # finer grid for onset timing
BANDS = {"low": (20, 160), "mid": (160, 2000), "high": (2000, 9000)}
NBINS = 24  # histogram bins per beat


def band_onsets(y, sr, fmin, fmax):
    S = np.abs(librosa.stft(y, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr)
    mask = (freqs >= fmin) & (freqs < fmax)
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S[mask] ** 2), hop_length=HOP)
    frames = librosa.onset.onset_detect(onset_envelope=env, hop_length=HOP,
                                        backtrack=False, delta=0.35)
    times = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
    strengths = env[frames] if len(frames) else np.array([])
    return times, strengths


def analyze(name: str):
    mix_path = WAV_DIR / f"{name}.wav"
    drum_path = STEM_DIR / name / "drums.wav"
    print(f"--- {name}")
    y_mix, sr = librosa.load(mix_path, sr=SR, mono=True)
    y_dr, _ = librosa.load(drum_path, sr=SR, mono=True)

    # beat grid from the full mix (more stable than drums alone)
    tempo, beats = librosa.beat.beat_track(y=y_mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    if len(bt) < 8:
        print("    not enough beats, skipping")
        return

    result = {"file": name, "tempo_grid_bpm": round(float(np.atleast_1d(tempo)[0]), 1),
              "n_beats": len(bt), "bands": {}}
    fig, axes = plt.subplots(len(BANDS), 1, figsize=(10, 7), sharex=True)

    for ax, (band, (lo, hi)) in zip(axes, BANDS.items()):
        times, strengths = band_onsets(y_dr, sr, lo, hi)
        # position of each onset within its beat, weighted by onset strength
        pos, wts = [], []
        for t, w in zip(times, strengths):
            i = np.searchsorted(bt, t) - 1
            if 0 <= i < len(bt) - 1:
                pos.append((t - bt[i]) / (bt[i + 1] - bt[i]))
                wts.append(w)
        pos, wts = np.array(pos), np.array(wts)
        hist, edges = np.histogram(pos, bins=NBINS, range=(0, 1), weights=wts)
        hist = hist / (hist.sum() + 1e-9)

        # swing metric: energy near straight 8th (0.42-0.58) vs swung (0.58-0.75)
        straight = float(hist[(edges[:-1] >= 0.42) & (edges[:-1] < 0.58)].sum())
        swung = float(hist[(edges[:-1] >= 0.58) & (edges[:-1] < 0.75)].sum())
        density = len(pos) / (bt[-1] - bt[0])  # onsets per second in this band

        result["bands"][band] = {
            "onsets_per_sec": round(float(density), 2),
            "histogram": [round(float(h), 4) for h in hist],
            "straight_8th_mass": round(straight, 3),
            "swung_mass": round(swung, 3),
            "swing_ratio": round(swung / (straight + 1e-9), 2),
        }
        ax.bar(edges[:-1], hist, width=1 / NBINS, align="edge", color="#36c")
        ax.axvline(0.5, color="r", ls="--", lw=0.8, alpha=0.6)
        ax.axvline(2 / 3, color="g", ls="--", lw=0.8, alpha=0.6)
        ax.set_ylabel(f"{band}\n({lo}-{hi}Hz)")
    axes[-1].set_xlabel("position within beat (red=straight 8th, green=triplet)")
    fig.suptitle(f"{name} — groove fingerprint @ {result['tempo_grid_bpm']} BPM grid")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"groove_{name}.png", dpi=110)
    plt.close(fig)

    (OUT_DIR / f"groove_{name}.json").write_text(json.dumps(result, indent=2))
    for b, d in result["bands"].items():
        print(f"    {b:>4}: {d['onsets_per_sec']}/s  swing_ratio {d['swing_ratio']}")


if __name__ == "__main__":
    names = sys.argv[1:] or [p.name for p in sorted(STEM_DIR.iterdir()) if p.is_dir()]
    for n in names:
        analyze(n)
