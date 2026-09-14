"""Second-pass transcription for non-English stems.

Whisper's auto-detect fails on sung Punjabi/Tamil/Hindi over music. This forces
the language and uses a larger model. Each stem is tried in several languages;
we keep whichever produces the most text with the best avg logprob, since a
wrong-language decode tends to be short and low-confidence.
"""
from pathlib import Path
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
OUT = ROOT / "reports"

# stem -> languages worth trying
TARGETS = {
    "Surma_South_2026_v2": ["ta", "te", "hi"],          # kuthu: Tamil/Telugu
    "SURMA_CLASSICAL_real_95_Pitch_0.00_-_Tempo_95_": ["ta", "hi", "sa"],
    "Khunde": ["pa", "hi", "en"],                        # bhangra: Punjabi
    "VC_Surma_GB_V1E2_2026": ["pa", "hi", "en"],         # jhummar
    "Shershaah_Finale_2026": ["pa", "hi", "en"],
    "Texas_Talaash_2022": ["hi", "ta", "pa"],
}

model = WhisperModel("medium", device="cpu", compute_type="int8")
for name, langs in TARGETS.items():
    vocals = STEMS / name / "vocals.wav"
    if not vocals.exists():
        continue
    print(f"--- {name}")
    best = None
    for lang in langs:
        segs, _ = model.transcribe(str(vocals), language=lang, vad_filter=True,
                                   beam_size=5)
        segs = list(segs)
        if not segs:
            print(f"    {lang}: (nothing)")
            continue
        chars = sum(len(s.text) for s in segs)
        avg_lp = sum(s.avg_logprob for s in segs) / len(segs)
        score = chars * (1.0 + avg_lp)  # penalize low-confidence decodes
        print(f"    {lang}: {len(segs)} segs, {chars} chars, logprob {avg_lp:.2f}")
        if best is None or score > best[0]:
            best = (score, lang, segs, avg_lp)
    if best:
        _, lang, segs, avg_lp = best
        lines = [f"# forced_language={lang} avg_logprob={avg_lp:.2f}"]
        lines += [f"[{s.start:7.1f}-{s.end:7.1f}] {s.text.strip()}" for s in segs]
        (OUT / f"lyrics_desi_{name}.txt").write_text("\n".join(lines))
        print(f"    -> kept {lang}")
print("done")
