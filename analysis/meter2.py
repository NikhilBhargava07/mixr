"""Robust subdivision analysis (replaces meter.py's fragile version).

Problems with v1, found 2026-08-02:
  - verdict flipped from "pure straight" to "compound" on a 4-second window shift
  - ratios came out as 0.00 or 1e8 because the epsilon was absolute (1e-9),
    so a near-empty bin produced a meaningless explosion
  - a single beat-grid hypothesis was assumed correct; if librosa locks onto a
    different metric level, duple and triple bins swap meaning

Fixes here:
  1. Regularized ratio: eps is a share of total histogram mass, not 1e-9, so
     ratios stay in a sane range and sparse data reads as "ambiguous".
  2. Minimum onset count per band; below it we report insufficient_data.
  3. Grid hypothesis search: try the detected beat period and its x0.5 / x2
     variants, keep whichever yields the most CONCENTRATED histogram
     (low normalized entropy) - a correct grid makes onsets pile into few bins.
  4. Report a confidence (concentration) alongside every verdict, so weak
     readings can be discarded downstream instead of silently believed.
"""
import json
import sys
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "workdir" / "wav"
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
OUT = ROOT / "reports"

SR = 22050
HOP = 256
BANDS = {"low": (20, 160), "mid": (160, 2000), "high": (2000, 9000)}
NBINS = 12
MIN_ONSETS = 25          # below this, no verdict
CONF_FLOOR = 0.15        # below this concentration, no verdict


def band_onsets(y, sr, lo, hi):
    S = np.abs(librosa.stft(y, hop_length=HOP))
    fr = librosa.fft_frequencies(sr=sr)
    mask = (fr >= lo) & (fr < hi)
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S[mask] ** 2), hop_length=HOP)
    f = librosa.onset.onset_detect(onset_envelope=env, hop_length=HOP,
                                   backtrack=False, delta=0.35)
    return librosa.frames_to_time(f, sr=sr, hop_length=HOP), env[f]


def hist_for_period(times, strengths, t0, period):
    """Histogram of onset phase within a cycle of the given period."""
    h = np.zeros(NBINS)
    for t, w in zip(times, strengths):
        phase = ((t - t0) / period) % 1.0
        h[int(phase * NBINS) % NBINS] += w
    return h / (h.sum() + 1e-12)


def concentration(h):
    """1 - normalized entropy. 0 = uniform (no rhythmic structure), 1 = one bin."""
    p = h[h > 0]
    if p.size == 0:
        return 0.0
    ent = -(p * np.log(p)).sum() / np.log(NBINS)
    return float(1.0 - ent)


def verdict_for(h):
    """Compare triplet positions (4,8) vs 16th positions (3,6,9), regularized."""
    eps = 1.0 / NBINS * 0.5     # half a bin's worth of uniform mass
    duple = h[[3, 6, 9]].mean()
    triple = h[[4, 8]].mean()
    ratio = float((triple + eps) / (duple + eps))
    if ratio > 1.25:
        v = "compound"
    elif ratio < 0.8:
        v = "straight"
    else:
        v = "ambiguous"
    return v, round(ratio, 2), round(float(duple), 4), round(float(triple), 4)


def analyze(name, start=None, end=None, label=""):
    kw = {}
    if start is not None:
        kw = {"offset": start, "duration": end - start}
    mix, sr = librosa.load(WAV / f"{name}.wav", sr=SR, mono=True, **kw)
    drums, _ = librosa.load(STEMS / name / "drums.wav", sr=SR, mono=True, **kw)

    tempo, beats = librosa.beat.beat_track(y=mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    if len(bt) < 6:
        return {"label": label, "error": "not enough beats"}
    base_period = float(np.median(np.diff(bt)))
    t0 = float(bt[0])

    res = {"label": label, "detected_bpm": round(60.0 / base_period, 1), "bands": {}}
    for band, (lo, hi) in BANDS.items():
        times, strengths = band_onsets(drums, sr, lo, hi)
        if len(times) < MIN_ONSETS:
            res["bands"][band] = {"verdict": "insufficient_data", "n_onsets": int(len(times))}
            continue
        # grid hypothesis search
        best = None
        for mult in (0.5, 1.0, 2.0):
            h = hist_for_period(times, strengths, t0, base_period * mult)
            c = concentration(h)
            if best is None or c > best[0]:
                best = (c, mult, h)
        conf, mult, h = best
        v, ratio, duple, triple = verdict_for(h)
        if conf < CONF_FLOOR:
            v = "no_clear_grid"
        res["bands"][band] = {
            "verdict": v, "triple_over_duple": ratio, "confidence": round(conf, 3),
            "grid_mult": mult, "n_onsets": int(len(times)),
            "onsets_per_sec": round(len(times) / (len(mix) / sr), 2),
            "duple_mass": duple, "triple_mass": triple,
            "histogram": [round(float(x), 4) for x in h],
        }
    return res


def fmt(r):
    if "error" in r:
        return f"{r['label']:<26} ERROR {r['error']}"
    parts = []
    for b in ("low", "mid", "high"):
        d = r["bands"][b]
        if d["verdict"] in ("insufficient_data",):
            parts.append(f"{b} n/a({d['n_onsets']})")
        else:
            parts.append(f"{b} {d['verdict']:<13}r={d['triple_over_duple']:.2f} c={d['confidence']:.2f}")
    return f"{r['label']:<26} {r['detected_bpm']:6.1f}bpm | " + " | ".join(parts)


if __name__ == "__main__":
    if sys.argv[1] == "--map":
        name, mapfile = sys.argv[2], sys.argv[3]
        segs = json.loads(Path(mapfile).read_text())
        out = []
        print(f"===== {name}")
        for s in segs:
            r = analyze(name, s["start"], s["end"], s["label"])
            out.append(r)
            print(fmt(r))
        (OUT / f"meter2_{name}.json").write_text(json.dumps(out, indent=2))
    else:
        for n in sys.argv[1:]:
            print(fmt(analyze(n, label=n)))
