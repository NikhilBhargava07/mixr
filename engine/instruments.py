"""Synthesized instruments for mixr.

Built from scratch (no samples) so we can generate percussion and melodic
material freely. Designed around the dhol's actual two-register construction:
dagga (heavy bass head, thick stick) and tilli (treble head, thin stick).

Everything returns float32 mono at SR unless noted.
"""
import numpy as np

SR = 44100


def _env(n, attack=0.002, decay=0.15, curve=3.0):
    """Percussive envelope: fast attack, exponential decay."""
    a = int(attack * SR)
    e = np.ones(n, dtype=np.float32)
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    d = np.exp(-curve * np.linspace(0, 1, max(1, n - a)) * (0.15 / max(decay, 1e-4)))
    e[a:] = d[: n - a]
    return e


def _noise(n, seed=None):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n).astype(np.float32)


def _lowpass(x, cutoff, sr=SR):
    """One-pole lowpass."""
    a = np.exp(-2 * np.pi * cutoff / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _highpass(x, cutoff, sr=SR):
    return x - _lowpass(x, cutoff, sr)


def _bandpass(x, lo, hi, sr=SR):
    return _lowpass(_highpass(x, lo, sr), hi, sr)


# ---------------------------------------------------------------- dhol

def dagga(dur=0.45, f0=95.0, f1=52.0, amp=1.0, click=0.35, seed=0):
    """Dhol bass head. Struck with the thick stick: deep boom with a pitch
    drop and a woody attack. This is the register the dancer feels in the chest."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # exponential pitch sweep - what gives a struck membrane its 'boom'
    f = f1 + (f0 - f1) * np.exp(-14 * t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase).astype(np.float32)
    body += 0.25 * np.sin(2 * phase).astype(np.float32)      # slight harmonic
    body *= _env(n, 0.001, 0.30, curve=2.2)
    # stick contact noise
    atk = _noise(n, seed) * _env(n, 0.0005, 0.012, curve=9.0)
    atk = _bandpass(atk, 300, 2600)
    return (body + click * atk).astype(np.float32) * amp


def tilli(dur=0.16, amp=1.0, tone=2400.0, seed=1):
    """Dhol treble head. Thin stick: bright, sharp, cutting crack."""
    n = int(dur * SR)
    nz = _noise(n, seed)
    crack = _bandpass(nz, 1100, 7000) * _env(n, 0.0004, 0.045, curve=7.0)
    # a little pitched ring so it isn't pure noise
    t = np.arange(n) / SR
    ring = np.sin(2 * np.pi * tone * t).astype(np.float32) * _env(n, 0.0004, 0.03, curve=9.0)
    return (crack + 0.3 * ring).astype(np.float32) * amp


def dhol_ghost(dur=0.09, amp=0.35, seed=2):
    """Light unaccented tilli tap - the filler strokes that make a bed feel alive."""
    return tilli(dur=dur, amp=amp, tone=3200, seed=seed) * 0.6


# ---------------------------------------------------------------- kit

def kick(dur=0.5, f0=120.0, f1=42.0, amp=1.0, punch=0.5):
    """Western kick / 808-ish. The element the dancer annotation says is
    non-negotiable in DDN chaal."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-22 * t)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    body *= _env(n, 0.0008, 0.34, curve=1.8)
    click = _noise(n, 7) * _env(n, 0.0003, 0.006, curve=12.0)
    click = _highpass(click, 1200)
    return (body + punch * 0.25 * click).astype(np.float32) * amp


def snare(dur=0.25, amp=1.0, seed=3):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * 185 * t) + np.sin(2 * np.pi * 278 * t)).astype(np.float32)
    tone *= _env(n, 0.0006, 0.05, curve=6.0)
    rattle = _bandpass(_noise(n, seed), 900, 8000) * _env(n, 0.0006, 0.10, curve=5.0)
    return (0.45 * tone + rattle).astype(np.float32) * amp


def hat(dur=0.07, amp=0.5, seed=4, open_=False):
    n = int(dur * (3 if open_ else 1) * SR)
    h = _highpass(_noise(n, seed), 6500) * _env(n, 0.0002, 0.02 if not open_ else 0.12, curve=10.0)
    return h.astype(np.float32) * amp


