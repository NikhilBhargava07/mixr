"""Compound vs straight meter — the test that finally worked (2026-08-10).

Recovered verbatim from the session that produced the published results,
after it turned out to exist only in a chat log. Kept here so it can't be
lost again.

WHY IT WORKS where four earlier methods failed: it takes the FELT tempo as an
independent input (the dancer's ground truth, or a regression fit), then asks
where periodic energy sits relative to it. Earlier methods inferred everything
from audio alone and ended up measuring the beat tracker's own choice.

Compound / 12-8 music puts tempogram energy at 1.5x the felt pulse (dotted
groupings); straight 4/4 puts it at 2x.  ratio = E(1.5x) / E(2x).

    .venv/bin/python -m analysis.compound          # re-run the validation
"""
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "workdir" / "wav"
SR = 22050
HOP = 512


def ratio(y, sr, felt: float, tol: float = 0.055) -> dict:
    """E(1.5x felt) / E(2x felt) from the mean tempogram of `y`."""
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tg = librosa.feature.tempogram(onset_envelope=oenv, sr=sr, hop_length=HOP)
    fr = librosa.tempo_frequencies(tg.shape[0], sr=sr, hop_length=HOP)
    st = tg.mean(axis=1)

    def energy_near(target):
        m = np.abs(fr - target) / target < tol
        return float(st[m].max()) if m.any() else 0.0

    e15, e20 = energy_near(felt * 1.5), energy_near(felt * 2.0)
    r = e15 / (e20 + 1e-9)
    verdict = "COMPOUND-leaning" if r > 1.12 else ("straight-leaning" if r < 0.89 else "ambiguous")
    return {"felt": felt, "e15": e15, "e20": e20, "ratio": r, "verdict": verdict}


def ratio_file(path, start: float, end: float, felt: float) -> dict:
    y, sr = librosa.load(str(path), sr=SR, mono=True, offset=start, duration=end - start)
    return ratio(y, sr, felt)


# (file stem, start, end, felt BPM, label, published ratio)
VALIDATION = [
    ("Michigan_Izzat_2026", 325, 400, 117.45, "Smooth Criminal [known straight]", 0.53),
    ("Shershaah_Buckeye_2026", 59, 81, 73.66, "Shershaah hiphop [straight]", 0.58),
    ("Hip_hop_1_", 5, 60, 71.8, "Surma hiphop [straight]", 0.81),
    ("Shershaah_Buckeye_2026", 38, 58, 98.13, "Shershaah CHAAL [Astro]", 1.44),
]


if __name__ == "__main__":
    print("re-running the published validation:\n")
    for stem, s, e, felt, label, published in VALIDATION:
        r = ratio_file(WAV / f"{stem}.wav", s, e, felt)
        same = abs(r["ratio"] - published) < 0.01
        print(f"  {label:34} ratio {r['ratio']:5.2f}  (published {published:.2f})  "
              f"{'✓ reproduced' if same else '✗ DIFFERS'}")
