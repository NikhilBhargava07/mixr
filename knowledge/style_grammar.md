# DDN Style Grammar — v0.4

The knowledge base. Each claim is tagged with evidence strength:
- **[M]** measured in our corpus (n = number of examples)
- **[D]** domain knowledge (genre convention, not yet verified in corpus)
- **[H]** hypothesis — plausible from n=1, could be this DJ's taste rather than the style

Corpus: Wisconsin Surma Jazba 2026 (1 full set ×2 versions, 5 segments);
Texas Talaash 2022 (4:18 mock, segment map unpinned); Shershaah 2026 intro +
finale (MASTERED exports, team/DJ unconfirmed). Claims marked with n.

---

## ⚠️ FRAMING: DDN styles are rooted in tradition; the MUSIC diverges

User (Surma dancer), 2026-08-02, in two passes:
1. *"ddn bhangra will be VERY different than traditional bhangra js bc it is
   fusion and we are first n foremost entertainers and college kids who wanna
   js have aura farming shit."*
2. Refinement: *"however ddn bhangra is still rooted in traditional bhangra...
   the music may not be sounding traditional or following traditional
   tempo/rhythm/etc so not like REALLY different but like yeah it might be
   different."*

**The precise distinction (do not over-correct in either direction):**

- **The DANCE forms are traditional and the names mean what they mean.**
  Jhummar, khunde, chaal, luddi, dhamaal are real bhangra vocabulary. A
  jhummar segment is backing actual jhummar movement. Domain knowledge about
  the *forms* stays valid and useful.
- **The MUSIC backing them need not obey traditional conventions.** Tempo,
  rhythm, instrumentation, and song sourcing are adapted for a college
  competition stage. So domain knowledge about *traditional music* — folk
  tempo ranges, authentic dhol patterns, meter — is a WEAK prior for
  predicting what these mixes actually do.
- Therefore: when domain knowledge about traditional **music** conflicts with
  measured corpus evidence, the corpus wins. When reasoning about what a
  **dance form** is or needs, tradition still informs it.

**Also true, and shaping every choice:** these are entertainment products.
Segments are built to produce moments — poses, hits, visual gags, crowd
reactions ("aura farming"). This explains the jacket segment having the
sparsest vocals in the corpus, Talaash's VO setting up a "seven rings" pun
before playing 7 Rings, and Astro dropping a Pittsburgh anthem into a
Pittsburgh team's finale. **Song choice is often driven by meaning and moment,
not only musical compatibility.**

**Expect deliberate outliers.** Penn Dhamaka's 147.66 BPM ending breaks the
bhangra-family tempo convention — and it turns out to be Macklemore's
"Can't Hold Us" at its native 146 BPM, closing a Bill Nye-themed set. A
designed departure, not an error. Record conventions AND their exceptions.

**Implication for mixr:** encode the corpus's conventions (what wins on this
circuit now), surface them as defaults, and let the user break them on
purpose — never enforce folkloric correctness.

## Cross-style principles (set architecture)

1. **Tempo family.** Sections cluster at ~86–99 / ~117–129 / ~143 / ~172 BPM —
   related by doublings and simple ratios (86≈172/2). Transitions bridge small
   gaps or clean octave jumps, never awkward ratios. [M, n=1 set]
2. **Relative major/minor pairs.** Adjacent material shares a pitch collection
   (D minor ↔ F major in kuthu; C minor → C major lift in hip hop). Songs gel
   when they share notes, not necessarily tonic. [M]
3. **Kill switch.** When adjacent segments' keys don't relate, don't blend —
   stop dead (silence/VO/FX, ~8s observed before finale) and reset the ear. [M]
4. **Dip before drop.** Every segment's loudest moment directly follows its
   quietest; 15–30s tension cycles inside segments. [M]
5. **The felt pulse ≠ the detected pulse.** Compound styles (jhummar, kuthu,
   classical) read to beat trackers at 4/3 or 2× the danced tempo. Always
   state which layer a BPM refers to. [M]