def clap(dur=0.3, amp=0.8, seed=5):
    """Layered short bursts - the classic hand-clap stack."""
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    for i, off in enumerate([0.0, 0.011, 0.021, 0.031]):
        s = int(off * SR)
        seg = _bandpass(_noise(n - s, seed + i), 1200, 5200) * _env(n - s, 0.0003, 0.03, curve=8.0)
        out[s:] += seg * (1.0 if i == 3 else 0.55)
    return out * amp


# ---------------------------------------------------------------- melodic

def karplus_strong(freq, dur, amp=1.0, damping=0.996, seed=9):
    """Plucked string physical model. Used for tumbi-style lines - the
    single-string, high-pitched, repetitive hook timbre of bhangra."""
    n = int(dur * SR)
    N = max(2, int(SR / freq))
    rng = np.random.default_rng(seed)
    buf = rng.standard_normal(N).astype(np.float32)
    out = np.empty(n, dtype=np.float32)
    idx = 0
    for i in range(n):
        out[i] = buf[idx]
        nxt = (idx + 1) % N
        buf[idx] = damping * 0.5 * (buf[idx] + buf[nxt])
        idx = nxt
    out *= _env(n, 0.001, dur * 0.9, curve=1.6)
    return out * amp


def tumbi(freq, dur=0.28, amp=0.7, seed=9):
    """Bright, nasal, cutting - tumbi sits high and repetitive."""
    s = karplus_strong(freq, dur, amp=amp, damping=0.992, seed=seed)
    return _highpass(s, 350).astype(np.float32)


def sub_bass(freq, dur, amp=0.8, glide_from=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = np.full(n, freq, dtype=np.float32)
    if glide_from:
        f = glide_from + (freq - glide_from) * np.clip(t / 0.08, 0, 1)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    y += 0.12 * np.sin(2 * np.pi * 2 * np.cumsum(f) / SR).astype(np.float32)
    a = int(0.006 * SR); r = int(0.03 * SR)
    e = np.ones(n, dtype=np.float32)
    e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r)
    return y * e * amp


def drone(freq, dur, amp=0.25):
    """Algoza-style sustained drone - traditional bhangra melody sits over a
    drone rather than moving chord changes."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for k, g in [(1, 1.0), (2, 0.28), (3, 0.14), (4, 0.07)]:
        y += g * np.sin(2 * np.pi * freq * k * t + k).astype(np.float32)
    # breathy flute noise
    y += 0.05 * _bandpass(_noise(n, 11), freq * 2, freq * 7)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 4.5 * t)
    y *= vib
    a = int(0.15 * SR); r = int(0.25 * SR)
    e = np.ones(n, dtype=np.float32)
    e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r)
    return (y / 1.5) * e * amp


def riser(dur=2.0, amp=0.5, f_start=200, f_end=4000):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f_start * (f_end / f_start) ** (t / dur)
    y = _bandpass(_noise(n, 13), 200, 9000)
    # sweep a resonant peak upward
    y = y * (0.3 + 0.7 * (t / dur))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32) * 0.25
    env = (t / dur) ** 1.5
    return ((y + tone) * env).astype(np.float32) * amp


def impact(dur=1.6, amp=1.0):
    """Big downbeat hit - the 'pose' moment."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (55 * np.exp(-3 * t) + 32) * t).astype(np.float32)
    boom *= np.exp(-3.2 * t)
    nz = _bandpass(_noise(n, 17), 200, 6000) * np.exp(-9 * t)
    return ((boom + 0.35 * nz)).astype(np.float32) * amp


NOTE = {"C":261.63,"C#":277.18,"D":293.66,"D#":311.13,"E":329.63,"F":349.23,
        "F#":369.99,"G":392.00,"G#":415.30,"A":440.00,"A#":466.16,"B":493.88}


def note_hz(name, octave=4):
    return NOTE[name] * (2 ** (octave - 4))


# ------------------------------------------------- light / "happier" voices
# Dancer note: deep sounds should be FELT not HEARD; lighter sounds carry the
# bounce and land on the &'s and odd beats. These are the bounce vocabulary.

def shaker(dur=0.06, amp=0.4, seed=21, bright=9000):
    n = int(dur * SR)
    s = _highpass(_noise(n, seed), bright * 0.55)
    return (s * _env(n, 0.0006, 0.018, curve=9.0)).astype(np.float32) * amp


