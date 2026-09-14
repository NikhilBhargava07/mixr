"""Render synthesized percussion beds from the dancer's annotations.

Three of these are an experiment, not just a demo. The open question is whether
DDN chaal preserves traditional chaal's 12/8 "dum-di" triplet lilt, or whether
the "1, a 2, 3, a 4" kick the dancer described is a straight-16th pickup.
So we render BOTH and let the ear decide.

Outputs to renders/.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from instruments import (SR, dagga, tilli, dhol_ghost, kick, snare, hat, clap,
                         tumbi, sub_bass, drone, note_hz, impact)
from sequencer import Sequencer, write

OUT = Path(__file__).resolve().parent.parent / "renders"
OUT.mkdir(exist_ok=True)


def jhummar_bed(bpm=95.0, bars=8):
    """Dancer annotation: 'straight eighths', 'light', 'bouncy', 'funk like'.
    So: syncopated light bass, lifted eighth-note treble with ghosts.
    Deliberately NOT triplet - the annotation ruled that out."""
    sq = Sequencer(bpm, bars, slots_per_beat=4)
    # light syncopated dagga - funk placement, not four-on-the-floor
    sq.pattern("dagga", "X...|..x.|X...|..x.",
               lambda: dagga(dur=0.34, f0=88, f1=54, amp=0.72, click=0.4),
               gain=0.9, seed=1)
    # bouncy straight eighths: ghost on the beat, accent on the '&'
    sq.pattern("tilli", "o.Xo|o.X.|o.Xo|o.X.",
               lambda: tilli(dur=0.14, amp=0.62, tone=2600, seed=np.random.randint(999)),
               gain=0.95, seed=2)
    # 16th filler for the funk feel
    sq.pattern("ghost", "..o.|.oo.|..o.|.o.o",
               lambda: dhol_ghost(seed=np.random.randint(999)), gain=0.7, seed=3)
    sq.track("dagga").pan = -0.05
    sq.track("tilli").pan = 0.12
    sq.track("ghost").pan = -0.25
    return sq


def chaal_straight(bpm=99.0, bars=8):
    """Reading '1, a 2, 3, a 4' as STRAIGHT 16ths: the 'a' is the last
    sixteenth before the beat."""
    sq = Sequencer(bpm, bars, slots_per_beat=4)
    sq.pattern("kick", "X..x|x...|X..x|x...",
               lambda: kick(dur=0.46, f0=125, f1=44, amp=1.0), gain=1.0, seed=4)
    sq.pattern("dagga", "X..x|....|X..x|....",
               lambda: dagga(dur=0.42, f0=96, f1=50, amp=0.8), gain=0.85, seed=5)
    sq.pattern("tilli", "..x.|X.x.|..x.|X.x.",
               lambda: tilli(dur=0.15, amp=0.6, seed=np.random.randint(999)),
               gain=0.9, seed=6)
    sq.track("tilli").pan = 0.15
    return sq


def chaal_triplet(bpm=99.0, bars=8):
    """Reading it as COMPOUND 12/8 - traditional chaal's documented
    'dum-di, dum-di'. The 'a' is the last triplet-eighth before the beat."""
    sq = Sequencer(bpm, bars, slots_per_beat=3)     # 3 slots per beat = triplets
    sq.pattern("kick", "X.x|X..|X.x|X..",
               lambda: kick(dur=0.46, f0=125, f1=44, amp=1.0), gain=1.0, seed=7)
    sq.pattern("dagga", "X.x|...|X.x|...",
               lambda: dagga(dur=0.42, f0=96, f1=50, amp=0.8), gain=0.85, seed=8)
    sq.pattern("tilli", ".xx|Xxx|.xx|Xxx",
               lambda: tilli(dur=0.15, amp=0.55, seed=np.random.randint(999)),
               gain=0.9, seed=9)
    sq.track("tilli").pan = 0.15
    return sq


def jhummar_musical(bpm=95.0, bars=16, root="F#", octave=3):
    """A fuller jhummar sketch: bed + tumbi hook + drone + bass.
    Traditional bhangra melody is modal over a drone, not chord changes -
    so: one tonal center, a repetitive plucked hook, sustained drone under."""
    sq = jhummar_bed(bpm, bars)
    spb = 60.0 / bpm
    f_root = note_hz(root, octave)

    # drone across the whole thing (algoza-style sustained pipe)
    sq.place("drone", 0.0, drone(f_root, sq.total, amp=0.20))
    sq.place("drone", 0.0, drone(f_root * 1.5, sq.total, amp=0.10))   # fifth

    # tumbi hook - repetitive, high, nasal. Minor pentatonic-ish over the root.
    scale = [0, 3, 5, 7, 10, 12]          # minor pentatonic + octave
    hook = [0, 3, 2, 3, 0, 5, 3, 2]        # indices into scale
    for bar in range(bars):
        if bar % 2 == 1 and bar < 4:
            continue                        # let it breathe early
        for i, si in enumerate(hook):
            semi = scale[si]
            f = f_root * 2 * (2 ** (semi / 12))
            t = bar * sq.bar_dur + i * (spb / 2)
            sq.place("tumbi", t, tumbi(f, dur=0.26, amp=0.30,
                                       seed=np.random.randint(999)))

    # bass follows the dagga placement, root-heavy
    for bar in range(bars):
        for beat_off in (0.0, 1.5, 2.0, 3.5):
            t = bar * sq.bar_dur + beat_off * spb
            sq.place("bass", t, sub_bass(f_root / 2, 0.4, amp=0.30))

    # structural moments: dip then drop (corpus rule)
    for tr in ("tumbi", "bass"):
        sq.tracks[tr].events = [(t, a) for (t, a) in sq.tracks[tr].events
                                if not (sq.bar_dur * 7 <= t < sq.bar_dur * 8)]
    sq.place("fx", sq.bar_dur * 8, impact(1.6, amp=0.65))
    sq.track("tumbi").pan = 0.3
    sq.track("drone").pan = -0.2
    return sq


if __name__ == "__main__":
    jobs = [
        ("jhummar_bed_95bpm", jhummar_bed()),
        ("chaal_STRAIGHT16_99bpm", chaal_straight()),
        ("chaal_TRIPLET12-8_99bpm", chaal_triplet()),
        ("jhummar_musical_sketch_95bpm", jhummar_musical()),
    ]
    for name, sq in jobs:
        p = write(str(OUT / f"{name}.wav"), sq.render())
        print(f"wrote {p}")
