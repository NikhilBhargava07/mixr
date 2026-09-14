"""Visual alignment chart — see exactly where every hit lands.

Rows, top to bottom:
    PTTR vocal      — vocal onsets, with lyric words marked
    PTTR low        — the song's own kick/bass events
    downbeats       — beat_this detected (blue) vs fixed grid (grey dashed)
    BED: kick / tilli / thok — what mixr places

Anything vertically aligned is simultaneous. Anything slightly offset is the
flam/drift you can hear.
"""
import sys
from pathlib import Path

import numpy as np
import librosa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
SR = 22050


def low_onsets(y, sr, lo=30, hi=160, delta=0.14):
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=128))
    fr = librosa.fft_frequencies(sr=sr, n_fft=1024)
    e = librosa.onset.onset_strength(
        S=librosa.power_to_db(S[(fr >= lo) & (fr < hi)] ** 2, ref=np.max), hop_length=128)
    e = e / (e.max() + 1e-9)
    pk = librosa.util.peak_pick(e, pre_max=4, post_max=4, pre_avg=8, post_avg=8,
                                delta=delta, wait=3)
    return librosa.frames_to_time(pk, sr=sr, hop_length=128), e


def draw(t0, t1, bed_times, out_png, title, words=None, downbeats=None,
         fixed_grid=None):
    fig, ax = plt.subplots(figsize=(15, 6.5))
    voc, sr = librosa.load(ROOT / "workdir/stems/htdemucs/PTTR/vocals.wav",
                           sr=SR, mono=True, offset=t0, duration=t1 - t0)
    oth, _ = librosa.load(ROOT / "workdir/stems/htdemucs/PTTR/other.wav",
                          sr=SR, mono=True, offset=t0, duration=t1 - t0)
    bas, _ = librosa.load(ROOT / "workdir/stems/htdemucs/PTTR/bass.wav",
                          sr=SR, mono=True, offset=t0, duration=t1 - t0)

    rows = {}
    y = 0
    # PTTR vocal envelope
    env = librosa.onset.onset_strength(y=voc, sr=sr, hop_length=128)
    env = env / (env.max() + 1e-9)
    te = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=128) + t0
    ax.fill_between(te, y, y + 0.85 * env, color="#7aa6d6", alpha=.85, lw=0)
    rows["PTTR vocal"] = y; y += 1.2

    # PTTR own low-frequency events
    tl, el = low_onsets(bas + oth, sr)
    ax.vlines(tl + t0, y, y + 0.9, color="#c1440e", lw=2.0)
    rows["PTTR low (bass+other)"] = y; y += 1.2

    # grids
    if downbeats is not None:
        for d in downbeats:
            if t0 <= d <= t1:
                ax.axvline(d, color="#2b6cb0", lw=1.6, alpha=.9, zorder=0)
    if fixed_grid is not None:
        for d in fixed_grid:
            if t0 <= d <= t1:
                ax.axvline(d, color="#888", lw=1.2, ls="--", alpha=.9, zorder=0)

    # bed
    colors = {"kick": "#111", "tilli": "#2e7d32", "thok": "#8e24aa", "air": "#00838f"}
    for name, times in bed_times.items():
        tt = [x for x in times if t0 <= x <= t1]
        ax.vlines(tt, y, y + 0.9, color=colors.get(name, "#555"), lw=2.6)
        rows[f"BED: {name}"] = y
        y += 1.1

    if words:
        for wt, w in words:
            if t0 <= wt <= t1:
                ax.text(wt, y + 0.15, w, rotation=0, fontsize=9, ha="center",
                        color="#b33", fontweight="bold")
                ax.vlines([wt], -0.2, y, color="#b33", lw=1.0, ls=":", alpha=.8)

    ax.set_yticks([v + 0.45 for v in rows.values()])
    ax.set_yticklabels(list(rows.keys()), fontsize=10)
    ax.set_xlim(t0, t1)
    ax.set_ylim(-0.3, y + 0.7)
    ax.set_xlabel("seconds")
    ax.set_title(title, fontsize=12)
    ax.grid(axis="x", alpha=.15)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return out_png
