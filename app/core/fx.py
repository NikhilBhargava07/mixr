"""The channel strip — what a track's sound goes through after warping.

One fixed strip per track rather than a rack of plugins: eight controls in the
order an engineer would reach for them, so nothing has to be wired up and
nothing can be put in a silly order.

    high-pass -> low-pass -> low shelf -> punch -> drive -> compress -> output -> safety limiter

Rendered on the server with the warped audio and cached alongside it, so what
you hear is exactly what exports — the same rule as everything else in mixr.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

# name: (off / default, min, max)
STRIP = {
    "hp_hz":    (20.0,    20.0,  400.0),   # high-pass; 20 = off
    "lp_hz":    (20000.0, 60.0, 20000.0),  # low-pass; 20000 = off
    "low_db":   (0.0,    -12.0,  12.0),    # low shelf boost/cut
    "low_hz":   (80.0,    30.0,  250.0),   # ...and where it starts
    "punch":    (0.0,     -1.0,   1.0),    # transient shaper: + harder hits, - softer
    "drive_db": (0.0,      0.0,  24.0),    # saturation: density and grit
    "comp":     (0.0,      0.0,   1.0),    # compression amount
    "gain_db":  (0.0,    -24.0,  12.0),    # output level
}

PRESETS = {
    "Punch":      {"low_db": 4.0, "low_hz": 70.0, "punch": 0.6, "drive_db": 4.0, "comp": 0.35},
    "Kick only":  {"lp_hz": 160.0, "low_db": 3.0, "low_hz": 60.0, "punch": 0.5, "comp": 0.25},
    "Sub weight": {"low_db": 6.0, "low_hz": 55.0, "drive_db": 6.0, "comp": 0.3},
    "Clean":      {},
}


def normalize(params: dict | None) -> dict:
    """Every control present, each clamped to its range."""
    params = params or {}
    out = {}
    for k, (d, lo, hi) in STRIP.items():
        v = params.get(k, d)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = d
        out[k] = round(min(hi, max(lo, v)), 4)
    return out


def is_identity(p: dict) -> bool:
    """A strip whose every active control is at 'off' — low_hz only matters
    when the shelf is actually boosting or cutting."""
    return all(p[k] == STRIP[k][0] for k in STRIP if k != "low_hz")


def params_of(effects) -> dict | None:
    """The active strip's settings from a track's effect list, or None."""
    for e in effects or []:
        e = e if isinstance(e, dict) else e.__dict__
        if e.get("kind") == "strip" and e.get("enabled", True):
            p = normalize(e.get("params"))
            return None if is_identity(p) else p
    return None


def signature(p: dict) -> str:
    return hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- processing
def _onepole(x, tau: float, sr: int):
    from scipy.signal import lfilter
    a = np.exp(-1.0 / (tau * sr))
    return lfilter([1 - a], [1, -a], x)


def steep(y, sr, kind: str, hz: float):
    """24 dB/octave Butterworth. pedalboard's own filters are 6 dB/octave,
    which let a hi-hat through a 160 Hz low-pass at only -25 dB — useless for
    pulling a kick out of a drum stem.

    A steep filter delays what it passes by a few ms. On a kick that's a flam
    against every other track, so the delay is measured in the passband and
    shifted back out."""
    from scipy.signal import butter, sosfilt, group_delay, sos2tf
    sos = butter(4, hz, kind, fs=sr, output="sos")
    out = sosfilt(sos, y, axis=1).astype(np.float32)
    probe = hz / 3 if kind == "lowpass" else min(hz * 3, sr / 2.5)
    b, a = sos2tf(sos)
    _, gd = group_delay((b, a), w=[probe], fs=sr)
    d = int(round(float(gd[0])))
    if d > 0:
        out = np.concatenate([out[:, d:], np.zeros((out.shape[0], d), np.float32)], axis=1)
    return out


def transient(y, sr, amount: float):
    """Punch. A fast envelope races ahead of a slow one at every attack; the
    gap between them says 'this is a hit', and the gain follows it — up for
    harder hits, down for softer ones. Both channels get the same gain so the
    stereo image doesn't wobble."""
    if abs(amount) < 1e-6:
        return y
    m = np.abs(y).max(axis=0)
    fast, slow = _onepole(m, 0.002, sr), _onepole(m, 0.050, sr)
    t = np.clip(fast / (slow + 1e-9) - 1.0, 0.0, 3.0)
    g = 1.0 + amount * 0.6 * t if amount > 0 else 1.0 / (1.0 + (-amount) * 0.6 * t)
    g = np.clip(_onepole(g, 0.001, sr), 0.25, 3.0)
    return (y * g).astype(np.float32)


def drive(y, drive_db: float):
    """Soft saturation that crossfades in over the first 3 dB, so the knob has
    no jump between 'off' and 'a little'. Quiet material passes at unity gain;
    peaks round off, which reads as density and weight."""
    if drive_db <= 0:
        return y
    g = 10 ** (drive_db / 20)
    wet = np.tanh(g * y) / g
    mix = min(1.0, drive_db / 3.0)
    return (y + (wet - y) * mix).astype(np.float32)


def apply(y, sr: int, p: dict):
    """Run (channels, samples) audio through the strip."""
    import pedalboard as pb
    y = np.ascontiguousarray(y, dtype=np.float32)
    if p["hp_hz"] > STRIP["hp_hz"][0]:
        y = steep(y, sr, "highpass", p["hp_hz"])
    if p["lp_hz"] < STRIP["lp_hz"][0]:
        y = steep(y, sr, "lowpass", p["lp_hz"])
    if p["low_db"] != 0:
        y = pb.Pedalboard([pb.LowShelfFilter(cutoff_frequency_hz=p["low_hz"],
                                             gain_db=p["low_db"])])(np.ascontiguousarray(y), sr)
    y = transient(y, sr, p["punch"])
    y = drive(y, p["drive_db"])
    post = []
    if p["comp"] > 0:
        a = p["comp"]
        thr, ratio = -30.0 * a, 1.0 + 7.0 * a
        # 8 ms attack lets each hit's front edge through before the
        # compressor clamps down — compression that keeps the punch
        post.append(pb.Compressor(threshold_db=thr, ratio=ratio, attack_ms=8.0, release_ms=120.0))
        post.append(pb.Gain(gain_db=-thr * (1 - 1 / ratio) * 0.6))       # auto makeup
    if p["gain_db"] != 0:
        post.append(pb.Gain(gain_db=p["gain_db"]))
    # never clip: squeezes toward -0.5 dB, with a hard ceiling at 0 dBFS
    # (measured — a few fast peaks do reach 0, none go past it)
    post.append(pb.Limiter(threshold_db=-0.5, release_ms=60.0))
    return pb.Pedalboard(post)(np.ascontiguousarray(y, dtype=np.float32), sr)
