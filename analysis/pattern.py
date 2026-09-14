"""Extract the actual drum pattern of a segment, per frequency band.

The blocker in every earlier attempt was the DOWNBEAT: without knowing where
bar 1 starts, a 16-slot pattern is meaningless. Solved here without needing
lyrics or user input:

    The correct downbeat phase is the one that makes the bar-to-bar pattern
    most SELF-CONSISTENT. A wrong phase smears different metrical positions
    together and lowers agreement between bars.

So we try all 4 phases, score each by mean inter-bar correlation, and keep the
winner. Output is a 16-slot x 3-band grid of onset energy, which is the thing
we actually want: where do low / mid / high hits land in the bar.

Bands map onto the physical instruments:
    low  20-160Hz    kick, dagga (dhol bass head)
    mid  160-2000Hz  drum body/shell, snare fundamental, thok, tilli body
    high 2-9kHz      hats, claps, tilli attack, transient air
"""
import sys
from pathlib import Path

import numpy as np
import librosa

ROOT = Path(__file__).resolve().parent.parent
WAV = ROOT / "workdir" / "wav"
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
SR = 22050
HOP = 128                    # fine resolution: 5.8ms
SLOTS = 16                   # 16th notes per bar
BANDS = {"low": (20, 160), "mid": (160, 2000), "high": (2000, 9000)}


def fit_grid(y, sr, anchor):
    _, b = librosa.beat.beat_track(y=y, sr=sr, hop_length=256, start_bpm=anchor, trim=False)
    bt = librosa.frames_to_time(b, sr=sr, hop_length=256)
    d = np.diff(bt)
    med = np.median(d)
    bt = bt[np.concatenate([[True], np.abs(d - med) < 0.25 * med])]
    idx = np.arange(len(bt))
    slope, inter = np.polyfit(idx, bt, 1)
    return float(slope), float(inter)      # beat period, first beat time


def band_env(y, sr, lo, hi):
    """Transient PEAKS only. Summing raw envelope energy makes every slot look
    equally loud (that was the v1 bug) — the pattern lives in the accents, so
    we subtract a moving baseline and keep only what pokes above it."""
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP))
    fr = librosa.fft_frequencies(sr=sr, n_fft=1024)
    m = (fr >= lo) & (fr < hi)
    e = librosa.onset.onset_strength(S=librosa.power_to_db(S[m] ** 2, ref=np.max),
                                     hop_length=HOP)
    W = 129                                   # ~0.75s moving baseline
    base = np.convolve(e, np.ones(W) / W, mode="same")
    e = np.maximum(e - base, 0.0)             # transients above local average
    # keep only local maxima so sustained energy cannot dominate
    peak = np.zeros_like(e)
    for i in range(1, len(e) - 1):
        if e[i] >= e[i - 1] and e[i] > e[i + 1]:
            peak[i] = e[i]
    return peak / (peak.max() + 1e-9)


def bar_matrix(env, times, t0, bar_dur):
    """Rows = bars, cols = 16 slots. Energy summed into each slot."""
    n_bars = int((times[-1] - t0) / bar_dur)
    if n_bars < 3:
        return None
    M = np.zeros((n_bars, SLOTS))
    pos = ((times - t0) / bar_dur)
    for bi in range(n_bars):
        m = (pos >= bi) & (pos < bi + 1)
        if not m.any():
            continue
        frac = pos[m] - bi
        slot = np.clip((frac * SLOTS).astype(int), 0, SLOTS - 1)
        np.add.at(M[bi], slot, env[m])
    return M


def consistency(M):
    """Mean pairwise correlation between bars. High = we found the real phase."""
    Mn = M - M.mean(axis=1, keepdims=True)
    sd = Mn.std(axis=1, keepdims=True) + 1e-9
    Mn = Mn / sd
    C = (Mn @ Mn.T) / SLOTS
    iu = np.triu_indices(len(M), k=1)
    return float(np.mean(C[iu])) if len(iu[0]) else 0.0


