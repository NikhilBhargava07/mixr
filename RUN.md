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
- **+ / −** zoom the timeline
- select a clip and press Delete to remove it
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
