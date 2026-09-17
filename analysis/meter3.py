"""Subdivision analysis v3 — continuous-envelope method.

History:
  v1 (meter.py):  fixed onset threshold + single grid  -> verdicts flipped on a
                  4-second window shift; ratios of 0.00 and 1e8.
  v2 (meter2.py): regularized ratio + grid search + confidence -> honest, but
                  still threw away most data because DISCRETE onset detection
                  with a fixed delta found 1 onset in 18s of hip hop. The
                  onset-strength envelope's dynamic range varies per segment,
                  so any fixed delta is effectively a random threshold.
  v3 (this):      no thresholding at all. Every frame of the continuous
                  onset-strength envelope contributes its value to the phase
                  histogram. Uses all the evidence, no tunable that can silently
                  break a segment.

Verdict = do drum accents fall on triplet positions (compound/6-8 feel) or
16th positions (straight)? Reported with a concentration confidence; grids that
don't produce a peaked histogram get no verdict.
"""
import json
import sys
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "workdir" / "wav"
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
OUT = ROOT / "research" / "reports"

SR = 22050
HOP = 256
BANDS = {"low": (20, 160), "mid": (160, 2000), "high": (2000, 9000)}
NBINS = 12
CONF_FLOOR = 0.02   # concentration above uniform; continuous envelopes are
                    # inherently smoother than onset spikes, so this is low


def band_envelope(y, sr, lo, hi):
    """Continuous onset-strength envelope restricted to a frequency band."""
    S = np.abs(librosa.stft(y, hop_length=HOP))
    fr = librosa.fft_frequencies(sr=sr)
    mask = (fr >= lo) & (fr < hi)
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S[mask] ** 2, ref=np.max),
                                       hop_length=HOP)
    return env / (env.max() + 1e-12)


def phase_hist(env, times, t0, period):
    """Accumulate envelope energy by phase within the cycle. No thresholds."""
    phase = (((times - t0) / period) % 1.0 * NBINS).astype(int) % NBINS
    h = np.bincount(phase, weights=env, minlength=NBINS).astype(float)
    return h / (h.sum() + 1e-12)


def concentration(h):
    p = h[h > 0]
    if p.size == 0:
        return 0.0
    ent = -(p * np.log(p)).sum() / np.log(NBINS)
    return float(1.0 - ent)


def verdict_for(h):
    eps = 1.0 / NBINS * 0.5
    duple = h[[3, 6, 9]].mean()
    triple = h[[4, 8]].mean()
    ratio = float((triple + eps) / (duple + eps))
    v = "compound" if ratio > 1.15 else ("straight" if ratio < 0.87 else "ambiguous")
    return v, round(ratio, 2), round(float(duple), 4), round(float(triple), 4)


def analyze(name, start=None, end=None, label=""):
    kw = {"offset": start, "duration": end - start} if start is not None else {}
    mix, sr = librosa.load(WAV / f"{name}.wav", sr=SR, mono=True, **kw)
    drums, _ = librosa.load(STEMS / name / "drums.wav", sr=SR, mono=True, **kw)

    _, beats = librosa.beat.beat_track(y=mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    if len(bt) < 6:
        return {"label": label, "error": "not enough beats"}
    period = float(np.median(np.diff(bt)))
    t0 = float(bt[0])

    res = {"label": label, "detected_bpm": round(60.0 / period, 1),
           "felt_bpm_half": round(30.0 / period, 1), "bands": {}}
    for band, (lo, hi) in BANDS.items():
        env = band_envelope(drums, sr, lo, hi)
        times = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=HOP)
        best = None
        for mult in (0.5, 1.0, 2.0):
            h = phase_hist(env, times, t0, period * mult)
            c = concentration(h)
            if best is None or c > best[0]:
                best = (c, mult, h)
        conf, mult, h = best
        v, ratio, duple, triple = verdict_for(h)
        if conf < CONF_FLOOR:
            v = "no_clear_grid"
        res["bands"][band] = {
            "verdict": v, "triple_over_duple": ratio, "confidence": round(conf, 4),
            "grid_mult": mult, "energy_share": round(float(env.mean()), 4),
            "histogram": [round(float(x), 4) for x in h],
        }
    return res


def fmt(r):
    if "error" in r:
        return f"{r['label']:<26} ERROR {r['error']}"
    parts = [f"{b} {r['bands'][b]['verdict']:<13}r={r['bands'][b]['triple_over_duple']:.2f} "
             f"c={r['bands'][b]['confidence']:.3f}" for b in ("low", "mid", "high")]
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
        (OUT / f"meter3_{name}.json").write_text(json.dumps(out, indent=2))
    else:
        for n in sys.argv[1:]:
            print(fmt(analyze(n, label=n)))
