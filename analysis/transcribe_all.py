"""Transcribe every vocal stem with Whisper for lyric-based song ID.

Writes reports/lyrics_<name>.txt (timestamped lines + detected language).
Multilingual: language auto-detected per file (English rap transcribes well;
Hindi/Tamil passable; Punjabi + heavy melisma weak — treat as candidates only).
"""
from pathlib import Path
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
OUT = ROOT / "reports"

FILES = [
    "Surma_South_2026_v2",
    "SURMA_CLASSICAL_real_95_Pitch_0.00_-_Tempo_95_",
    "Khunde",
    "VC_Surma_GB_V1E2_2026",
    "Shershaah_Intro_2026",
    "Shershaah_Finale_2026",
    "Texas_Talaash_2022",
    "Wisconsin_Surma_Jazba_2026_FINAL_CLEAN_",
]

model = WhisperModel("small", device="cpu", compute_type="int8")
for name in FILES:
    vocals = STEMS / name / "vocals.wav"
    if not vocals.exists():
        print(f"SKIP {name} (no stem)")
        continue
    print(f"--- {name}")
    lines = []
    segs, info = model.transcribe(str(vocals), vad_filter=True)
    lines.append(f"# language={info.language} p={info.language_probability:.2f}")
    for s in segs:
        lines.append(f"[{s.start:7.1f}-{s.end:7.1f}] {s.text.strip()}")
    (OUT / f"lyrics_{name}.txt").write_text("\n".join(lines))
    print(f"    {info.language} ({info.language_probability:.2f}), {len(lines)-1} lines")
print("done")
