"""Transcribe a mix's vocal stem and hunt for DJ tags + known cue phrases.

DJ tags are spoken signatures dropped into a mix ("VC on the track",
"it's the mf TK"). They're timestamped evidence of WHO mixed WHICH section -
in multi-DJ sets that's the only in-audio attribution available.

Usage: tags.py <stem_name> [<stem_name> ...]
Writes research/reports/lyrics_<name>.txt and reports/tags_<name>.json
"""
import json
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
STEMS = ROOT / "workdir" / "stems" / "htdemucs"
OUT = ROOT / "research" / "reports"

# Known circuit DJ tags. Patterns are loose because Whisper garbles names.
TAG_PATTERNS = {
    "V3NOM":  r"\bv[e3]+n[o0]m\b|\bvenom\b",
    "Lotus":  r"\blotus\b|\blowtus\b",
    "LOKA":   r"\bloka\b|\bloca\b|\blocka\b",
    "Astro":  r"\bastro\b|\bastra\b",
    "Havoc":  r"\bhavoc\b|\bhavok\b|\bhavic\b",
    "VC":     r"\bv\.?\s?c\.?\s+on the track\b|\bvc on the track\b|\bwe see on\b|\breally see on\b",
    "TK":     r"it'?s the (mf|motherfucking|m\.?f\.?) tk\b|\bthe mf tk\b|\bdj tk\b",
    "Kraken": r"\bkraken\b|\bcracken\b|\bcrackin['g]? \b",
    "TEG":    r"\bteg\b",
    "XANDR":  r"\bxandr\b|\bzander\b|\bxander\b",
    "KEV7N":  r"\bkev[7i]n\b|\bkevin\b",
    "Rev7in": r"\brev[7i]n\b|\brevin\b",
    "REAPER": r"\breaper\b",
    "Bassdoctor": r"\bbass ?doctor\b",
}

# Structural cue phrases users have flagged as segment transitions
CUE_PATTERNS = {
    "dont_forget_me": r"don'?t forget me( now)+",
    "damn_son": r"damn,? son,? where'?d you find this",
    "you_ready": r"\byou ready\b|\by'?all ready\b|\bare you ready\b",
    "cant_mess_with_club": r"can'?t (mess|fuck) with (the|this) club",
}


def run(name: str, model):
    stem = STEMS / name / "vocals.wav"
    if not stem.exists():
        print(f"SKIP {name}: no vocal stem")
        return
    print(f"--- {name}")
    segs, info = model.transcribe(str(stem), vad_filter=True, beam_size=5)
    lines, hits = [], {"dj_tags": [], "cues": []}
    lines.append(f"# language={info.language} p={info.language_probability:.2f}")
    for s in segs:
        txt = s.text.strip()
        lines.append(f"[{s.start:7.1f}-{s.end:7.1f}] {txt}")
        low = txt.lower()
        for dj, pat in TAG_PATTERNS.items():
            if re.search(pat, low):
                hits["dj_tags"].append({"dj": dj, "t": round(s.start, 1),
                                        "mmss": f"{int(s.start//60)}:{s.start%60:04.1f}",
                                        "text": txt})
        for cue, pat in CUE_PATTERNS.items():
            if re.search(pat, low):
                hits["cues"].append({"cue": cue, "t": round(s.start, 1),
                                     "mmss": f"{int(s.start//60)}:{s.start%60:04.1f}",
                                     "text": txt})
    (OUT / f"lyrics_{name}.txt").write_text("\n".join(lines))
    (OUT / f"tags_{name}.json").write_text(json.dumps(hits, indent=2))
    for h in hits["dj_tags"]:
        print(f"    TAG  {h['mmss']:>8}  {h['dj']:<10} \"{h['text'][:60]}\"")
    for h in hits["cues"]:
        print(f"    CUE  {h['mmss']:>8}  {h['cue']:<20} \"{h['text'][:60]}\"")
    if not hits["dj_tags"] and not hits["cues"]:
        print("    (no tags or cues matched)")


if __name__ == "__main__":
    model = WhisperModel("small", device="cpu", compute_type="int8")
    for n in sys.argv[1:]:
        run(n, model)
