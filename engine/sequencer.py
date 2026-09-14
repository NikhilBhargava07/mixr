"""Grid sequencer + mixdown for mixr.

Places synthesized (or sampled) audio on a musical grid at a given BPM, mixes
tracks with gain/pan, and exports. Patterns are written as strings so they read
like a drum machine:

    "X..x|X...|X..x|X..."     one bar, 4 beats, 4 slots per beat
    X = accent, x = normal, o = ghost, . = rest

`slots_per_beat` controls resolution: 4 = 16th notes, 3 = triplets/compound.
That switch is how we A/B a straight bed against a compound one.
"""
import numpy as np
import soundfile as sf

SR = 44100
LEVELS = {"X": 1.0, "x": 0.68, "o": 0.34}


class Track:
    def __init__(self, name, gain=1.0, pan=0.0):
        self.name, self.gain, self.pan = name, gain, pan
        self.events = []          # (time_sec, audio)

    def add(self, t, audio, gain=1.0):
        self.events.append((t, audio * gain))
        return self


class Sequencer:
    def __init__(self, bpm, bars, beats_per_bar=4, slots_per_beat=4, swing=0.5):
        """swing: where the off-beat eighth lands within the beat.
        0.50 = dead straight, 0.58-0.62 = the 'bounce' pocket,
        0.667 = full triplet/shuffle. Warps the whole beat smoothly so
        16th-note ghosts move with the eighths instead of fighting them."""
        self.bpm = bpm
        self.spb = 60.0 / bpm                       # seconds per beat
        self.bars, self.bpbar, self.slots = bars, beats_per_bar, slots_per_beat
        self.swing = swing
        self.tracks = {}

    def _warp(self, p):
        """Map straight within-beat position p in [0,1) to swung position."""
        sw = self.swing
        if sw == 0.5:
            return p
        return p * 2 * sw if p < 0.5 else sw + (p - 0.5) * 2 * (1 - sw)

    @property
    def bar_dur(self):
        return self.spb * self.bpbar

    @property
    def total(self):
        return self.bar_dur * self.bars

    def track(self, name, gain=1.0, pan=0.0):
        if name not in self.tracks:
            self.tracks[name] = Track(name, gain, pan)
        return self.tracks[name]

    def slot_time(self, bar, slot):
        """slot index within the bar, at self.slots resolution, swing applied."""
        beat, sub = divmod(slot, self.slots)
        p = self._warp(sub / self.slots)
        return bar * self.bar_dur + (beat + p) * self.spb

    def pattern(self, track_name, pattern, voice, bars=None, gain=1.0,
                humanize=0.004, velocity_jitter=0.06, seed=0):
        """Apply a pattern string across bars.

        `voice` is either audio (ndarray) or a callable returning audio, so a
        voice can vary per hit (different seed / tone).
        """
        rng = np.random.default_rng(seed)
        pat = pattern.replace("|", "")
        tr = self.track(track_name)
        target = range(self.bars) if bars is None else bars
        for bar in target:
            for i, ch in enumerate(pat):
                if ch not in LEVELS:
                    continue
                lvl = LEVELS[ch] * gain
                lvl *= 1.0 + rng.uniform(-velocity_jitter, velocity_jitter)
                t = self.slot_time(bar, i) + rng.uniform(-humanize, humanize)
                aud = voice() if callable(voice) else voice
                tr.add(max(0.0, t), aud, lvl)
        return self

    def place(self, track_name, t, audio, gain=1.0):
        self.track(track_name).add(t, audio, gain)
        return self

    def render(self, tail=1.5):
        n = int((self.total + tail) * SR)
        out = np.zeros((2, n), dtype=np.float32)
        for tr in self.tracks.values():
            buf = np.zeros(n, dtype=np.float32)
            for t, aud in tr.events:
                s = int(t * SR)
                e = min(n, s + len(aud))
                if s < n:
                    buf[s:e] += aud[: e - s]
            l = np.sqrt(0.5 * (1 - tr.pan)); r = np.sqrt(0.5 * (1 + tr.pan))
            out[0] += buf * tr.gain * l
            out[1] += buf * tr.gain * r
        return out


def soft_clip(x, drive=1.0):
    return np.tanh(x * drive).astype(np.float32)


def normalize(x, peak=0.89):
    m = np.max(np.abs(x)) + 1e-9
    return (x * (peak / m)).astype(np.float32)


def write(path, stereo, sr=SR, normalize_to=0.89, drive=1.05):
    y = soft_clip(stereo, drive)
    y = normalize(y, normalize_to)
    sf.write(path, y.T, sr)
    return path


def swing_warp(audio, bpm, swing, sr=SR, downbeat=0.0):
    """Swing-quantize audio: move straight off-beat eighths onto the swung grid.

    A straight vocal over a swung bed always sounds EARLY, because its '&'
    lands at 50% of the beat while the bed's lands at `swing`. This resamples
    each beat piecewise: the first eighth is stretched to occupy `swing` of the
    beat, the second compressed into the remainder.

    audio: (2, n) or (n,)  ->  same shape, swung.
    """
    import numpy as np
    if swing == 0.5:
        return audio
    mono = audio.ndim == 1
    x = audio[None, :] if mono else audio
    spb = 60.0 / bpm
    n = x.shape[1]
    out = np.zeros_like(x)
    half = spb / 2.0
    t = downbeat
    while t < n / sr:
        for k, (src_dur, dst_frac) in enumerate([(half, swing), (half, 1 - swing)]):
            s0 = t + k * half
            s1 = s0 + src_dur
            d0 = t + (0.0 if k == 0 else swing * spb)
            d1 = d0 + dst_frac * spb
            i0, i1 = int(s0 * sr), int(s1 * sr)
            j0, j1 = int(d0 * sr), int(d1 * sr)
            if i0 >= n or j0 >= n:
                continue
            i1, j1 = min(i1, n), min(j1, n)
            seg = x[:, i0:i1]
            if seg.shape[1] < 2 or j1 - j0 < 2:
                continue
            # linear resample the segment into its new slot
            src_idx = np.linspace(0, seg.shape[1] - 1, j1 - j0)
            for c in range(x.shape[0]):
                out[c, j0:j1] += np.interp(src_idx, np.arange(seg.shape[1]), seg[c])
        t += spb
    return out[0] if mono else out