def rim(dur=0.09, amp=0.5, tone=1750.0, seed=22):
    """Woody rim/click - dry, light, cuts without weight."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = (np.sin(2 * np.pi * tone * t) + 0.5 * np.sin(2 * np.pi * tone * 1.6 * t))
    body = body.astype(np.float32) * _env(n, 0.0004, 0.012, curve=11.0)
    tick = _bandpass(_noise(n, seed), 2200, 7000) * _env(n, 0.0003, 0.008, curve=12.0)
    return (0.7 * body + 0.5 * tick).astype(np.float32) * amp


def light_clap(dur=0.16, amp=0.45, seed=23):
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    for i, off in enumerate([0.0, 0.008, 0.016]):
        s = int(off * SR)
        seg = _bandpass(_noise(n - s, seed + i), 1600, 6000) * _env(n - s, 0.0003, 0.022, curve=9.0)
        out[s:] += seg * (1.0 if i == 2 else 0.5)
    return out * amp


def bell_tick(freq=1400.0, dur=0.12, amp=0.3, seed=24):
    """Small bright metallic tick - chimta-ish sparkle on off-beats."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for k, g in [(1, 1.0), (2.76, 0.5), (5.4, 0.25)]:
        y += g * np.sin(2 * np.pi * freq * k * t).astype(np.float32)
    return (y * _env(n, 0.0004, 0.03, curve=8.0) / 1.75) * amp


def felt_sub(freq=48.0, dur=0.55, amp=0.5):
    """Deep weight with NO attack - felt, not heard. Drives without competing."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * t).astype(np.float32)
    a = int(0.035 * SR)                       # slow attack = no click
    e = np.exp(-3.0 * t).astype(np.float32)
    e[:a] *= np.linspace(0, 1, a)
    return _lowpass(y * e, 140) * amp


# ---------------------------------------------- v10: midrange body
# Measured 2026-08-08: real jhummar drum stems sit at L/M/H ~80/12/6 %, but my
# synthesized bed was 96.5/2.1/1.4 — almost pure sub with no body. Bounce lives
# in the 200-2000Hz shell resonance of a real drum, not in the sub. These
# voices add that body.

def dagga2(dur=0.42, f0=95.0, f1=52.0, amp=1.0, body=0.55, click=0.45,
           sub_level=1.0, seed=0):
    """Dagga with a resonant SHELL. The sub gives weight; the mid-band modes
    give the woody 'thok' that makes a struck drum read as a drum."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-14 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph).astype(np.float32) * _env(n, 0.001, 0.26, curve=2.4)
    # shell modes: a struck membrane has inharmonic partials well above f0
    shell = np.zeros(n, dtype=np.float32)
    for fm, g, dec in [(210.0, 1.0, 0.10), (330.0, 0.62, 0.075),
                       (505.0, 0.40, 0.055), (760.0, 0.24, 0.040)]:
        shell += g * np.sin(2 * np.pi * fm * t + fm).astype(np.float32) * \
                 _env(n, 0.0008, dec, curve=5.0)
    shell /= 2.26
    atk = _bandpass(_noise(n, seed), 400, 3000) * _env(n, 0.0005, 0.013, curve=9.0)
    return (sub_level * sub + body * shell + click * atk).astype(np.float32) * amp


def tilli2(dur=0.15, amp=1.0, amp_mid=0.7, seed=1):
    """Tilli with more mid weight — the treble head has body too, not just hiss."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    crack = _bandpass(_noise(n, seed), 900, 6500) * _env(n, 0.0004, 0.040, curve=7.0)
    mid = np.zeros(n, dtype=np.float32)
    for fm, g in [(430.0, 1.0), (690.0, 0.66), (1120.0, 0.44)]:
        mid += g * np.sin(2 * np.pi * fm * t + fm).astype(np.float32) * \
               _env(n, 0.0005, 0.055, curve=6.0)
    mid /= 2.1
    return (crack + amp_mid * mid).astype(np.float32) * amp


def thok(dur=0.13, amp=0.6, pitch=380.0, seed=31):
    """Rim/edge stroke — almost pure midrange. Pure articulation, no weight."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for fm, g in [(pitch, 1.0), (pitch * 1.58, 0.55), (pitch * 2.31, 0.3)]:
        y += g * np.sin(2 * np.pi * fm * t).astype(np.float32) * _env(n, 0.0005, 0.035, curve=7.0)
    y /= 1.85
    y += 0.35 * _bandpass(_noise(n, seed), 600, 4000) * _env(n, 0.0004, 0.012, curve=10.0)
    return y.astype(np.float32) * amp
