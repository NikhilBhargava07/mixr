# Running mixr

```bash
cd ~/random_projects/mixr
.venv/bin/uvicorn app.server:app --reload --port 8765
```

Then open **http://localhost:8765** in any browser.

Leave that terminal running — it's the backend. `--reload` means it restarts
itself whenever you edit a Python file. For frontend files (`app/static/*`)
just refresh the page.

## What you can do right now
- click any file in the left panel → it becomes a track
- drag clips sideways to move them (snaps to bars)
- space = play / pause, and clicking the ruler scrubs
- click **M** / **S** on a track to mute / solo
- drag the blue bar under M/S to change track volume
- type a tempo in the **BPM** box — warped clips follow it, keeping their
  place in the bar (the clip label shows the resulting speed, e.g. 80.0%)
- each track header has a **level meter**; the bar in the toolbar is the master
  (click it to set the master fader, or let mixr fit the mix to −1 dBFS)
- **+ / −** zoom the timeline
- scroll sideways with a trackpad swipe, **shift + scroll wheel**, or the scrollbar under the tracks
- **Home** jumps back to the start; **End** to the end
- **loop / click / count-in** toggles sit in the toolbar; shift-drag the ruler
  to set the loop, or right-click the ruler for markers and loop presets
- drag a track's name up or down to reorder it
- track menu: **Freeze** bounces a track to one clip (and back again)
- clip menu: **Normalize**, **Reverse**, **Consolidate**
- select a clip and press Delete to remove it
- shift-click to select several clips; ⌘A selects all, Esc clears
- ⌘C / ⌘X / ⌘V copy, cut and paste at the playhead; ⌘D duplicates after the selection
- ← → nudge selected clips by a bar (hold alt for 10 ms)
- right-click a clip for warping: **match project tempo**, **warp every bar to
  grid**, **match project key**, transpose, and the Beats/Tones warp mode
- double-click a clip's bottom strip to drop a warp pin, drag a pin to warp the
  audio around it, alt-click a pin to remove it

Warped audio is cached under `app/_cache/`, which holds nothing but rebuildable
files — clearing it never touches your projects (`app/_projects/`), stems
(`app/_stems/`) or exported mixes (`mixes/`). It caps itself at 2 GB, and
**Open ▸ Free up disk** clears it by hand.

## Where things live
```
app/server.py          the API — thin wrappers, no logic
app/core/project.py    the data model (Project / Track / Clip)
app/core/audio.py      analysis wrappers (tempo, key, waveform, downbeats)
app/core/stems.py      Demucs, run in a background thread
app/static/app.js      the whole UI
app/static/style.css   styling
```
