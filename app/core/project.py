"""The mixr project data model.

This is the most important file in the app. Every feature — editing, playback,
effects, export, undo — reads and writes these objects, so the shape here
decides how easy everything else is.

Three ideas, borrowed from how every DAW works:

  Project  the session: tempo, sample rate, a list of tracks
  Track    a lane: name, volume, pan, mute/solo, effects, and a list of clips
  Clip     a REFERENCE to a region of an audio file placed on the timeline

The key design decision is that a Clip is NON-DESTRUCTIVE. It does not contain
audio. It says "play file X, from `offset` seconds in, for `length` seconds,
starting at `start` on the timeline." Trimming a clip changes two numbers; it
never touches the file. That is what makes undo cheap and editing safe.

Times are in SECONDS everywhere (not samples, not bars). Seconds survive tempo
changes and are what both the audio engine and the UI want.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Clip:
    """A region of an audio file placed on the timeline."""
    id: str = field(default_factory=_id)
    name: str = ""
    source: str = ""          # which folder ("mixes", "library", "stems", ...)
    file: str = ""            # filename within that folder
    start: float = 0.0        # where it sits on the timeline, seconds
    offset: float = 0.0       # how far into the source file the clip begins
    length: float = 0.0       # how long it plays, seconds
    gain: float = 1.0         # linear, 1.0 = unity
    fade_in: float = 0.01     # seconds — a tiny default fade avoids clicks
    fade_out: float = 0.01
    # warping: if set, the clip is time-stretched by this ratio on render
    stretch: float = 1.0      # 1.0 = original speed; 0.95 = 5% slower
    pitch: float = 0.0        # semitones

    @property
    def end(self) -> float:
        return self.start + self.length


@dataclass
class Effect:
    """One node in a track's effect chain. `kind` maps to a pedalboard class,
    or "plugin" for an external VST3/AU loaded by path."""
    id: str = field(default_factory=_id)
    kind: str = "Gain"
    enabled: bool = True
    params: dict = field(default_factory=dict)


@dataclass
class Track:
    id: str = field(default_factory=_id)
    name: str = "Track"
    volume: float = 1.0       # linear
    pan: float = 0.0          # -1 left .. +1 right
    mute: bool = False
    solo: bool = False
    color: str = "#4da3ff"
    clips: list[Clip] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)

    def add_clip(self, **kw) -> Clip:
        c = Clip(**kw)
        self.clips.append(c)
        self.clips.sort(key=lambda x: x.start)
        return c

    def clip(self, cid: str) -> Optional[Clip]:
        return next((c for c in self.clips if c.id == cid), None)


@dataclass
class Project:
    id: str = field(default_factory=_id)
    name: str = "Untitled"
    bpm: float = 100.0
    # The grid. If downbeats is populated we use it verbatim (per-bar, so it
    # cannot drift); otherwise the UI falls back to a fixed bpm grid.
    downbeats: list[float] = field(default_factory=list)
    sample_rate: int = 44100
    tracks: list[Track] = field(default_factory=list)

    # ---------------------------------------------------------------- tracks
    def add_track(self, name="Track", color="#4da3ff") -> Track:
        t = Track(name=name or f"Track {len(self.tracks) + 1}", color=color)
        self.tracks.append(t)
        return t

    def track(self, tid: str) -> Optional[Track]:
        return next((t for t in self.tracks if t.id == tid), None)

    def remove_track(self, tid: str) -> bool:
        n = len(self.tracks)
        self.tracks = [t for t in self.tracks if t.id != tid]
        return len(self.tracks) != n

    # ---------------------------------------------------------------- timing
    @property
    def duration(self) -> float:
        return max((c.end for t in self.tracks for c in t.clips), default=0.0)

    def audible_tracks(self) -> list[Track]:
        """Solo beats mute — standard DAW behaviour."""
        soloed = [t for t in self.tracks if t.solo]
        pool = soloed if soloed else self.tracks
        return [t for t in pool if not t.mute]

    # ---------------------------------------------------------------- io
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls(id=d.get("id", _id()), name=d.get("name", "Untitled"),
                bpm=d.get("bpm", 100.0), downbeats=d.get("downbeats", []),
                sample_rate=d.get("sample_rate", 44100))
        for td in d.get("tracks", []):
            t = Track(**{k: v for k, v in td.items() if k not in ("clips", "effects")})
            t.clips = [Clip(**cd) for cd in td.get("clips", [])]
            t.effects = [Effect(**ed) for ed in td.get("effects", [])]
            p.tracks.append(t)
        return p

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "Project":
        return cls.from_dict(json.loads(path.read_text()))
