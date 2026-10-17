"""Build a drum kit out of audio you already have.

Separates drums, finds hits that are ISOLATED enough to be usable as one-shots
(quiet before, nothing on top), sorts them into kick / snare / tom / hat by
where their energy sits, and writes the cleanest few of each to a kit folder.

    .venv/bin/python -m analysis.extract_kit "example_mixes/<file>" --name surma

Hits mined from someone else's mix are their recordings — fine for study and
practice, the same "spec, not material" line the research notes draw. For a
competition mix, prefer your own team's audio or a licensed pack.
"""
import argparse
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from app.core import audio, stems

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
KITS = ROOT / "library" / "audio" / "kits"


def band(y, lo, hi):
    sos = butter(4, [lo, hi], "bandpass", fs=SR, output="sos")
    return sosfiltfilt(sos, y).astype(np.float32)


def classify(seg):
    """Where does this hit's energy live, and how long does it last?"""
    e = {"sub": np.sum(band(seg, 25, 120) ** 2),
         "low": np.sum(band(seg, 120, 400) ** 2),
         "mid": np.sum(band(seg, 400, 2000) ** 2),
         "high": np.sum(band(seg, 2000, 12000) ** 2)}
    total = sum(e.values()) + 1e-12
    f = {k: v / total for k, v in e.items()}
    env = np.abs(seg)
    peak = env.max() + 1e-12
    tail = np.argmax(env[::-1] > peak * 0.05)
    dur = (len(seg) - tail) / SR
    if f["high"] > 0.55 and dur < 0.25:
        return "hat", f
    if f["sub"] + f["low"] > 0.72 and dur < 0.55:
        return "kick", f
    if f["low"] + f["mid"] > 0.55 and dur < 0.45:
        return "tom", f
    if f["mid"] + f["high"] > 0.45:
        return "snare", f
    return "other", f


def isolation(env, i, pre=int(0.06 * SR)):
    """How quiet is it just before the hit? Clean one-shots start from silence."""
    a = max(0, i - pre)
    before = env[a:i].mean() + 1e-9
    after = env[i:i + int(0.02 * SR)].max() + 1e-9
    return float(after / before)


def extract(src: Path, name: str, per_class: int = 6):
    drums = stems.existing(src)
    if drums:
        y = librosa.load(drums["drums"], sr=SR, mono=True)[0]
    else:
        print("  separating drums first (Demucs)…")
        stems._run(audio._key(src), src)
        y = librosa.load(stems.existing(src)["drums"], sr=SR, mono=True)[0]

    env = np.abs(y)
    env = np.convolve(env, np.ones(221) / 221, mode="same")
    on = librosa.onset.onset_detect(y=y, sr=SR, hop_length=128, units="samples",
                                    backtrack=True)
    found = {}
    for k, i in enumerate(on):
        nxt = on[k + 1] if k + 1 < len(on) else len(y)
        seg = y[i:min(nxt, i + int(0.9 * SR))]
        if len(seg) < int(0.04 * SR) or np.abs(seg).max() < 0.02:
            continue
        iso = isolation(env, i)
        if iso < 6:                       # something else was already ringing
            continue
        kind, _ = classify(seg)
        if kind == "other":
            continue
        found.setdefault(kind, []).append((iso, i, seg))

    out = KITS / name
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for kind, hits in found.items():
        hits.sort(key=lambda h: -h[0])            # cleanest first
        for n, (iso, i, seg) in enumerate(hits[:per_class], 1):
            s = seg.copy()
            f = min(len(s), int(0.004 * SR))
            s[-f:] *= np.linspace(1, 0, f)        # no click at the cut
            s = s / (np.abs(s).max() + 1e-9) * 0.9
            sf.write(out / f"{kind}_{n:02d}.wav", np.stack([s, s]).T, SR, subtype="PCM_16")
        written[kind] = min(len(hits), per_class)
    return written, out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--name", required=True)
    ap.add_argument("--per-class", type=int, default=6)
    a = ap.parse_args()
    w, out = extract(Path(a.source), a.name, a.per_class)
    print(f"  {out.relative_to(ROOT)}: " + ", ".join(f"{k} x{v}" for k, v in sorted(w.items())))
