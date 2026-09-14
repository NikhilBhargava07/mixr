"""Per-segment analysis inside a full set.

Full-set numbers are useless for style study (they average 7 styles together).
This slices a mix + its stems to a time range and runs the full battery:
tempo, key, subdivision (duple vs compound, per band), percussion density,
and vocal-vs-drum grid alignment.

Usage:
    segment.py <mix_name> <start_sec> <end_sec> <label>
    segment.py --map <mix_name> <map.json>   # batch from a segment map
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
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def estimate_key(ch):
    best = max(((np.corrcoef(np.roll(p, i), ch)[0, 1], f"{NOTES[i]} {n}")
                for i in range(12) for p, n in ((MAJOR, "major"), (MINOR, "minor"))),
               key=lambda x: x[0])
    return {"key": best[1], "confidence": round(float(best[0]), 3)}


def band_onsets(y, sr, lo, hi):
    S = np.abs(librosa.stft(y, hop_length=HOP))
    fr = librosa.fft_frequencies(sr=sr)
    mask = (fr >= lo) & (fr < hi)
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S[mask] ** 2), hop_length=HOP)
    f = librosa.onset.onset_detect(onset_envelope=env, hop_length=HOP,
                                   backtrack=False, delta=0.35)
    return librosa.frames_to_time(f, sr=sr, hop_length=HOP), env[f]


def twelve_bin(times, strengths, bt):
    h = np.zeros(12)
    for t, w in zip(times, strengths):
        i = np.searchsorted(bt, t) - 1
        if 0 <= i < len(bt) - 1:
            h[int((t - bt[i]) / (bt[i + 1] - bt[i]) * 12) % 12] += w
    return h / (h.sum() + 1e-9)


def load_slice(path, start, end):
    y, sr = librosa.load(path, sr=SR, mono=True, offset=start, duration=end - start)
    return y, sr


def analyze(name, start, end, label):
    mix, sr = load_slice(WAV / f"{name}.wav", start, end)
    drums, _ = load_slice(STEMS / name / "drums.wav", start, end)
    vox, _ = load_slice(STEMS / name / "vocals.wav", start, end)
    other, _ = load_slice(STEMS / name / "other.wav", start, end)

    tempo, beats = librosa.beat.beat_track(y=mix, sr=sr, hop_length=HOP, trim=False)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    tempo = float(np.atleast_1d(tempo)[0])
    chroma = librosa.feature.chroma_cqt(y=other + mix * 0.3, sr=sr, hop_length=HOP)

    res = {"label": label, "start": start, "end": end,
           "mmss": f"{int(start//60)}:{start%60:04.1f}-{int(end//60)}:{end%60:04.1f}",
           "tempo_bpm": round(tempo, 1), "tempo_half": round(tempo / 2, 1),
           "key": estimate_key(chroma.mean(axis=1)),
           "rms": round(float(np.sqrt((mix ** 2).mean())), 4), "bands": {}}

    dur = end - start
    for band, (lo, hi) in BANDS.items():
        t, s = band_onsets(drums, sr, lo, hi)
        h = twelve_bin(t, s, bt) if len(bt) > 4 else np.zeros(12)
        duple = h[[3, 6, 9]].sum() / 3
        triple = h[[4, 8]].sum() / 2
        ratio = float(triple / (duple + 1e-9))
        res["bands"][band] = {
            "onsets_per_sec": round(len(t) / dur, 2),
            "triple_over_duple": round(ratio, 2),
            "verdict": "compound" if ratio > 1.3 else ("straight" if ratio < 0.77 else "ambiguous"),
        }

    # vocal alignment
    venv = librosa.onset.onset_strength(y=vox, sr=sr, hop_length=HOP)
    vf = librosa.onset.onset_detect(onset_envelope=venv, hop_length=HOP, backtrack=False, delta=0.3)
    vt, vs = librosa.frames_to_time(vf, sr=sr, hop_length=HOP), venv[vf]
    denv = librosa.onset.onset_strength(y=drums, sr=sr, hop_length=HOP)
    df = librosa.onset.onset_detect(onset_envelope=denv, hop_length=HOP, backtrack=False, delta=0.3)
    dt, ds = librosa.frames_to_time(df, sr=sr, hop_length=HOP), denv[df]
    vrms = librosa.feature.rms(y=vox, hop_length=HOP)[0]
    if len(bt) > 4 and len(vt) and len(dt):
        vh, dh = twelve_bin(vt, vs, bt), twelve_bin(dt, ds, bt)
        cos = float(np.dot(vh, dh) / (np.linalg.norm(vh) * np.linalg.norm(dh) + 1e-9))
    else:
        cos = float("nan")
    res["vocal"] = {
        "coverage": round(float((vrms > max(0.02, np.percentile(vrms, 60) * 0.5)).mean()), 3),
        "onsets_per_sec": round(len(vt) / dur, 2),
        "vocal_drum_cosine": round(cos, 3),
    }
    return res


def fmt(r):
    b = r["bands"]
    return (f"{r['mmss']:>17} {r['label']:<22} {r['tempo_bpm']:6.1f}(/2={r['tempo_half']:5.1f}) "
            f"{r['key']['key']:<9} rms {r['rms']:.3f} | "
            f"lo {b['low']['verdict']:<9}{b['low']['triple_over_duple']:5.2f} "
            f"mid {b['mid']['verdict']:<9}{b['mid']['triple_over_duple']:5.2f} "
            f"hi {b['high']['verdict']:<9}{b['high']['triple_over_duple']:5.2f} | "
            f"vox {r['vocal']['onsets_per_sec']:4.2f}/s cos {r['vocal']['vocal_drum_cosine']:.2f}")


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
        (OUT / f"segments_{name}.json").write_text(json.dumps(out, indent=2))
    else:
        name, start, end, label = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
        print(fmt(analyze(name, start, end, label)))