6. **Major lift = climax.** The brightest harmonic move is saved for the final
   push: hip hop C min→C maj (DJ unknown), classical D min→D maj (Astro),
   Shershaah finale G# min→G# maj (Astro). Parallel or relative major, always
   at the energy climax. [M, n=3 sightings, 2 of 3 are Astro — needs a
   confirmed non-Astro sighting to be circuit-wide]
7. **Sets are multi-DJ compilations.** Surma Jazba 2026: kuthu=Loka,
   bnat=Astro, khunde=V3NOM, afrobeats×kathak=Havoc, jhummar=VC,
   finale=Astro. Teams commission segments per-DJ, then someone assembles the
   set (VO glue, level-matching). Cross-segment consistency (tempo family,
   kill-switch resets) survives ACROSS DJs — meaning either the assembler
   enforces it or it's shared circuit convention. [M, n=1 set]

## Tempo conventions — the most reliable finding in the corpus

Measured by least-squares fit of beat times (sub-frame precision; validated
against Smooth Criminal, which reads 118.19 vs its true 118 BPM — 0.2% error).

⚠️ Earlier versions of this file reported "exactly 99.4" for finales. That was
**frame quantization**: librosa's beat tracker emits integer frame indices, so
median-interval tempo can only land on 60/(k x 11.61ms) — near 99 BPM the
reachable values are 101.33, 99.38, 97.51, 95.70... i.e. ~1.9 BPM resolution.
Regression over many beats removes this. Real numbers below.

| segment | DJ | fitted BPM |
|---|---|---|
| Surma finale | Astro | 99.82 |
| Shershaah finale | Astro | 98.80 |
| Izzat finale | V3NOM | 99.17 |
| Broad Street finale | multi-DJ | 99.93 |
| **finale mean** | **3+ DJs, 4 sets** | **99.4 ± 0.5** |
| Izzat khunde | V3NOM | 98.27 |
| VC jhummar | VC | 95.43 |
| Izzat jhummar | V3NOM | 92.28 |
| kuthu (Surma / Izzat / Izzat-finale) | Loka, V3NOM-set | 82 - 86 |
| Penn Dhamaka ending | multi-DJ | **147.66 — NOT in the family** |

**What holds [M, n=4, 3+ DJs]:** finale bhangra lands at **99.4 ± 0.5 BPM**
across four independent sets and at least three DJ credits. A 1.1 BPM spread
over four sets is a real convention, not coincidence.

**What I over-claimed and now correct:** I said this tempo was *specific to
finales*. It isn't — Izzat's khunde sits at 98.27, inside the finale range.
The honest statement is that **the bhangra family (khunde, chaal, finale)
lives at ~98-100 BPM**, and finale is one member of it, not a separate target.

**What IS tempo-distinct:** jhummar (92-96) is clearly slower than the bhangra
family, and kuthu (82-86) clearly slower still. Those separations are 3-6x the
measurement error, so they're solid.

**Counterexample worth noting:** Penn Dhamaka's ending is 147.66 BPM — nowhere
near the bhangra family. Either Legends-format sets end differently, or Penn's
finale is elsewhere in the mix. Unresolved.

Practical takeaway for building a mix: bhangra-family ~99, jhummar ~93-95,
kuthu ~84. Get the tempo right and you are most of the way to the style.

## ⛔ RETRACTED: all subdivision / swing claims (2026-08-02)

**Every claim I previously made about where swing "lives" per style is
withdrawn.** They were measurement artifacts. Three independent method
versions all failed, and the failure is instructive:

