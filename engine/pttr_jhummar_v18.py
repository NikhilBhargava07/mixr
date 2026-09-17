"""PTTR x Jhummar — v18. THE FLAM WAS INSIDE THE KICK. Built from research/knowledge/placement_science.md.

Every change below traces to a measurement.

1. THROUGH-COMPOSED, NOT LOOPED.  Measured: real jhummar beds score 0.004-0.136
   bar-to-bar self-consistency; a synthetic exact loop scores 0.917. Real DDN
   drum beds do not repeat. So the bed here is generated stochastically: the
   structural kick on count 1 is certain, everything ornamental is probabilistic
   with per-bar variation, and no two bars come out identical.

2. KICK RATE LIMIT.  Measured: a kick occupies 420ms; an 8th at 99 BPM is
   303ms. Two kicks an 8th apart OVERLAP by ~117ms and smear into one event.
   So the kick never plays faster than one per beat, and mostly sits on 1
   (plus 3 on some bars).

3. NO LAYERED SUB.  Measured: sub peaks at 36ms, kick at 6.6ms -> layering them
   is a flam, which the dancer heard. Single voice only.

4. BAND BALANCE toward the measured real-jhummar target L/M/H 80/12/6.
   v13's first attempt rendered 91.4/6.9/1.8 — WORSE than v12. Gains were
   swept empirically against the rendered bed; sub_level 0.30 + tilli 1.5 +
   air 0.34 lands at 80.2/14.3/5.5, essentially on target. tilli gets
   more air; a varied (never constant) high accent replaces the rejected
   constant-8th shaker.

5. MASKING WINDOW.  Upward spread of masking means high-band detail right after
   the kick is partly inaudible. Ornaments are suppressed in the ~120ms after
   any count-1 kick.

6. KICK+BASS AS ONE OBJECT.  Overlapping critical bands -> the graceful section
   drops both together (measured: bass -72 to -77% while melody rises).

v15/v16 — THE "PA-BUM", PROPERLY DIAGNOSED.

What it is NOT: dagga2's own components peak 0.5ms apart. Not an internal flam.

v15 attempt (FAILED, recorded so we don't repeat it): PTTR's strongest low
event sits a median +81ms after the grid downbeat, so I delayed the whole bed
78ms to match. Flam-candidate rate got WORSE, 46% -> 58%. Reason: that median
had sd 77ms — as large as the offset. PTTR's low events are SCATTERED, not
consistently late, so there is no single offset that aligns to them.

Measured root cause: PTTR's own low end is already event-dense.
    PTTR bass alone   32% flam-candidate rate
    PTTR other alone  74%
    bass+other        61%
Any kick placed anywhere will collide with some of them. This is a LEVEL
problem, not a timing problem.

v16 attempt (also insufficient): SIDECHAIN DUCKING. PTTR's low end is briefly attenuated around each
bed kick, so only one low-frequency event is audible at a time — the standard
production solution to exactly this collision.

v18 — ROOT CAUSE FOUND. A single dagga2 hit, in silence, produces TWO
low-band attacks: +26ms and +102ms. The pitch sweep 98->50Hz descends slowly
enough that it re-triggers a second perceptual attack as it falls. 76ms apart
= textbook flam. This is the "pa-bum", it lives INSIDE one kick, and no amount
of timing, offsetting, or sidechain ducking could ever have removed it —
which is exactly why v15 and v16 both failed.

Parameter sweep for a single attack:
    f0=98 f1=50 rate=14  -> 2 peaks (26, 102ms)   <- what we had
    f0=98 f1=50 rate=40  -> 2 peaks (26, 189ms)
    f0=70 f1=50 rate=14  -> 1 peak                <- CHOSEN
    f0=55 f1=50 rate=30  -> 1 peak
    f0=50 f1=50 rate=20  -> 1 peak (no sweep at all)
A shallower sweep (70->50Hz) keeps the pitch-drop character that makes a drum
read as struck, while staying inside the band so it never re-triggers.

v17 (also correct, kept) — MEASURED THE COLLISION DIRECTLY AND REMOVED ITS CAUSE.

The earlier flam metric counted low-band peak pairs across the whole mix, which
is dominated by PTTR's own content (61% by itself) and therefore could not
isolate MY contribution. Correct metric: for each kick I place, is there a
competing PTTR low event 25-140ms away?

    PTTR bass low-passed 210Hz (v10-v16):  8/16 kicks collide  (50%)
    PTTR bass low-passed 120Hz          :  9/16 kicks collide  (56%)
    PTTR "other" high-passed 240Hz      :  2/16 kicks collide  (12%)
    PTTR bass REMOVED                   :  0/16 kicks collide  ( 0%)

So it is specifically PTTR's BASS STEM. Filtering does not help because the
bass notes live in the kick's register by definition.

TRADE-OFF, stated plainly: the dancer asked to keep all PTTR instruments except
drums. Measurement says PTTR's bass and an added kick cannot both own the low
register without flamming. v17 removes PTTR's bass so the kick lands clean on
count 1 — which was the other explicit request. The alternative (keep PTTR's
bass, drop the kick entirely and let PTTR's own bass be the foundation) is a
legitimate different mix and easy to render on request.

Grid unchanged: native 99.38 BPM, no stretch, downbeat 2.5658s from the
"bitch = count 1" anchor plus the half-beat pickup correction.
"""
import sys
from pathlib import Path

