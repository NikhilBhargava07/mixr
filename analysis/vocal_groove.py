"""How do vocals sit on the groove? (e.g. English vocals on a jhummar grid)

From a segment's Demucs vocal stem:
  - find vocal-active regions (RMS gate)
  - detect syllable onsets in the vocal stem
  - histogram their positions within the beat (12 bins, as in meter.py)
  - compare against the drum stem's preferred positions:
      * cosine similarity of vocal vs drum position histograms
      * % of vocal onsets landing within +-1 bin of a drum-preferred position
  - report vocal activity coverage and onset rate (phrasing density)

High similarity = vocals locked to the groove's subdivision (chopped/aligned);
low similarity with high activity = vocals floating across the grid (rubato/legato).
"""
import json
import sys
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV_DIR = ROOT / "workdir" / "wav"
STEM_DIR = ROOT / "workdir" / "stems" / "htdemucs"
OUT_DIR = ROOT / "reports"

SR = 22050
HOP = 256


def onsets(y, sr, delta=0.3):
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    frames = librosa.onset.onset_detect(onset_envelope=env, hop_length=HOP,
                                        backtrack=False, delta=delta)
    return librosa.frames_to_time(frames, sr=sr, hop_length=HOP), env[frames]


def twelve_bin(times, strengths, beat_times):
    hist = np.zeros(12)
    for t, w in zip(times, strengths):
        i = np.searchsorted(beat_times, t) - 1
        if 0 <= i < len(beat_times) - 1:
            frac = (t - beat_times[i]) / (beat_times[i + 1] - beat_times[i])
            hist[int(frac * 12) % 12] += w
    return hist / (hist.sum() + 1e-9)


def analyze(name: str):
    print(f"--- {name}")
    y_mix, sr = librosa.load(WAV_DIR / f"{name}.wav", sr=SR, mono=True)
    y_vox, _ = librosa.load(STEM_DIR / name / "vocals.wav", sr=SR, mono=True)
    y_dr, _ = librosa.load(STEM_DIR / name / "drums.wav", sr=SR, mono=True)

    _, beats = librosa.beat.beat_track(y=y_mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)

    # vocal activity coverage
    rms = librosa.feature.rms(y=y_vox, hop_length=HOP)[0]
    thresh = max(0.02, np.percentile(rms, 60) * 0.5)
    active = rms > thresh
    coverage = float(active.mean())

    vt, vs = onsets(y_vox, sr)
    dt, ds = onsets(y_dr, sr)
    # keep vocal onsets only in active regions
    act_times = librosa.times_like(rms, sr=sr, hop_length=HOP)
    keep = [i for i, t in enumerate(vt) if active[min(np.searchsorted(act_times, t), len(active) - 1)]]
    vt, vs = vt[keep], vs[keep]

    vh = twelve_bin(vt, vs, bt)
    dh = twelve_bin(dt, ds, bt)
    cos = float(np.dot(vh, dh) / (np.linalg.norm(vh) * np.linalg.norm(dh) + 1e-9))

    # drum-preferred bins = top 4 bins; how many vocal onsets land within +-1 bin
    pref = set(np.argsort(dh)[-4:])
    pref_wide = {(b + d) % 12 for b in pref for d in (-1, 0, 1)}
    on_grid = 0
    for t in vt:
        i = np.searchsorted(bt, t) - 1
        if 0 <= i < len(bt) - 1:
            frac = (t - bt[i]) / (bt[i + 1] - bt[i])
            if int(frac * 12) % 12 in pref_wide:
                on_grid += 1
    lock = on_grid / (len(vt) + 1e-9)

    dur_active = coverage * len(y_vox) / sr
    result = {
        "file": name,
        "vocal_coverage": round(coverage, 3),
        "vocal_onsets_per_active_sec": round(float(len(vt) / (dur_active + 1e-9)), 2),
        "vocal_hist_12bin": [round(float(h), 4) for h in vh],
        "drum_hist_12bin": [round(float(h), 4) for h in dh],
        "vocal_drum_cosine": round(cos, 3),
        "vocal_lock_to_drum_grid": round(float(lock), 3),
    }
    (OUT_DIR / f"vocal_{name}.json").write_text(json.dumps(result, indent=2))
    print(f"    coverage {coverage:.0%} | {result['vocal_onsets_per_active_sec']} syll/s | "
          f"cosine {cos:.2f} | grid-lock {lock:.0%}")


if __name__ == "__main__":
    names = sys.argv[1:] or ["VC_Surma_GB_V1E2_2026", "Hip_hop_1_", "Khunde",
                             "Surma_South_2026_v2",
                             "SURMA_CLASSICAL_real_95_Pitch_0.00_-_Tempo_95_"]
    for n in names:
        analyze(n)
