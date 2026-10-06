# mixr — what's left

Ordered by what unlocks the most. "Measured" notes are from tests in `tests/`
or the session that found them; anything marked ⚠️ is a known defect, not a
wish.

---

## 1. Capability gaps (things Ableton has that we don't)

### Automation — the biggest one
Volume, filter and pan moves over time. Without it there are no filter sweeps
into a drop and no volume rides under a vocal, which is most of what makes a
transition sound produced.
- model: breakpoints `[(time, value)]` per track parameter
- render: numpy interpolation; preview: `setValueCurveAtTime`
- the catch: preview == export means implementing it twice and proving they
  match, the way fades were done

### Crossfades between overlapping clips
Equal-power fade where two clips overlap on a track. Extends the existing fade
code in both paths.

### Track groups
12 tracks is already unwieldy; the stems make it worse. Fold a parent track's
children, sum through a group bus.

### Sends / returns + sidechain
One reverb shared by several tracks, and ducking the 808 under the kick.
Sidechain is the one that matters for this music — it's the direct fix for the
808-vs-dhol collision measured on Mmhmm.

### Step sequencer + drum rack
The conceptual hole: mixr can only arrange audio that already exists. A dhol
bed has to be programmed. `engine/instruments.py` already synthesises dagga and
tilli; wire a 16-step grid to it and the beds get built inside mixr instead of
in scripts.

### Smaller
- time selection (select a range across tracks; insert/delete time)
- take lanes / comping
- clip envelopes (per-clip automation)
- export: stems as separate files, export the loop range only, mp3
- a visible scrollbar for the sidebar (it still uses the invisible system one)

---

## 2. Known defects and rough edges

- ⚠️ **Consolidate changes dynamics.** With a compressor on the track, bouncing
  clips together shifts the sound at clip boundaries, because the compressor
  then sees one continuous clip. Sample-identical without a strip. Matches
  Ableton's behaviour, but it should warn before doing it.
- ⚠️ **43 samples of every render differ from preview** (~-70 dB, inside one
  clip's fade). Web Audio's ramp and numpy's round differently. Harmless,
  documented, unfixed.
- ⚠️ **Old caches orphan when a file moves.** Cache keys include the resolved
  path, so moving or renaming a file silently abandons its stems and warps.
  Mmhmm's stems had to be rebuilt once already. A content hash would fix it.
- ⚠️ **`app/_cache` reached 1.9 GB.** Self-limits at 2 GB now, but warp renders
  are ~8 MB a window and stems are never pruned.
- Reloading the page starts a fresh project; the autosave has to be restored by
  hand from the Open menu.
- Exports always write to `mixes/` AND trigger a browser download — two copies
  every time.

---

## 3. Before anyone else can use it

Required if teammates ever get their own mixr (the original point of the
project):
- **authentication** — every endpoint is open today, including upload and
  Demucs
- **per-user state** — `STATE["current"]` is one global project
- **a job queue** — Demucs and exports currently run inside a web request
- storage (S3), and the rights question about whose audio sits on a shared box

See `deploy/README.md`. Running it on your own Mac as a login agent is already
done and is the right answer until teammates need it.

---

## 4. The AI layer

Needs no download and no labels:
- **groove extract / apply** — measure where onsets fall between beats, apply
  it as warp pins. Directly useful: stamp chaal's lilt onto straight material.
  Also a better meter test than the tempogram one, which was shown to be
  partly reading its own bin grid.
- **structure detection** — self-similarity to find where sections change.

Needs labels (the blocker, not the models):
- **style classifier.** `labels.json` now has time-stamped segments from one
  mix. Twenty mixes annotated that way makes this trainable with frozen
  embeddings + logistic regression, validated leave-one-mix-out.
- **"find me a section like this"** — embeddings, no labels needed. The one
  case where a ~300 MB model download earns its keep.

Not realistic on this data: generating dhol patterns with a trained model. A
rule-based generator driven by the measured style grammar will beat it and can
be debugged.

---

## 5. Open questions only the dancer can answer

1. The 2027 chaal section — counted at ~99 (like the khunde before it) or
   about half that? **The compound verdict flips on this.**
2. Virasat's 2024 jhummar reads compound while four other jhummars read
   straight. Does it feel bouncier?
3. Classical 2027: what pulse do you count? 89.83 or 136.36?
4. The three `feel-demos` — which pickup placement sounds like chaal?
5. The three `chaal test` renders — does the song want to be stretched to 99,
   or left alone with the bed on top?
