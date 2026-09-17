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
| **Warp** | warp maps (pins from source time to timeline time) rendered by Rubber Band; Beats mode keeps hits within ~4 ms of the grid; preview is sample-for-sample identical to the export |
| **Stems** | 4-way source separation (Demucs) from the clip menu |
| **Session** | undo/redo, save/open projects, autosave |
| **Export** | render to WAV |

## What's missing

Effects (EQ/filter/reverb), automation lanes, copy/paste, crossfades, loop
regions, track reordering, and hosting. The AI-assisted arranging that
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
- **Preview must equal export.** Warped clips play the same cached stretched
  file the renderer reads, and the offline renderer mirrors the Web Audio graph
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