def analyze(name, start=None, end=None, anchor=95, label=""):
    kw = {"offset": start, "duration": end - start} if start is not None else {}
    mix, sr = librosa.load(WAV / f"{name}.wav", sr=SR, mono=True, **kw)
    dpath = STEMS / name / "drums.wav"
    drums, _ = librosa.load(dpath, sr=SR, mono=True, **kw) if dpath.exists() else (mix, sr)

    period, t_first = fit_grid(mix, sr, anchor)
    bar_dur = period * 4
    bpm = 60 / period
    while bpm > 130:
        bpm /= 2; bar_dur *= 2
    while bpm < 70:
        bpm *= 2; bar_dur /= 2

    envs = {b: band_env(drums, sr, lo, hi) for b, (lo, hi) in BANDS.items()}
    L = min(len(e) for e in envs.values())
    times = librosa.frames_to_time(np.arange(L), sr=sr, hop_length=HOP)
    envs = {b: e[:L] for b, e in envs.items()}

    # pick the downbeat phase that maximises bar-to-bar self-consistency
    best = None
    for ph in range(4):
        t0 = t_first + ph * (bar_dur / 4)
        while t0 < times[0]:
            t0 += bar_dur
        score, mats = 0.0, {}
        for b, e in envs.items():
            M = bar_matrix(e, times, t0, bar_dur)
            if M is None:
                continue
            mats[b] = M
            score += consistency(M)
        if mats and (best is None or score > best[0]):
            best = (score, ph, t0, mats)
    if best is None:
        return None
    score, ph, t0, mats = best
    out = {"label": label or name, "bpm": round(bpm, 2), "phase": ph,
           "consistency": round(score / 3, 3), "bars": len(next(iter(mats.values())))}
    for b, M in mats.items():
        v = M.mean(axis=0)
        # z-score across slots so CONTRAST is visible, not absolute level
        out[b] = (v - v.mean()) / (v.std() + 1e-9)
    return out


def show(r):
    print(f"\n{r['label']}   {r['bpm']:.2f} BPM   ({r['bars']} bars, "
          f"phase-consistency {r['consistency']:.3f})")
    print("        slot: 1  e  &  a  2  e  &  a  3  e  &  a  4  e  &  a")
    for b in ("low", "mid", "high"):
        v = r[b]
        cells = "".join(f"{'#' if x > 1.1 else '+' if x > 0.45 else '-' if x > -0.2 else '.':>3}"
                        for x in v)
        print(f"  {b:>5}      {cells}")


if __name__ == "__main__":
    JHUMMAR = [
        ("VC_Surma_GB_V1E2_2026", 8, 70, 95, "jhummar VC [Surma]"),
        ("Michigan_Izzat_2026", 112, 185, 92, "jhummar V3NOM [Izzat]"),
        ("Mohini_Jhummar_2024", 5, 58, 92, "jhummar [Mohini 2024]"),
        ("Manzat_Jhummar_2024", 5, 66, 93, "jhummar [Manzat 2024]"),
        ("Virasat_Jhummar_2024", 5, 66, 86, "jhummar [Virasat 2024]"),
        ("Virasat_Jhummar_2025", 5, 80, 99, "jhummar [Virasat 2025]"),
        ("Shershaah_Buckeye_2026", 310, 382, 101, "jhummar Rev7in [Shershaah]"),
        ("Purdue_Kahaani_2026", 258, 365, 93, "jhummar TK+DG [Purdue]"),
    ]
    BHANGRA = [
        ("Shershaah_Buckeye_2026", 38, 58, 98, "CHAAL Astro [Shershaah]"),
        ("Virasat_Khunde_2025", 6, 66, 99, "khunde V3NOMxLotus"),
        ("Virasat_Saap_2025", 6, 55, 98, "saap SubsonicxLotus"),
        ("Shershaah_Buckeye_2026", 455, 550, 100, "finale Astro [Shershaah]"),
        ("Purdue_Kahaani_2026", 505, 565, 99, "ender bhangra V3NOM+DG"),
    ]
    which = sys.argv[1] if len(sys.argv) > 1 else "jhummar"
    rows = JHUMMAR if which == "jhummar" else BHANGRA
    print(f"===== {which.upper()}   ( # >0.72   + >0.45   - >0.25   . weak )")
    got = []
    for args in rows:
        r = analyze(*args[:4], label=args[4])
        if r:
            show(r)
            got.append(r)
    if len(got) > 1:
        print(f"\n\n===== AVERAGE ACROSS {len(got)} SEGMENTS")
        avg = {"label": f"MEAN {which}", "bpm": np.mean([g['bpm'] for g in got]),
               "bars": 0, "consistency": np.mean([g['consistency'] for g in got])}
        for b in ("low", "mid", "high"):
            m = np.mean([g[b] for g in got], axis=0)
            avg[b] = (m - m.mean()) / (m.std() + 1e-9)
        show(avg)
        for b in ("low", "mid", "high"):
            v = avg[b]
            top = np.argsort(v)[::-1][:5]
            names = ["1", "1e", "1&", "1a", "2", "2e", "2&", "2a",
                     "3", "3e", "3&", "3a", "4", "4e", "4&", "4a"]
            print(f"  {b:>5} strongest slots: " +
                  ", ".join(f"{names[i]}({v[i]:.2f})" for i in sorted(top, key=lambda i: -v[i])))
