# PTTR × Jhummar — Mix Plan v1

**Seed:** Doja Cat — "Paint The Town Red" (2023)
**Target style:** jhummar
**Status:** design draft. Not yet rendered — no PTTR audio in the project, and
no render engine built yet (that's Phase 3).

---

## 1. The tempo math says your instinct was right

| | BPM |
|---|---|
| PTTR native | **100** |
| VC's jhummar (Surma) | 95.38 |
| V3NOM's jhummar (Izzat) | 93.52 |
| **corpus jhummar range** | **93.5 – 95.4** |

PTTR needs to come down **4.6–6.5%** to sit in the jhummar pocket. That is a
*small* stretch — well inside the range where modern time-stretching leaves no
audible artifacts on vocals, and it barely touches the groove's character.

**Recommendation: 95 BPM.** It matches VC's jhummar almost exactly (95.38),
which is our cleanest jhummar reference, and it's a 5.0% slowdown from 100 —
a round number that's easy to dial in.

Why this matters: tempo is the single most reliable style marker we measured
across the whole corpus (jhummar 93–95, bhangra-family ~99, kuthu 82–86, all
replicating across different DJs). Hitting 95 is most of the battle.

## 2. Key — needs measuring, don't trust the databases

Public BPM/key sites disagree on PTTR (F major vs A♭ major reported; the
Dionne Warwick "Walk On By" sample complicates it). **Measure it directly**
when we have the file — our own key estimator is in `analysis/analyze.py` and
has been sane across the corpus.

What matters for pairing:
- VC's jhummar sits in **F# minor**, Izzat's in **C minor**.
- The corpus principle that held up: adjacent/layered material should share a
  **pitch collection** — relative major/minor pairs, not necessarily same tonic.
- So once PTTR's real key is measured, pick dhol/melodic partners in its
  relative or parallel minor. PTTR is dark and minor-leaning in feel, which is
  friendly to the jhummar references we have.

## 3. What survives from PTTR, layer by layer

Demucs gives us vocals / drums / bass / other. Decisions:

| layer | verdict | reasoning |
|---|---|---|
| **Hook vocal** ("paint the town red") | **KEEP — this is the anchor** | Chant-like, repetitive, low syllable density. Fits the measured jhummar vocal profile (0.63–0.84 syllables/sec vs rap's 1.15). |
| **Verse rap** | **CHOP HARD or drop** | Verse flow is dense 16th-note rap. That is the single behaviour our data says fights jhummar. Keep only isolated punch-in lines on accents. |
| **"Walk On By" sample / melodic bed** | **KEEP, filtered** | Minor-mode, sparse, loops cleanly. This is the melodic identity people recognise. Consider high-passing it so the dhol owns the low end. |
| **Trap drums / 808** | **REPLACE ENTIRELY** | This is the actual jhummar conversion. Doja's kit says "pop-rap"; a dhol bed says "jhummar". Nothing else moves the needle this much. |
| **Bass** | **REPLACE or heavily duck** | Needs to get out of the dhol's way. See kuthu's empty-sub finding: leaving low-end room is what lets desi percussion read. |

**The one-line version:** keep PTTR's *hook and melody*, throw away its *rhythm
section*, and rebuild the bottom half as jhummar.

## 4. What we need to source, and from where

Roles to fill (this is where your library and the DJs' tracklists come in):

1. **Dhol bed — the core.** A jhummar dhol groove at 95 BPM. Reference audio
   extracted to `reference/jhummar/VC_jhummar_DRUMS.wav` and
   `Izzat_jhummar_DRUMS.wav` — these are the isolated drum stems from the two
   corpus jhummar segments. Listen to them as the target sound. **Do not
   reuse them in a competition mix** — they're VC's and V3NOM's work. They're
   the spec, not the material.
2. **Punjabi vocal counterpoint** — a boliyan/hook line to answer the English
   hook. Both jhummar references have this call-and-response texture.
   *This is the piece I can't source for you:* automated song ID fails
   completely on Punjabi vocals (documented in `knowledge/song_ids.json`), so
   the candidate list has to come from you or from a DJ.
3. **Optional desi melodic color** — tumbi or algoza line. Reference melody
   stems at `reference/jhummar/*_MELODY.wav`.

## 5. Draft structure (~72 seconds)

Corpus jhummar segments run 72–73s (VC's file 72s; Izzat's 1:52–3:05 = 73s).
Energy shape follows the corpus's dip-before-drop rule (every segment's loudest
moment directly follows its quietest, on 15–30s cycles).

| time | what | energy |
|---|---|---|
| 0:00–0:08 | **Entry.** PTTR melodic bed alone, filtered, no drums. Recognizable but naked — audience clocks the song. | low |
| 0:08–0:12 | **Dhol enters alone** for 4 bars. The conversion moment: same song, new body. | rising |
| 0:12–0:30 | **Main groove.** Hook vocal over full dhol bed. PTTR bass out, dhol owns low end. | mid-high |
| 0:30–0:38 | **Call and response.** Punjabi counterpoint answers the English hook. | high |
| 0:38–0:44 | **THE DIP.** Strip to vocal + minimal percussion, or near-silence. This is the corpus's most consistent structural rule. | low |
| 0:44–0:66 | **The drop / main dance block.** Everything in, densest dhol, hook repeating. This is where the choreo peak goes. | peak |
| 0:66–0:72 | **Exit.** Either a kill-switch reset (silence/VO) if the next segment's key is unrelated, or a tempo ramp if it's adjacent. | — |

## 6. Honest gaps in this plan

- **I cannot yet tell you the dhol *pattern*.** All three of my subdivision/
  swing analyses failed (see the retraction in `style_grammar.md`) — I can
  measure jhummar's tempo confidently but not its rhythmic figure. So
  "jhummar dhol groove" here means "sounds like the reference stems", not a
  notated pattern. Fixing this needs a proper downbeat/meter tracker, or your
  ear.
- **No render engine yet.** This plan is instructions, not audio. Phase 3.
- **PTTR's key is unmeasured** (no file in project).
- **Punjabi source material can't be auto-identified** — structural limit.

## 7. To move this forward

1. Drop `paint the town red.mp3/wav` into `example_mixes/` → I measure its real
   key, confirm the tempo, separate stems, and analyze the hook's actual
   syllable density against the jhummar target.
2. Name 2–3 Punjabi tracks you'd consider for the counterpoint role → I can
   analyze tempo/key compatibility even though I can't identify them blind.
3. Sanity-check the structure above against how Surma actually counts a
   72-second segment — you know the choreo side better than the numbers do.
