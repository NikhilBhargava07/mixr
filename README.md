# mixr

> **🚧 In active development.** Usable, but rough around the edges and changing often.

A free, browser-based DAW built for the **DDN** (Desi Dance Network) fusion
circuit — plus the analysis work behind it, studying how competition DJs
actually build their mixes.

It exists because mixing software costs ~$400 and most of us are college kids.

---

## Why this is two projects in one

**The editor** (`app/`) — a non-destructive multi-track audio editor that runs
in a browser. Python/FastAPI backend, vanilla JS frontend, no build step.

**The analysis** (`analysis/`, `engine/`) — measuring real
competition mixes to work out the musical grammar of each dance style: tempo
conventions, meter, where hits land relative to the downbeat. The measurement
code is here; the data it produces about other teams' sets is kept private.

The point of the pairing: the editor is eventually meant to use what the
analysis learned to *suggest* arrangements, not just host them.

## What works today

| | |
|---|---|
| **Arrange** | multi-track timeline, drag to move, trim clip edges, split at playhead, snap to real bar lines |
| **Shape** | per-clip gain and fades with drag handles, track volume, pan, mute/solo |
| **Warp** | warp maps (pins from source time to timeline time) rendered by Rubber Band; Beats mode keeps hits within ~4 ms of the pins; only the stretch a clip uses is rendered, so edits land in ~1.5 s instead of ~17 s |
| **Beat-match** | match a clip to the project tempo, or pin every detected bar to the grid (95% of bars land within 20 ms); drag, add and delete warp pins by hand |
| **Key** | detect a clip's key and transpose it into the project's, by the shortest path |
| **Tempo** | change the project tempo and every warped clip follows, keeping its place in the bar |
| **Warp modes** | Crisp, Tones, Slice (Ableton-style: every drum hit unstretched, full punch, hits within 1.6 ms) and Re-Pitch |
| **Sound** | a per-track channel strip — low boost, punch (transient), drive, compress, steep high/low-pass, output — with presets |
| **Stems** | 4-way source separation (Demucs) from the clip menu |
| **Session** | undo/redo (batched: pasting six clips is one step), save/open projects, autosave restored on restart |
| **Transport** | loop region (gapless), metronome, count-in, markers |
| **Bouncing** | freeze/unfreeze a track, consolidate clips, reverse, normalize |
| **Editing** | multi-select, group drag, copy/cut/paste at the playhead, duplicate, nudge by a bar |
| **Export** | render to WAV, reporting the peak level and any clipping |
| **Metering** | peak meters per track and on the master, with peak-hold and clip warnings; a master fader with "fit to −1 dBFS" |

## What's missing

Reverb/delay, automation lanes, crossfades, loop regions, track
reordering, and hosting. The AI-assisted arranging that
motivated the whole thing hasn't been started.

## Design notes

A few decisions that shaped everything else:

- **A clip is a window, not audio.** `(source, file, start, offset, length)`.
  Trimming changes two numbers and never touches a file, which is what makes
  undo cheap and editing safe.
- **Seconds everywhere**, never samples or bars — seconds survive tempo changes.
- **The server owns the project.** Every endpoint returns the whole project, so
  the browser can't drift out of sync with it.
- **Warp is a map, not a number.** A clip's warp is a list of `[source, dest]`
  pins; a plain stretch is just two pins. The maths is pure and tested
  (`app/core/warp.py`, `tests/`), and warp accuracy is *measured* on a click
  track rather than assumed (`tests/warp_accuracy.py`).
- **Preview must equal export.** Warped clips play the same cached window the
  renderer reads — verified in-browser as bit-identical (max sample difference 0), and the offline renderer mirrors the Web Audio graph
  node for node — including copying `StereoPannerNode`'s pan law exactly.

## Running it

Needs Python 3.11, [Rubber Band](https://breakfastquay.com/rubberband/)
(`brew install rubberband`), and macOS (`afconvert` is used for format
conversion).

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.server:app --reload --port 8765
```

Then open <http://localhost:8765>. See [RUN.md](RUN.md) for the controls.

## A note on the audio

No audio is in this repo, deliberately. The analysis was run on competition
mixes that belong to the teams and DJs who made them; only derived measurements
(tempo, onset timing, plots) are committed. Reference material extracted during
analysis is treated as *spec, not material* — it informs what a style sounds
like, it doesn't get reused in a mix.

---

*Built by [@NikhilBhargava07](https://github.com/NikhilBhargava07) — dancer with
Wisconsin Surma, UW–Madison.*