| version | approach | outcome |
|---|---|---|
| v1 `meter.py` | fixed onset threshold, single beat grid | **unstable** — verdict flipped straight↔compound on a 4-second window shift; ratios of 0.00 and 1e8 |
| v2 `meter2.py` | regularized ratio, grid search, confidence | **honest but starved** — the fixed onset `delta` detected 1 onset in 18s of hip hop; envelope dynamic range varies per segment so any fixed threshold is arbitrary |
| v3 `meter3.py` | continuous envelope, no threshold | **stable but blind** — ratios reproducible to ±0.03, but known-STRAIGHT Smooth Criminal (0.96) is indistinguishable from expect-COMPOUND bharatanatyam (1.09). Everything regresses to 1.0 |
| v4 (autocorrelation) | periodicity at beat/3 vs beat/2, beat/4 | **explains why**: every segment shows strong duple periodicity (0.39–0.74) and near-zero triplet (−0.15–0.16), regardless of actual style |

**Root cause.** You cannot infer compound vs. duple meter by measuring
subdivisions *relative to an automatically detected beat*, because the beat
tracker already picks whatever metric level fits the music. If a 6/8 groove
makes librosa lock onto the dotted-quarter or the eighth, subdivisions look
duple relative to that beat. The tracker absorbs the very distinction we
were trying to measure. All three methods were measuring the tracker's
choice, not the music's meter.

Retracted specifically: "jhummar's swing lives in the bass", "kuthu is
triplet-pure", "the bhangra hybrid stack (swung dhol under straight hats)",
"bharatanatyam rides 3-over-2 in the bell layer", "hip hop is straight
everywhere". None are supported by our data. Some may still be TRUE as
domain knowledge [D] — but we have not measured them.

