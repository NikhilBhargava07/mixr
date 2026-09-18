"""Channel strip. Run: .venv/bin/python -m tests.test_fx"""
import numpy as np
from app.core import fx

SR = 44100


def kick(n_hits=8, every=0.5):
    """Synthetic kick: 55 Hz sine with a fast attack and 120 ms decay."""
    t = np.arange(int(n_hits * every * SR)) / SR
    y = np.zeros_like(t)
    k = np.arange(int(0.3 * SR)) / SR
    hit = np.sin(2 * np.pi * 55 * k) * np.exp(-k / 0.12) * np.minimum(1, k / 0.002)
    for i in range(n_hits):
        s = int(i * every * SR)
        y[s:s + len(hit)] += hit[: len(y) - s]
    return np.stack([y, y]).astype(np.float32) * 0.5


def peak_over_tail(y):
    e = np.abs(y[0])
    return np.mean([e[int((i*.5)*SR):int((i*.5+.03)*SR)].max() /
                    (e[int((i*.5+.08)*SR):int((i*.5+.3)*SR)].mean() + 1e-9) for i in range(8)])


def test_normalize_fills_and_clamps():
    p = fx.normalize({"low_db": 99, "punch": "x", "comp": -1})
    assert p["low_db"] == 12.0 and p["punch"] == 0.0 and p["comp"] == 0.0
    assert set(p) == set(fx.STRIP)


def test_clean_is_no_strip():
    assert fx.params_of([{"kind": "strip", "params": fx.PRESETS["Clean"]}]) is None
    assert fx.params_of([]) is None
    assert fx.params_of([{"kind": "strip", "enabled": False, "params": fx.PRESETS["Punch"]}]) is None


def test_punch_makes_hits_stand_out():
    y = kick()
    before = peak_over_tail(y)
    after = peak_over_tail(fx.transient(y, SR, 1.0))
    softer = peak_over_tail(fx.transient(y, SR, -1.0))
    assert after > before * 1.15, (before, after)
    assert softer < before, (before, softer)


def test_drive_has_no_jump_at_zero():
    y = kick()
    assert np.array_equal(fx.drive(y, 0.0), y)
    small = fx.drive(y, 0.1)
    assert np.abs(small - y).max() < 0.01          # a hair of drive is a hair of change


def test_strip_never_clips_and_is_deterministic():
    y = kick() * 1.8                               # deliberately too hot
    p = fx.normalize({**fx.PRESETS["Punch"], "gain_db": 12})
    a, b = fx.apply(y, SR, p), fx.apply(y, SR, p)
    assert np.abs(a).max() <= 1.0                  # no sample past 0 dBFS
    assert np.array_equal(a, b)                    # same input, same bytes: caching is safe


def test_kick_only_removes_the_highs():
    t = np.arange(SR) / SR
    y = np.stack([np.sin(2*np.pi*3000*t)] * 2).astype(np.float32) * 0.5
    out = fx.apply(y, SR, fx.normalize(fx.PRESETS["Kick only"]))
    assert np.abs(out).max() < 0.05




def test_steep_lowpass_keeps_the_kick_on_time():
    """Delay compensation: the kick's attack must not move."""
    y = kick()
    out = fx.steep(y, SR, "lowpass", 160.0)
    def attack(z):
        e = np.abs(z[0, :int(0.1 * SR)]); return int(np.argmax(e >= 0.5 * e.max()))
    shift_ms = (attack(out) - attack(y)) / SR * 1000
    assert abs(shift_ms) < 1.5, shift_ms


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} passed")
