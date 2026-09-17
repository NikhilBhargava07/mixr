"""Does warped audio put hits where the warp map says? Measured, not assumed.

Builds a click track with known click times, warps it through the real
audio.warped() pipeline, detects where the clicks came out, and compares with
where warp.src_to_dst() says they should be.

    .venv/bin/python -m tests.warp_accuracy

The onset detector has its own bias (~+3 ms on these clicks), so each click's
error on the ORIGINAL file is subtracted first: what's left is what warping
added. Passing bar: beats mode within 5 ms of that. Tones mode is reported,
not enforced — it's known to pull hits ~16 ms early.
"""
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from app.core import audio, warp

SR = 44100
TOL_MS = 5.0


def click_track(path: Path, n=16, every=0.5, first=0.25, dur=8.5):
    y = np.zeros(int(dur * SR), dtype=np.float32)
    k = int(0.01 * SR)
    click = (np.sin(2 * np.pi * 1500 * np.arange(k) / SR) * np.hanning(k)).astype(np.float32)
    times = first + every * np.arange(n)
    for t in times:
        s = int(t * SR)
        y[s:s + k] += click
    sf.write(path, np.stack([y, y]).T, SR)
    return times


def errors_ms(wav: Path, expected):
    y, _ = sf.read(wav)
    on = librosa.onset.onset_detect(y=y.mean(axis=1).astype(np.float32), sr=SR,
                                    units="time", hop_length=64)
    got = np.array([on[np.argmin(np.abs(on - e))] for e in expected])
    return (got - expected) * 1000


def main():
    cases = {
        "uniform 1.075 (slower)": warp.uniform(1.075),
        "uniform 0.9 (faster)":   warp.uniform(0.9),
        "piecewise 1.25 then 1":  warp.normalize([[0, 0], [4, 5], [8.5, 9.5]]),
        "drift fix (4 pins)":     warp.normalize([[0, 0], [2, 2.1], [5, 5.0], [8, 8.4]]),
    }
    failed = 0
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "clicks.wav"
        times = click_track(src)
        baseline = errors_ms(src, times)          # the detector's own error, per click
        for mode in warp.MODES:
            for name, pins in cases.items():
                out = audio.warped(src, pins, 0.0, mode)
                exp = np.array([warp.src_to_dst(pins, t) for t in times])
                raw = errors_ms(out, exp)
                e = raw - baseline
                length_ok = abs(sf.info(str(out)).duration
                                - warp.src_to_dst(pins, sf.info(str(src)).duration)) < 0.01
                ok = length_ok and (mode != "beats" or np.abs(e).max() <= TOL_MS)
                failed += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {mode:5s}  {name:24s} "
                      f"mean {e.mean():+6.1f} ms   worst {np.abs(e).max():5.1f} ms"
                      f"   (raw worst {np.abs(raw).max():4.1f})"
                      f"{'' if length_ok else '   LENGTH WRONG'}")
    print("all good" if not failed else f"{failed} failed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