⚠️ **Also suspect: the vocal-on-groove numbers.** `vocal_groove.py` and the
`vocal_drum_cosine` field in `segment.py` use the same fixed-threshold onset
detection that broke in v2. Vocal *coverage* and *syllable density* are
probably fine (they're RMS- and count-based), but any claim resting on
vocal↔drum grid alignment needs re-verification before use.

**Path forward if we want meter back:** a purpose-built downbeat tracker with
explicit meter estimation (madmom's DBN downbeat processor estimates 3/4 vs
4/4), or — more useful for teaching — skip classification entirely and just
extract and *visualize/audition the actual dhol pattern* per segment, so
patterns can be compared directly across mixes of the same style.


## 🎧 PERCEPTUAL GROUND TRUTH (dancer annotation, 2026-08-06)

Highest-confidence rhythm evidence we have. Source: the user — a Surma dancer —
listening to 7 isolated dhol beds extracted from the corpus, blind to the
measurements. Tagged [P]. **This outranks my failed signal analysis and
outranks traditional-music domain knowledge for DDN questions**, because it is
direct observation of the actual corpus by someone trained in the form.

### Jhummar — RESOLVED, and my triplet claim was WRONG
- "very driven... lowk feels like **straight eighths**"
- "very **light**", "**bouncy** n light"
- "their beds seem very similar, almost **funk like**"
- Both jhummar beds (VC, V3NOM) read as the SAME groove to a dancer → the
  style has a consistent identity across DJs [P, n=2]

**→ DDN jhummar is STRAIGHT and LIGHT, not compound/triplet.** My earlier
"jhummar swings in the bass" claim is now doubly dead: the measurement was
broken AND the perception contradicts it. Note this also diverges from the
traditional description (swaying, gentle) — DDN jhummar is *driven and funky*.
A real tradition-vs-DDN divergence, exactly the kind the user predicted.

### Chaal family — heavy, kick-led
- "way less light, much more **boom-bap** style"
- **Surma finale [Astro]: kick on "1, a 2, 3, a 4"** — i.e. a PICKUP note
  before beats 2 and 4. ⚠️ This is plausibly DDN's surviving trace of
  traditional chaal's documented 12/8 "dum-di, dum-di" lilt — the "a" is the
  "di". Tradition and DDN may line up here after all. NOT yet confirmed.
- Izzat khunde chaal: "much more **dhol centered**" but same driven/slow/heavy feel
- UT Saaya: "a little bit **lighter**, almost like Izzat jhummar, but the kick
  drum stood out much more" — same kick pattern
- Virasat khunde: "heavy on the kick drum"

### THE INVARIANT [P] — most actionable rule found so far
> "chaal beds feel **variant through different djs** but presence of a **kick
> drum or a bass or bass sounds are always there**"

**Chaal/DDN-bhangra requires a strong kick and heavy low end. The flavor varies
by DJ; the low-end presence never does.** For pose-hitting / "aura farming"
segments this is the non-negotiable ingredient.

### Saap — the documented exception [P]
- "not many drums and not as heavy... but that might js be like a sapp thing"

**→ This CONFIRMS the prediction from traditional research:** saap is a
percussion instrument the dancers play (folding wooden slats, sharp crack).
The mix thins out to leave acoustic room for it. Same principle as kuthu's
empty sub. **Prop segments (saap, khunde, chimta) get lighter mixes on
purpose** — an exception with a mechanical reason, not a violation. [P + D agree]

### What the dancer could NOT hear
- No rhythmic figure extractable from jhummar beyond "lighter" — so jhummar's
  identity may be more about TEXTURE/WEIGHT than about a pattern.

### Method note
My bar-level low-band test (30-130Hz across a 4-beat bar) was better-posed than
the earlier within-beat analyses — it targets the specific "1, a 2, 3, a 4"
claim — but profiles came back diffuse (concentration 0.02-0.15) on everything
except UT Saaya, whose kick shows a clear regular pulse that does NOT align
simply to the detected beat (repeats about every 0.75 beat = a 4:3 relationship,
the compound-meter ambiguity again). **Still inconclusive. The dancer's ear
remains the better instrument.**


## ✅ METER — PARTIALLY RESOLVED (2026-08-10), after 3 failed attempts

A working test finally exists. **Why this one works and v1-v4 didn't:** it needs
the FELT tempo as an independent input (from regression fitting + the dancer's
ground truth), then measures where periodic energy sits *relative to it*.
Earlier methods tried to infer everything from audio alone and kept measuring
the beat tracker's own choice.

**Method:** tempogram energy at 1.5x the felt pulse vs at 2x. Compound/12-8
music puts energy at 1.5x (dotted groupings); straight 4/4 puts it at 2x.
Reported as ratio = E(1.5x) / E(2x).

**VALIDATED ON KNOWN-STRAIGHT CONTROLS FIRST** — this is what the earlier
methods never passed:

| control | ratio | verdict |
|---|---|---|
| Smooth Criminal (unambiguously straight) | 0.53 | straight ✅ |
| Shershaah hiphop | 0.58 | straight ✅ |
| Surma hiphop | 0.81 | straight ✅ |

### Results

| segment | DJ | ratio | reading |
|---|---|---|---|
| **Shershaah CHAAL** | Astro | **1.44** | **COMPOUND** |
| Shershaah finale | Astro | 0.90 | ambiguous |
| Virasat khunde | V3NOM×Lotus | 0.81 | straight |
| Izzat finale bhangra | V3NOM | 0.71 | straight |
| Purdue jhummar | TK+DG | 0.94 | ambiguous |
| Shershaah jhummar | Rev7in | 0.64 | straight |
| VC jhummar | VC | 0.61 | straight |

### What this establishes

1. **JHUMMAR IS STRAIGHT — confirmed by measurement, 3 DJs.** Ratios 0.61,
   0.64, 0.94, all at or below the straight controls. This independently
   confirms the dancer's perception ("lowk feels like straight eighths") and
   permanently kills my original triplet claim. [M, n=3 DJs + [P]]

2. **CHAAL SPECIFICALLY IS COMPOUND.** 1.44 — far above every control and
   every other segment. This matches the traditional documentation exactly
   (chaal = 4/4 felt as 12/8, "dum-di dum-di"). It also explains why the beat
   tracker read that section at 147.2 BPM: 98.13 x 1.5 = 147.2, the dotted
   grouping. ⚠️ **n=1.** Needs more explicitly-labelled chaal segments.

3. **NOT ALL BHANGRA-FAMILY IS COMPOUND.** Khunde (0.81) and finale (0.71,
   0.90) read straight-to-ambiguous. So the triplet lilt is chaal's signature,
   not a blanket property of bhangra-family material. This is a real
   distinction the corpus supports and my earlier blanket claims got wrong in
   both directions.

**Still open:** more chaal examples; whether the ambiguous finales (0.90) sit
between deliberately.

## New style tempos (2026-08-10)

| style | BPM | source |
|---|---|---|
| dhamaal | **74.76** | Shershaah [Astro], user-timestamped |
| contemp | **135.53** (felt ~68) | Purdue [DG] — FIRST contemp measurement |
| saaps bhangra | 97.85 (Jasmit) / 98.41 (Subsonic×Lotus) | two DJs, 0.5 BPM apart |
| chaal | 98.13 | Shershaah [Astro] |

**Jhummar range widens to 86-102** with n=8: 86.27, 92.28, 92.37, 92.98,
92.99, 95.43, 98.87, 101.58. Centre of mass still ~93, but Rev7in's runs
notably fast at 101.6.

## Vocal-on-groove treatment

Measured on vocal stems (cosine = vocal/drum position-histogram similarity): [M, n=1 each]

| style     | coverage | syllables/s | cosine | reading |
|-----------|----------|-------------|--------|---------|
| hip hop   | 61%      | 1.15        | 0.95   | rap doubles the drum grid — vocal IS percussion |
| classical | 47%      | 1.56        | 0.81   | dense but floats off-grid most (melisma/konnakol) |
| jhummar   | 66%      | **0.63**    | 0.63   | sparse & sustained (density is the reliable part) |
| khunde    | 66%      | 0.89        | 0.70   | middle ground |
| kuthu     | 53%      | 1.40        | 0.24   | interlocks with drums (call/response), doesn't double them |

⚠️ **Cosine column is UNRELIABLE** — it depends on the same broken onset
detection (see retraction above). Coverage and syllables/s are count/RMS based
and survive.

**The English-vocal-on-jhummar answer (v1, trimmed to what holds):** VC's
jhummar vocal is *syllable-sparse* — 0.63/s vs rap's 1.15/s, and Izzat's
jhummar is 0.84/s, so both jhummar segments sit well below rap density. That
part replicates across two DJs. → Surviving transferable rule: **for jhummar,
pick English vocals with slow, sustained phrasing, or chop a dense vocal
sparse — roughly half the syllable rate of a rap verse.** The dhol owns
rhythm, the vocal owns melody. [M, n=2]

The stronger claim I made earlier — that accents land on a *swung* grid — is
withdrawn pending a working meter method.

## Per-style quick sheets

### Jhummar
- Tempo: **92.3 (Izzat/V3NOM) – 95.7 (Surma/VC)** — replicates across DJs [M, n=2]
- Meter: 6/8-family [D — domain knowledge only; our measurement was retracted]
- Vocals: VC's is sparse/sustained (0.63-0.84 onsets/s), lower syllable density
  than rap. Density figure is count-based so it survives the retraction;
  the grid-alignment figure does not. [M partial, n=2]
- Key: F# minor (VC), C minor (Izzat) — no style-level key claim [—]

### Kuthu
- Tempo: **82 (Izzat/V3NOM-set) – 86 (Surma/Loka)** felt; detectors report 2x.
  Loka's Izzat finale kuthu also lands at 82.0. [M, n=3, 2 DJs]
- Meter: 6/8-family folk feel [D — our measurement retracted]
- Keys: D minor ↔ F major relative flips (Surma) [M n=1]
- Vocals: densest of the desi styles (1.40/s) [M n=1]

### Khunde (bhangra)
- Tempo: **97.5 (Izzat) – 99.4 (Surma)**, both V3NOM [M, n=2 same DJ]
- Form: a "damn son where'd you find this" drop marks the switch into khunde
  chaal in Izzat (4:55). Segment structure = khunde → drop → chaal. [M n=1]
- Subdivision signature: RETRACTED, see above.

### Bharatanatyam / classical
- Tempo: DAW label 95, detector 129 (≈95×4/3) [M n=1]
- Vocals: highest syllable density in corpus (1.56/s) [M n=1]
- Ends with minor→major (D min → D maj) lift into next segment [H n=1]

### Western hip hop
- Tempo: 143.6 felt 72 half-time (Surma) [M n=1]
- Harmonic arc: minor for body, relative/parallel major lift for last stretch [M n=1]
- Loudest single drop of the set lives here (RMS 0.45) [M n=1]
- Two songs, key-related, swapped at the lift point (ian '3.5' C min →
  A$AP Ferg 'Demons') — the "lift" is partly just a song change [M n=1]

### Visual-gimmick segments (jacket dance, glove-style tricks)
- Izzat's jacket segment has the **sparsest vocals in the whole corpus**
  (0.17–0.20 onsets/s, ~1/6 of rap density) [M n=1]
- Reading: when 30 dancers must hit a visual on an exact count, the music gets
  out of the way — sparse, obvious, unambiguous. Contrast with the hip hop
  right before it (1.48–1.56/s). [H n=1, but mechanically sensible]

### Finale bhangra (luddi → chaal → bhangra)
- **THE 99.4 BPM FINALE GROOVE IS CROSS-DJ — upgraded to circuit convention.**
  Astro (Surma finale, G min), Astro (Shershaah finale, G#), and **V3NOM
  (Michigan Izzat finale, F min)** all land on a 99.4 BPM detected grid. Two
  independent DJs, three sets, identical groove tempo. This is no longer one
  DJ's formula — it's how finale bhangra is built on this circuit. [M, n=3, 2 DJs]
- Sustained energy: RMS 0.47 (Astro's two) / 0.33 (V3NOM's). Astro masters
  hotter; the tempo convention is shared, the loudness is taste. [M, n=3]
- **One key for the whole finale** — no harmonic wandering; variety comes from
  dhol + texture, not keys. Shershaah holds G# ~100s; Surma holds G min 74s.
  [M, n=2 same DJ]
- Vocals: chant-like, coverage 73% (highest in corpus) — boliyan/chant texture.
  The grid-alignment figure is retracted; coverage stands. [M partial, n=1]
- Izzat's finale is preceded by a Loka kuthu at 82 BPM, then a
  "you ready? / make way for the king" call, then V3NOM's bhangra at 99.4.
  Finale = handoff between two DJs' segments. [M n=1]
- Parallel-major lift for the sustained climax. [M, n=1 finale; n=3 overall]
- Internal order luddi → chaal → bhangra (user ground truth, Surma)
- Surma sub-segment split (luddi/chaal/bhangra tempo-meter) still TODO

### Intro
- Energy ramps monotonically — NO dip-before-drop cycles; that rule is for
  segments, intros just climb (RMS 0.14→0.40 over 84s). [M, n=1]
- Fastest section-cutting in corpus (10 sections / 84s). [M, n=1]
- Half-time "menace" section (76 BPM, corpus's slowest) early, before the ramp. [M, n=1]
- Shershaah intro percussion is triplet-PURE low+mid (zero duple mass) —
  filmi-dhol-driven opening. Whether compound intros are a norm or this set's
  theme choice: unknown. [H, n=1]

### Afrobeats × kathak, contemp
- No isolated example yet. [—]

## Open questions
- VO placement/ducking rules (full-set stems separating now; diff VO vs CLEAN)
- Finale internal grammar: what changes luddi→chaal→bhangra?
- Where do the drums come from? (sample-source ID needs source tracklists — ask Astro/VC)
- Language/singing-style detection on vocal stems (Punjabi vs Tamil vs English profiling)
