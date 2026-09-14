"""Meter analysis: does a segment's groove subdivide in 2s (straight 16ths)
or 3s (compound/triplet, i.e. 6/8-family like jhummar & kuthu)?

Method: beat-track the mix, subdivide each beat into 12 positions, histogram
strength-weighted drum onsets at those positions. Duple grooves concentrate
mass at {0,3,6,9}/12; compound grooves at {0,4,8}/12. Reports a per-band
verdict plus the full 12-bin cycle pattern (the rhythm 'stencil' of the style).
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
OUT_DIR = ROOT / "reports"

SR = 22050
HOP = 256
BANDS = {"low": (20, 160), "mid": (160, 2000), "high": (2000, 9000)}


def band_onsets(y, sr, fmin, fmax):
    S = np.abs(librosa.stft(y, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr)
    mask = (freqs >= fmin) & (freqs < fmax)
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S[mask] ** 2), hop_length=HOP)
    frames = librosa.onset.onset_detect(onset_envelope=env, hop_length=HOP,
                                        backtrack=False, delta=0.35)
    return librosa.frames_to_time(frames, sr=sr, hop_length=HOP), env[frames]


def twelve_bin(times, strengths, beat_times):
    """Strength-weighted histogram of onset positions, 12 bins per beat."""
    hist = np.zeros(12)
    for t, w in zip(times, strengths):
        i = np.searchsorted(beat_times, t) - 1
        if 0 <= i < len(beat_times) - 1:
            frac = (t - beat_times[i]) / (beat_times[i + 1] - beat_times[i])
            hist[int(frac * 12) % 12] += w
    return hist / (hist.sum() + 1e-9)


def verdict(hist):
    # exclude bin 0 (downbeat, shared by both interpretations)
    duple = hist[[3, 6, 9]].sum() / 3      # 16th-note positions
    triple = hist[[4, 8]].sum() / 2        # triplet positions
    ratio = triple / (duple + 1e-9)
    label = "compound(3s)" if ratio > 1.3 else ("straight(2s)" if ratio < 0.77 else "ambiguous")
    return {"duple_mass": round(float(duple), 4), "triple_mass": round(float(triple), 4),
            "triple_over_duple": round(float(ratio), 2), "verdict": label}


def analyze(name: str):
    print(f"--- {name}")
    y_mix, sr = librosa.load(WAV_DIR / f"{name}.wav", sr=SR, mono=True)
    y_dr, _ = librosa.load(STEM_DIR / name / "drums.wav", sr=SR, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y_mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    tempo = float(np.atleast_1d(tempo)[0])

    result = {"file": name, "grid_bpm": round(tempo, 1), "bands": {}}
    fig, axes = plt.subplots(len(BANDS), 1, figsize=(9, 7), sharex=True)
    for ax, (band, (lo, hi)) in zip(axes, BANDS.items()):
        times, strengths = band_onsets(y_dr, sr, lo, hi)
        hist = twelve_bin(times, strengths, bt)
        v = verdict(hist)
        result["bands"][band] = {**v, "cycle_12bin": [round(float(h), 4) for h in hist]}
        colors = ["#c33" if i in (3, 6, 9) else "#3a3" if i in (4, 8) else "#36c" if i == 0 else "#aaa"
                  for i in range(12)]
        ax.bar(range(12), hist, color=colors)
        ax.set_ylabel(f"{band}\n{v['verdict']}")
        ax.set_xticks(range(12))
    axes[-1].set_xlabel("12 positions per beat (blue=downbeat, red=16th/duple, green=triplet/compound)")
    fig.suptitle(f"{name} — subdivision analysis @ {result['grid_bpm']} BPM grid")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"meter_{name}.png", dpi=110)
    plt.close(fig)

    (OUT_DIR / f"meter_{name}.json").write_text(json.dumps(result, indent=2))
    for b, d in result["bands"].items():
        print(f"    {b:>4}: {d['verdict']:<13} (3:2 mass ratio {d['triple_over_duple']})")


if __name__ == "__main__":
    names = sys.argv[1:] or ["VC_Surma_GB_V1E2_2026", "Surma_South_2026_v2", "Khunde",
                             "SURMA_CLASSICAL_real_95_Pitch_0.00_-_Tempo_95_", "Hip_hop_1_"]
    for n in names:
        analyze(n)
