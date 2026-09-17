"""Warp maps: where each moment of a file lands in time.

This is the backbone of beat-matching. A warp map is a list of PINS, each
`[src, dst]` in seconds: "the moment `src` seconds into the original file plays
at `dst` seconds into the clip's warped audio". Between pins the audio is
stretched evenly; beyond the outermost pins it continues at the slope of the
nearest segment.

    no pins                 -> unwarped (dst == src)
    [[0, 0], [1, 1.075]]    -> the whole file 7.5% slower (a plain stretch)
    one pin per downbeat    -> every bar locked to a grid, even if the song drifts

Everything here is pure maths on lists of numbers — no audio, no files — so it
can be tested exactly (see tests/test_warp.py).

Invariants, enforced by normalize():
  * pins sorted, src and dst both strictly increasing (audio can't run backwards)
  * every segment's slope within SLOPE_RANGE (so Rubber Band stays sane)
  * dst(0) == 0: the warped file starts where the original does. Clip offsets
    are measured on the warped file, so this keeps offset 0 meaning "the top".
"""
from __future__ import annotations

import hashlib
import json

SLOPE_RANGE = (0.5, 2.0)     # half speed .. double speed, per segment
MIN_GAP = 0.001              # pins closer than 1 ms are treated as a mistake
MODES = ("beats", "tones")


class WarpError(ValueError):
    pass


def _pairs(pins):
    return [(float(a), float(b)) for a, b in pins]


def _slope(p, q):
    return (q[1] - p[1]) / (q[0] - p[0])


def src_to_dst(pins, t: float) -> float:
    """Where source time `t` lands on the warped timeline."""
    p = _pairs(pins)
    if not p:
        return t
    if len(p) == 1:                      # a lone pin is a shift, slope 1
        return t + (p[0][1] - p[0][0])
    # pick the segment containing t, or the nearest end segment to extrapolate
    i = 0
    while i < len(p) - 2 and t > p[i + 1][0]:
        i += 1
    a, b = p[i], p[i + 1]
    return a[1] + (t - a[0]) * _slope(a, b)


def dst_to_src(pins, t: float) -> float:
    """The inverse: which source moment plays at warped time `t`.
    Swapping each pin's coordinates inverts a monotonic piecewise-linear map."""
    return src_to_dst([(b, a) for a, b in _pairs(pins)], t)


def uniform(stretch: float):
    """A plain stretch as a map. stretch is a DURATION ratio (>1 = slower)."""
    if abs(stretch - 1.0) < 1e-9:
        return []
    return [[0.0, 0.0], [1.0, float(stretch)]]


def normalize(pins):
    """Validate and canonicalise. Raises WarpError with a readable reason."""
    p = sorted(_pairs(pins))
    if not p:
        return []
    if p[0][0] < 0:
        raise WarpError("pins can't point before the start of the file")
    for a, b in zip(p, p[1:]):
        if b[0] - a[0] < MIN_GAP or b[1] - a[1] < MIN_GAP:
            raise WarpError("pins must move forward in both source and warped time")
        s = _slope(a, b)
        if not SLOPE_RANGE[0] <= s <= SLOPE_RANGE[1]:
            raise WarpError(f"a segment's stretch of {s:.3f} is outside {SLOPE_RANGE}")
    if len(p) == 1:
        return []                        # a lone pin only shifts; dst(0)==0 cancels it
    d0 = src_to_dst(p, 0.0)
    out = [[round(a, 6), round(b - d0, 6)] for a, b in p]
    # a map that is the identity everywhere is no map at all
    if all(abs(a - b) < 1e-6 for a, b in out):
        return []
    return out


def is_uniform(pins) -> bool:
    return len(pins) <= 2


def overall_stretch(pins) -> float:
    """Average stretch across the pinned region (1.0 when unwarped)."""
    p = _pairs(pins)
    if len(p) < 2:
        return 1.0
    return _slope(p[0], p[-1])


def rescale_window(old, new, offset: float, length: float):
    """Keep a clip on the same MUSIC when its warp map changes.

    A clip's (offset, length) are measured on the warped file. Map the window's
    two edges back to the source with the old map, then forward with the new
    one. For a plain stretch this reduces to multiplying both by new/old.
    """
    s0 = dst_to_src(old, offset)
    s1 = dst_to_src(old, offset + length)
    d0 = src_to_dst(new, s0)
    return d0, src_to_dst(new, s1) - d0


def rubberband_map(pins, duration: float, sr: int):
    """Frame pairs for `rubberband --timemap`, plus the output duration.

    Rubber Band needs the whole file covered, so the map always includes the
    file's start and end, extrapolated from the pins."""
    end = src_to_dst(pins, duration)
    inner = [(a, b) for a, b in _pairs(pins) if 0 < a < duration]
    frames = [(0, 0)] + [(round(a * sr), round(b * sr)) for a, b in inner] \
             + [(round(duration * sr), round(end * sr))]
    return frames, end


def signature(pins, pitch: float, mode: str) -> str:
    """Stable id for one (map, pitch, mode) — the cache key for rendered audio."""
    blob = json.dumps([[round(a, 4), round(b, 4)] for a, b in _pairs(pins)]
                      + [round(float(pitch), 3), mode])
    return hashlib.sha1(blob.encode()).hexdigest()[:12]