import numpy as np
import librosa
from scipy.signal import butter, sosfilt

sys.path.insert(0, str(Path(__file__).parent))
from instruments import (SR, dagga2, tilli2, thok, shaker, light_clap,
                         riser, impact, _highpass)
from sequencer import Sequencer, write

ROOT = Path(__file__).resolve().parent.parent
STEMS = ROOT / "workdir" / "stems" / "htdemucs" / "PTTR"
OUT = ROOT / "renders"

SWING = 0.54
BITCH_BAR = 7
INTRO_BARS = 6
GRACE = (14, 20)
TOTAL = 28
RNG = np.random.default_rng(7)


def pttr_grid():
    y, sr = librosa.load(ROOT / "workdir" / "wav" / "PTTR.wav", sr=22050, mono=True)
    _, b = librosa.beat.beat_track(y=y, sr=sr, hop_length=256, start_bpm=100, trim=False)
    bt = librosa.frames_to_time(b, sr=sr, hop_length=256)
    beat = float(np.median(np.diff(bt)))
    S = np.abs(librosa.stft(y, hop_length=256))
    fr = librosa.fft_frequencies(sr=sr)
    low = S[(fr >= 30) & (fr < 130)].mean(axis=0)
    lt = librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=256)
    sc = [0.0] * 4
    for k, tt in enumerate(bt[:200]):
        i = np.argmin(np.abs(lt - tt))
        sc[k % 4] += float(low[max(0, i - 2):i + 3].max())
    return float(bt[int(np.argmax(sc))]), beat * 4, 60.0 / beat


_REF, PTTR_BAR, PTTR_BPM = pttr_grid()
_BEAT = PTTR_BAR / 4
DOWNBEAT = _REF + 3 * _BEAT + 0.5 * _BEAT
assert abs(DOWNBEAT - 2.5658) < 0.01
BPM = PTTR_BPM


def load(stem, start_bar, n_bars):
    y, sr = librosa.load(STEMS / f"{stem}.wav", sr=SR, mono=False,
                         offset=max(0.0, DOWNBEAT + start_bar * PTTR_BAR),
                         duration=n_bars * PTTR_BAR)
    return (y if y.ndim > 1 else np.stack([y, y])).astype(np.float32)


def hp(x, c):
    return sosfilt(butter(4, c, btype="highpass", fs=SR, output="sos"), x, axis=-1).astype(np.float32)


def lp(x, c):
    return sosfilt(butter(4, c, btype="lowpass", fs=SR, output="sos"), x, axis=-1).astype(np.float32)


def bright_tilli(amp=1.0, seed=0):
    """tilli with extra air — v12 rendered only 2.5% high energy vs the ~6%
    measured in real jhummar beds."""
    t = tilli2(dur=0.15, amp=amp, amp_mid=0.62, seed=seed)
    air = _highpass(np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32), 7000)
    env = np.exp(-np.linspace(0, 1, len(t)) * 26).astype(np.float32)
    return (t + 0.35 * amp * air * env).astype(np.float32)


