# The Science of Percussion Placement in DDN Mixes

Everything here is either measured in our corpus or measured directly on
synthesized voices in this project. Where a claim is established
psychoacoustics rather than something we measured, it says so.

---

## 1. THE CENTRAL RESULT: register determines articulation rate

This is a **physical constraint, not a stylistic choice**, and it explains most
of what "sounds right" in these mixes.

Measured on our own voices (Hilbert envelope, time to −20 dB):

| voice | spectral centroid | perceptual onset | occupies | max clean rate |
|---|---|---|---|---|
| felt_sub 50 Hz | 57 Hz | **17.5 ms** | **600 ms** | 1.7 /s |
| dagga (kick register) | 115 Hz | 0.9 ms | **420 ms** | 2.4 /s |
| thok (mid body) | 3.8 kHz | ~0 ms | 12 ms | 81 /s |
| tilli (mid-high) | 8.9 kHz | ~0 ms | 19 ms | 52 /s |
| shaker (high) | 12.6 kHz | ~0 ms | 4 ms | 228 /s |

At 95 BPM: **beat = 632 ms, 8th = 316 ms, 16th = 158 ms.**

**Therefore:**

- A kick occupies **420 ms — that is 66% of a whole beat.** Two kicks an eighth
  apart (316 ms) physically **overlap by 104 ms**. They do not articulate as two
  events; they smear into one lumpy mass. *A kick literally cannot play
  eighth notes cleanly at this tempo.*
- A tilli occupies **19 ms — 12% of a 16th-note slot.** You can place one on
  every single 16th and still leave 88% of the time empty.

> **This is the answer to "why do kicks work here but not there."** It is not
> taste. Low-frequency events are long because low frequencies need many
> cycles to exist at all — a 50 Hz tone takes 20 ms for ONE cycle, and the ear
> needs several cycles before it hears pitch. High-frequency events are short
> because the opposite is true. **The band you choose sets the maximum rate you
> can articulate in it.**

### The corollary the dancer arrived at independently

> *"deeper sounds should be felt not heard (there to drive the song, but not to
> take away from the bounce and lightness) and lighter happier sounds should
> fall on the and's and odds"*

That is exactly the constraint above, stated from the dance floor: put slow
structural events in the low band, put fast articulation in the high band.
The physics and the intuition agree.

## 2. Perceptual onset is frequency-dependent — the flam trap

Measured: `felt_sub` (50 Hz) reaches perceptual peak at **36 ms**; `dagga2`
with mid shell modes peaks at **6.6 ms**. Both triggered at t=0.

**Consequence:** layering a sub under a kick creates *two* perceptual onsets
30 ms apart from one event — an audible flam. We hit this exactly, and the
dancer heard it as "a t-tung sorta sound, almost like a flam but on a kick."
The fix was to use a single voice.

**Rule:** if two layers must read as one hit, either give them the same attack
time, or place the low layer EARLIER by the difference. Otherwise a "layered"
kick becomes a flam.

## 3. Why the low band carries the energy but the fewest events

Measured band balance of real jhummar drum stems: **L/M/H ≈ 80 / 12 / 6 %**
(n=6 segments). Measured event density: **2.8–6.2 hits/sec total.**

These two facts are only compatible if the low band holds most of the *energy*
while the mid/high hold most of the *events* — which is what the rate limits
above require. Equal-loudness contours (established psychoacoustics) explain
the energy side: low frequencies need substantially more energy than mids to
be perceived as equally loud.

**Design consequence:** a drum bed that is 96% low energy — as ours was before
the fix — has no articulation left. It reads as weight with no groove. That
was measurably our problem, and correcting the band balance to ~88/9/2 is what
fixed the "no natural bounce" complaint.

## 4. Masking: why space after the kick is not optional

Established psychoacoustics: masking spreads **upward** in frequency far more
than downward. A loud low-frequency event raises the hearing threshold for
higher-frequency events for a short window after it.

**Consequence:** delicate high-frequency detail placed immediately after a
kick is partly inaudible — you pay CPU and headroom for something the ear
discards. This is why corpus beds leave the moments right after the downbeat
comparatively open, and why ghost notes land between structural hits rather
than on top of them.

**Related measured finding:** in all four new jhummar tracks, when drums drop
out the **bass drops harder than the melody** (Mohini −72% bass vs −32%
melody; Virasat 2025 −77% bass while melody *rose* 68%). Kick and bass occupy
overlapping critical bands — they are one perceptual object, so DJs remove
them together. A "graceful" section is a **register inversion**, not a tempo
change (tempo held constant: Manzat residual SD 13.9 ms).

## 5. ⛔ NEGATIVE RESULT: there is no fixed "jhummar drum pattern"

We tried to extract one. It does not exist in this corpus, and we can prove
the method wasn't at fault.

**Method:** find the downbeat phase maximising bar-to-bar self-consistency,
then average the 16-slot × 3-band grid across all bars.

**Control:** a synthesized bed with a literally exact repeating 1-bar pattern.

| material | 1-bar self-consistency |
|---|---|
| **CONTROL (known fixed loop)** | **0.917** |
| Manzat jhummar 2024 | 0.136 |
| VC jhummar [Surma] | 0.013 |
| TK+DG jhummar [Purdue] | 0.021 |
| Rev7in jhummar [Shershaah] | 0.004 |
| Chaal [Astro] | 0.013 |
| Khunde [V3NOM×Lotus] | 0.015 |

The control recovers 0.917. Real segments score 0.004–0.136 — **7× to 200×
lower.** The method works; the music genuinely does not repeat a fixed one-bar
drum pattern. (Longer-cycle tests at 2/4/8 bars are underpowered — too few
cycles to be statistically meaningful — so they neither confirm nor rule out
longer loops.)

**What this means for mixr — and it is a design decision, not a footnote:**

DDN drum beds are **through-composed**, not loop-based. Style identity does
NOT live in a repeating pattern you can copy. It lives in the *statistical and
physical* properties:

- tempo (the single most reliable marker)
- meter — compound vs straight (chaal compound at 1.44; jhummar straight at 0.61–0.94)
- band balance (~80/12/6 for bhangra-family drums)
- event density (2.8–6.2 hits/s)
- the register rate limits in §1

**So mixr should generate beds that satisfy these constraints and vary
continuously — not stamp out a loop.** Our synthesized beds have sounded
artificial partly because they repeat exactly; real ones never do.

## 6. Practical placement rules that follow

1. **Kick: at most one per beat**, realistically on 1 and sometimes 3. Two
   kicks an eighth apart overlap by 104 ms at 95 BPM. If you want fast low-end
   movement, shorten the kick — you cannot have both length and speed.
2. **Never layer a slow-attack sub under a fast-attack kick** unless you offset
   it. That is a flam, not a layer.
3. **All fast subdivision goes in the mid/high bands.** 16ths, ghost notes,
   swing detail — these are physically only available above ~2 kHz.
4. **Leave the window right after the kick relatively clear** in the high band;
   upward masking eats it anyway.
5. **Treat kick and bass as one object.** Drop them together for graceful
   sections; the corpus does this consistently.
6. **Target ~80/12/6 L/M/H energy** for a bhangra-family drum bed. Below ~5%
   mid, the bed loses articulation and reads as weight only.
7. **Vary the bed continuously.** Bar-to-bar identity in real mixes is near
   zero; exact repetition is an audible tell of synthetic production.
