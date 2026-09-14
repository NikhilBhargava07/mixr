"""First-pass musical analysis for DDN mix study.

For each WAV in workdir/wav, extracts:
  - global + time-varying tempo
  - beat grid
  - key estimate (global and per-section, Krumhansl-Schmuckler)
  - RMS energy curve, onset density, spectral brightness
  - percussive vs harmonic energy balance (dhol/drum presence proxy)
  - structural section boundaries (novelty-based)

Writes reports/<name>.json and reports/<name>.png.
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
OUT_DIR = ROOT / "reports"
OUT_DIR.mkdir(exist_ok=True)

SR = 22050
HOP = 512

# Krumhansl-Schmuckler key profiles
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def estimate_key(chroma_mean):
    scores = []
    for i in range(12):
        maj = np.corrcoef(np.roll(MAJOR, i), chroma_mean)[0, 1]
        mnr = np.corrcoef(np.roll(MINOR, i), chroma_mean)[0, 1]
        scores.append((maj, f"{NOTES[i]} major"))
        scores.append((mnr, f"{NOTES[i]} minor"))
    scores.sort(reverse=True)
    return {"key": scores[0][1], "confidence": round(float(scores[0][0]), 3),
            "runner_up": scores[1][1]}


def analyze(path: Path):
    name = path.stem
    print(f"--- {name}")
    y, sr = librosa.load(path, sr=SR, mono=True)
    dur = len(y) / sr

    # tempo: global + dynamic
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo_global = float(librosa.feature.tempo(onset_envelope=onset_env, sr=sr, hop_length=HOP)[0])
    tempo_dyn = librosa.feature.tempo(onset_envelope=onset_env, sr=sr, hop_length=HOP,
                                      aggregate=None, std_bpm=2.0)
    _, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP)
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)

    # energy / brightness / onset density (2s windows)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP)[0]
    times = librosa.times_like(rms, sr=sr, hop_length=HOP)

    # percussive vs harmonic balance
    y_h, y_p = librosa.effects.hpss(y)
    rms_h = librosa.feature.rms(y=y_h, hop_length=HOP)[0]
    rms_p = librosa.feature.rms(y=y_p, hop_length=HOP)[0]

    # structure: novelty-based boundaries on chroma+mfcc
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=13)
    feats = np.vstack([librosa.util.normalize(chroma, axis=0),
                       librosa.util.normalize(mfcc, axis=0)])
    # sync to beats for cleaner segmentation
    if len(beats) > 8:
        feats_sync = librosa.util.sync(feats, beats)
        k = max(2, min(int(dur // 8), 24))
        bounds = librosa.segment.agglomerative(feats_sync, k)
        bound_times = beat_times[np.minimum(bounds, len(beat_times) - 1)]
    else:
        bound_times = np.array([0.0])

    # per-section stats
    sections = []
    edges = list(bound_times) + [dur]
    for i in range(len(edges) - 1):
        s, e = float(edges[i]), float(edges[i + 1])
        if e - s < 1.0:
            continue
        sl = slice(*librosa.time_to_frames([s, e], sr=sr, hop_length=HOP))
        sec_chroma = chroma[:, sl].mean(axis=1) if chroma[:, sl].size else chroma.mean(axis=1)
        sec_tempo = tempo_dyn[sl]
        sections.append({
            "start": round(s, 2), "end": round(e, 2),
            "tempo_median": round(float(np.median(sec_tempo)), 1) if sec_tempo.size else None,
            "key": estimate_key(sec_chroma),
            "rms_mean": round(float(rms[sl].mean()), 4) if rms[sl].size else None,
            "perc_ratio": round(float(rms_p[sl].mean() / (rms_h[sl].mean() + rms_p[sl].mean() + 1e-9)), 3),
            "brightness_hz": round(float(centroid[sl].mean()), 0) if centroid[sl].size else None,
        })

    result = {
        "file": name,
        "duration_sec": round(dur, 2),
        "tempo_global_bpm": round(tempo_global, 1),
        "tempo_dynamic_median": round(float(np.median(tempo_dyn)), 1),
        "tempo_dynamic_range": [round(float(np.percentile(tempo_dyn, 5)), 1),
                                round(float(np.percentile(tempo_dyn, 95)), 1)],
        "n_beats": int(len(beat_times)),
        "key_global": estimate_key(chroma.mean(axis=1)),
        "perc_ratio_global": round(float(rms_p.mean() / (rms_h.mean() + rms_p.mean() + 1e-9)), 3),
        "sections": sections,
    }
    (OUT_DIR / f"{name}.json").write_text(json.dumps(result, indent=2))

    # plot: waveform+rms with boundaries, tempo curve
    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(np.linspace(0, dur, len(y))[::50], y[::50], lw=0.3, color="#888")
    axes[0].set_ylabel("waveform")
    axes[1].plot(times, rms, color="#d33", lw=1, label="RMS energy")
    axes[1].plot(times, rms_p, color="#36c", lw=0.8, label="percussive")
    axes[1].plot(times, rms_h, color="#3a3", lw=0.8, label="harmonic")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].set_ylabel("energy")
    t_tempo = librosa.times_like(tempo_dyn, sr=sr, hop_length=HOP)
    axes[2].plot(t_tempo, tempo_dyn, color="#93c", lw=1)
    axes[2].set_ylabel("tempo (BPM)")
    axes[2].set_xlabel("time (s)")
    for ax in axes:
        for b in bound_times:
            ax.axvline(b, color="k", alpha=0.25, lw=0.7, ls="--")
    fig.suptitle(name)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{name}.png", dpi=110)
    plt.close(fig)
    print(f"    {dur:.0f}s | tempo ~{result['tempo_dynamic_median']} BPM | "
          f"key {result['key_global']['key']} | {len(sections)} sections")


if __name__ == "__main__":
    targets = sys.argv[1:] or sorted(WAV_DIR.glob("*.wav"))
    for p in targets:
        analyze(Path(p))