def build():
    sq = Sequencer(BPM, TOTAL, slots_per_beat=4, swing=SWING)
    bar, spb = sq.bar_dur, sq.spb
    play = [b for b in range(INTRO_BARS, TOTAL) if not (GRACE[0] <= b < GRACE[1])]

    # ---- STOCHASTIC BED: structure fixed, ornament varied every bar --------
    kick_times = []
    for bi in play:
        pos = bi - INTRO_BARS
        # --- kick: count 1 always; count 3 on ~45% of bars. Never faster than
        #     one per beat (rate limit: 420ms occupancy vs 303ms per 8th).
        kick_times.append(sq.slot_time(bi, 0))
        sq.place("kick", sq.slot_time(bi, 0),
                 dagga2(dur=0.44, f0=70, f1=50, amp=1.0, body=0.85,
                        click=0.0, sub_level=0.30))
        if RNG.random() < 0.45:
            kick_times.append(sq.slot_time(bi, 8))
            sq.place("kick", sq.slot_time(bi, 8),
                     dagga2(dur=0.40, f0=68, f1=50, amp=0.72, body=0.85,
                            click=0.0, sub_level=0.30))

        # --- tilli: the '&'s are the backbone, but velocity varies widely and
        #     each bar drops or adds one. Suppressed in the 120ms masking
        #     window after the count-1 kick.
        mask_until = sq.slot_time(bi, 0) + 0.12
        for slot in (2, 6, 10, 14):
            if RNG.random() < 0.88:
                t = sq.slot_time(bi, slot)
                if t < mask_until:
                    continue
                v = 0.95 + RNG.uniform(-0.22, 0.22)
                sq.place("tilli", t, bright_tilli(amp=v, seed=RNG.integers(9999)))
        # occasional extra 16th ornament — different slot each bar
        if RNG.random() < 0.55:
            slot = int(RNG.choice([3, 7, 11, 13, 15]))
            t = sq.slot_time(bi, slot)
            if t >= mask_until:
                sq.place("tilli", t, bright_tilli(amp=0.46 + RNG.uniform(0, 0.20),
                                                  seed=RNG.integers(9999)))

        # --- thok: mid articulation, roams. Never the same slot two bars running.
        choices = [4, 8, 12, 6, 10]
        slot = int(choices[(pos * 3 + int(RNG.integers(0, 2))) % len(choices)])
        sq.place("thok", sq.slot_time(bi, slot),
                 thok(amp=0.42 + RNG.uniform(-0.10, 0.14),
                      pitch=350 + RNG.uniform(-45, 45), seed=RNG.integers(9999)))
        if RNG.random() < 0.4:
            sq.place("thok", sq.slot_time(bi, int(RNG.choice([5, 9, 13]))),
                     thok(amp=0.26, pitch=420 + RNG.uniform(-50, 50), seed=RNG.integers(9999)))

        # --- high air, sparse and never on a fixed grid (the constant 8th
        #     shaker was rejected by the dancer as "tit tit tit")
        for _ in range(int(RNG.integers(1, 4))):
            slot = int(RNG.choice([3, 7, 11, 14, 15, 6, 10]))
            t = sq.slot_time(bi, slot)
            if t >= mask_until:
                sq.place("air", t, shaker(amp=0.30 + RNG.uniform(0, 0.14),
                                          seed=RNG.integers(9999)))
        # turnaround lift every 4th bar, with variation
        if pos % 4 == 3:
            sq.place("clap", sq.slot_time(bi, 14),
                     light_clap(amp=0.24 + RNG.uniform(0, 0.08), seed=RNG.integers(9999)))

    sq.track("kick").pan = 0.0
    sq.track("tilli").pan = 0.12
    sq.track("thok").pan = -0.20
    sq.track("air").pan = 0.30
    sq.track("clap").pan = 0.20

    base = sq.render()
    n = base.shape[1]

    def put(a, at_bar, gain=1.0, fin=0.12, fout=0.25, env=None):
        s = int(at_bar * bar * SR)
        a = a[:, : max(0, n - s)].copy()
        if a.shape[1] <= 0:
            return
        f, fo = int(fin * SR), int(fout * SR)
        if a.shape[1] > f + fo:
            a[:, :f] *= np.linspace(0, 1, f) ** 0.6
            a[:, -fo:] *= np.linspace(1, 0, fo)
        if env is not None:
            a *= np.interp(np.linspace(0, 1, a.shape[1]),
                           np.linspace(0, 1, len(env)), env)
        base[:, s:s + a.shape[1]] += a * gain

    def duck_env(length, times, depth=0.22, pre=0.012, hold=0.075, rel=0.16):
        """Sidechain: dip PTTR's low end around each kick so only one
        low-frequency event is audible at a time."""
        g = np.ones(length, dtype=np.float32)
        for tt in times:
            s = int((tt - pre) * SR)
            h = int(hold * SR); r = int(rel * SR)
            if s < 0 or s >= length:
                continue
            e1 = min(length, s + h)
            g[s:e1] = np.minimum(g[s:e1], depth)
            e2 = min(length, e1 + r)
            if e2 > e1:
                g[e1:e2] = np.minimum(g[e1:e2], np.linspace(depth, 1.0, e2 - e1))
        return g

    span, src = 22, BITCH_BAR - INTRO_BARS
    voc, oth, bas = (load(s, src, span) for s in ("vocals", "other", "bass"))
    steps = span * 8

    def env_for(kind):
        e = np.ones(steps, dtype=np.float32)
        g0, g1 = int(GRACE[0] / span * steps), int(GRACE[1] / span * steps)
        if kind == "bass":
            e[g0:g1] = 0.18
        elif kind == "other":
            e[g0:g1] = 1.55
        else:
            e[g0:g1] = 0.95
        k = 12
        return np.convolve(e, np.ones(k) / k, mode="same")

    put(hp(voc, 130), 0, gain=1.0, env=env_for("vocals"))
    put(hp(oth, 240), 0, gain=0.72, env=env_for("other"))
    # PTTR bass: split at 210Hz and duck ONLY the low part against the kick
    # PTTR bass REMOVED — measured 0/16 kick collisions vs 8/16 with it.
    # The synthesized kick now owns the low register outright.
    put(np.stack([riser(bar * 2.0, amp=0.30)] * 2), 20, gain=1.0, fin=0.02)

    for st, g in (("vocals", 1.05), ("other", 0.80)):
        a = load(st, BITCH_BAR, TOTAL - 22)
        a = hp(a, 130 if st == "vocals" else 240)
        put(a, 22, gain=g)
    imp = impact(1.7, amp=0.45)
    s = int(22 * bar * SR)
    base[:, s:s + len(imp)] += np.stack([imp, imp]) * 0.5
    return base


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    y = build()
    print("wrote", write(str(OUT / "PTTR_jhummar_v18.wav"), y), f"({y.shape[1]/SR:.1f}s)")
