"""mixr backend — FastAPI.

Every route is deliberately thin: take a request, call into core/, return JSON.
The real work lives in analysis/ and engine/, unchanged.

This is also the "clean API boundary" that makes hosting possible later — the
frontend never imports Python, it only speaks HTTP. Swapping localhost for a
server URL is the whole migration.

Run:  .venv/bin/uvicorn app.server:app --reload --port 8765
"""
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "engine"))

from app.core import audio, stems, render, warp, fx      # noqa: E402
from app.core.project import Project, Clip, Effect     # noqa: E402

app = FastAPI(title="mixr", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.middleware("http")
async def no_cache(request, call_next):
    """Dev convenience: never cache the UI. Without this, editing app.js or
    index.html and refreshing can silently serve you the OLD file, and you
    debug code that isn't running."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp

# What the user sees in the browser, in order. Everything else on disk
# (example_mixes/ research material, raw renders/) stays hidden — the sidebar
# should show the user's own content, not our working files.
SOURCES = {
    "mixes":   ROOT / "mixes",              # finished mixes made in mixr
    "media":   ROOT / "library" / "audio",  # imported source tracks
    # internal: reachable by path (clips reference them) but not listed
    "stems":   ROOT / "app" / "_stems",
    "renders": ROOT / "renders",
    "examples": ROOT / "example_mixes",
}
VISIBLE = ["mixes", "media"]
LABELS = {"mixes": "Mixes", "media": "Your Media"}
for _f in SOURCES.values():
    _f.mkdir(parents=True, exist_ok=True)
PROJECTS = ROOT / "app" / "_projects"
PROJECTS.mkdir(parents=True, exist_ok=True)
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".aiff", ".aif", ".ogg"}

# One project held in memory. Multi-project comes later; this keeps the
# editing endpoints simple while the model settles.
def _restore_autosave() -> Project:
    """Start from the autosave, not a blank project.

    Any restart — including --reload after a code edit — used to drop the
    open project, and everything since the last explicit Save went with it.
    The browser autosaves every few seconds, so picking that up loses at most
    those seconds."""
    f = PROJECTS / "__autosave.json"
    if f.exists():
        try:
            return Project.load(f)
        except Exception:
            pass                                # a corrupt autosave shouldn't block startup
    return Project(name="Untitled")


STATE: dict[str, Project] = {"current": _restore_autosave()}

# ---------------------------------------------------------------- undo/redo
# A project is only numbers and file references, so a full snapshot is tiny
# (~1KB) and copying it is far simpler than tracking per-field diffs.
UNDO: list[dict] = []
REDO: list[dict] = []
MAX_UNDO = 60
_last_snap = {"key": None, "t": 0.0}


def snapshot(key: str | None = None, coalesce: bool = False):
    """Record the CURRENT state so it can be restored.

    `coalesce` collapses a burst of edits to the same control (dragging a
    volume slider fires dozens of updates) into a single undo step, so one
    Cmd+Z undoes the whole gesture rather than one pixel of it.
    """
    import time
    now = time.time()
    if coalesce and key is not None and _last_snap["key"] == key \
            and now - _last_snap["t"] < 1.2:
        _last_snap["t"] = now
        return                                   # same gesture, already captured
    UNDO.append(STATE["current"].to_dict())
    if len(UNDO) > MAX_UNDO:
        UNDO.pop(0)
    REDO.clear()                                 # a new edit invalidates redo
    _last_snap["key"] = key
    _last_snap["t"] = now


def _resolve(source: str, name: str) -> Path:
    if source not in SOURCES:
        raise HTTPException(404, f"unknown source '{source}'")
    base = SOURCES[source].resolve()
    p = (SOURCES[source] / name).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(400, "path escapes source folder")
    if not p.exists():
        raise HTTPException(404, f"no such file: {name}")
    return p


PITCH_RANGE = (-12.0, 12.0)    # an octave either way


def _warp_args(pins, pitch, mode):
    """Validate a (pins, pitch, mode) triple, turning bad input into a 400."""
    try:
        pins = warp.normalize(pins or [])
    except warp.WarpError as e:
        raise HTTPException(400, str(e))
    pitch = round(float(pitch or 0.0), 3)
    if not PITCH_RANGE[0] <= pitch <= PITCH_RANGE[1]:
        raise HTTPException(400, f"pitch must be within {PITCH_RANGE}")
    if mode not in warp.MODES:
        raise HTTPException(400, f"warp_mode must be one of {warp.MODES}")
    return pins, pitch, mode


# ------------------------------------------------------------------ browsing
@app.get("/api/sources")
def list_sources():
    """Only the user-facing categories. Internal folders are still reachable
    by path so existing clips keep resolving; they just aren't browsable."""
    out = []
    for key in VISIBLE:
        folder = SOURCES[key]
        files = []
        if folder.exists():
            for f in sorted(folder.rglob("*")):
                if f.suffix.lower() not in AUDIO_EXT or f.name.startswith("."):
                    continue
                files.append({"file": str(f.relative_to(folder)),
                              "name": f.stem,
                              "ext": f.suffix.lstrip(".").lower(),
                              "size": f.stat().st_size,
                              "modified": f.stat().st_mtime})
        files.sort(key=lambda x: -x["modified"])
        out.append({"source": key, "label": LABELS[key], "count": len(files),
                    "files": files})
    return out


@app.post("/api/media/import")
async def import_media(file: UploadFile = File(...)):
    """Copy an uploaded file into Your Media."""
    dest = SOURCES["media"] / Path(file.filename).name
    dest.write_bytes(await file.read())
    return {"imported": dest.name}


@app.get("/api/waveform")
def get_waveform(source: str, name: str, buckets: int = 2000):
    return audio.waveform(audio.to_wav(_resolve(source, name)), buckets=buckets)


@app.get("/api/analyze")
def get_analysis(source: str, name: str):
    return audio.analyze(_resolve(source, name))


@app.get("/api/audio")
def get_audio(source: str, name: str):
    wav = audio.to_wav(_resolve(source, name))
    return FileResponse(wav, media_type="audio/wav", filename=wav.name)


@app.get("/api/fx")
def fx_info():
    """The strip's controls and presets, so the UI never hard-codes a range."""
    return {"strip": {k: {"off": d, "min": lo, "max": hi} for k, (d, lo, hi) in fx.STRIP.items()},
            "presets": fx.PRESETS}


@app.post("/api/track/effects")
def track_effects(track: str, payload: dict = Body(...)):
    """Set a track's strip: {"preset": "Punch"}, {"params": {...}} (merged into
    what's there), and/or {"enabled": false} to bypass it."""
    snapshot(f"track.fx:{track}", coalesce=True)
    t = STATE["current"].track(track)
    if not t:
        raise HTTPException(404, "no such track")
    cur = next((e for e in t.effects if e.kind == "strip"), None)
    params = dict(cur.params) if cur else {}
    enabled = cur.enabled if cur else True
    if "preset" in payload:
        if payload["preset"] not in fx.PRESETS:
            raise HTTPException(400, f"unknown preset {payload['preset']!r}")
        params = dict(fx.PRESETS[payload["preset"]])
        enabled = True
    params.update(payload.get("params") or {})
    enabled = bool(payload.get("enabled", enabled))
    p = fx.normalize(params)
    # an all-off strip is stored as no strip, so "Clean" really is untouched audio
    t.effects = [] if fx.is_identity(p) else [Effect(id=cur.id if cur else Effect().id,
                                                     kind="strip", enabled=enabled, params=p)]
    return STATE["current"].to_dict()


@app.get("/api/cache")
def cache_info():
    return audio.cache_stats()


@app.post("/api/cache/clear")
def cache_clear(kind: str = "renders"):
    """Safe by construction: this only touches app/_cache, which holds nothing
    but rebuildable files. Projects, stems and exported mixes live elsewhere."""
    return {"freed": audio.clear_cache(kind), **audio.cache_stats()}


# ------------------------------------------------------------------ warp
# POST because a warp map can hold hundreds of pins. The body carries the map
# itself rather than a clip id, so the response depends only on the request —
# the browser can cache by it, and nothing can change underneath mid-fetch.
def _warped_path(body: dict):
    """(path, base) for a clip's audio. `base` is the warped-file time the
    returned audio starts at; the browser subtracts it when scheduling."""
    pins, pitch, mode = _warp_args(body.get("warp"), body.get("pitch"),
                                   body.get("warp_mode", "crisp"))
    try:
        src = _resolve(body["source"], body["name"])
    except KeyError:
        raise HTTPException(400, "body needs source and name")
    return audio.clip_audio(src, pins, pitch, mode,
                            float(body.get("offset", 0.0)),
                            float(body.get("length", 0.0)),
                            body.get("effects") or [])


@app.post("/api/warp/audio")
def warp_audio(body: dict = Body(...)):
    wav, base = _warped_path(body)
    # the base rides along in a header so the audio body stays a plain WAV
    return FileResponse(wav, media_type="audio/wav", filename=wav.name,
                        headers={"X-Warp-Base": f"{base:.6f}",
                                 "Access-Control-Expose-Headers": "X-Warp-Base"})


@app.post("/api/warp/waveform")
def warp_waveform(body: dict = Body(...)):
    wav, base = _warped_path(body)
    out = dict(audio.waveform(wav, buckets=int(body.get("buckets", 2000))))
    out["base"] = base
    return out


# ------------------------------------------------------------------ stems
@app.post("/api/stems/start")
def stems_start(source: str, name: str):
    return stems.start(_resolve(source, name))


@app.get("/api/stems/status")
def stems_status(source: str, name: str):
    src = _resolve(source, name)
    st = stems.status(src)
    found = stems.existing(src)
    if found:
        rel = {k: str(v.relative_to(SOURCES["stems"])) for k, v in found.items()}
        st = {**st, "stems": rel}
    return st


# ------------------------------------------------------------------ project
@app.get("/api/project")
def get_project():
    return STATE["current"].to_dict()


@app.post("/api/project/new")
def new_project(name: str = "Untitled"):
    UNDO.clear(); REDO.clear()
    STATE["current"] = Project(name=name)
    return STATE["current"].to_dict()


@app.post("/api/project/tempo")
def set_tempo(bpm: float = Body(...), downbeats: list[float] = Body(default=[]),
              key: str = Body(default=""), clear_downbeats: bool = Body(default=False)):
    """Sets the tempo NUMBER only — warped clips don't follow. Use
    /api/project/retempo to change tempo and carry the clips with it.

    clear_downbeats drops an analysed grid so snapping falls back to a plain
    bpm grid (an empty `downbeats` list means "leave it alone")."""
    snapshot("tempo", coalesce=True)
    p = STATE["current"]
    p.bpm = bpm
    if clear_downbeats:
        p.downbeats = []
    elif downbeats:
        p.downbeats = downbeats
    if key:
        p.key = key
    return p.to_dict()


@app.post("/api/project/retempo")
def retempo(bpm: float = Body(..., embed=True)):
    """Change the project tempo and carry every warped clip with it."""
    snapshot("retempo")
    p = STATE["current"]
    try:
        r = p.retempo(bpm)
    except warp.WarpError as e:
        UNDO.pop()                                 # nothing changed; don't leave an empty undo step
        raise HTTPException(400, str(e))
    return {"ratio": r, "project": p.to_dict()}


# ------------------------------------------------------------------ auto-warp
def _grid(p, t: float, step: float):
    """The project bar line nearest timeline position `t`."""
    if p.downbeats:
        near = min(p.downbeats, key=lambda d: abs(d - t))
        if abs(near - t) <= step:                    # inside the analysed stretch
            return near
        # past the end of the analysed grid: keep counting bars from the last one
        last = p.downbeats[-1]
        return last + round((t - last) / step) * step
    return round(t / step) * step


@app.post("/api/clip/warp-to-grid")
def warp_to_grid(track: str, clip: str):
    """Pin every downbeat of the clip's file to a bar line of the project.

    Three steps, in this order:
      1. build the map from the file's detected downbeats
      2. keep the clip on the same MUSIC (rescale its window onto the new map)
      3. slide the clip so its first downbeat sits exactly on a bar line
    """
    snapshot("clip.warp-to-grid")
    p = STATE["current"]
    t = p.track(track)
    c = t.clip(clip) if t else None
    if not c:
        raise HTTPException(404, "no such clip")

    info = audio.analyze(_resolve(c.source, c.file))
    dbs = info.get("downbeats") or []
    if len(dbs) < 2:
        raise HTTPException(400, "no downbeats were detected in this file")

    bar = warp.best_bar(dbs, 240.0 / (p.bpm or 100.0))
    # the first downbeat inside the clip's window is the anchor
    win0 = warp.dst_to_src(c.warp, c.offset)
    anchor = next((i for i, d in enumerate(dbs) if d >= win0 - 1e-6), 0)
    pins = warp.from_downbeats(dbs, bar, anchor_dst=warp.src_to_dst(c.warp, dbs[anchor]),
                               anchor=anchor)
    try:
        pins = warp.normalize(pins)
    except warp.WarpError as e:
        raise HTTPException(400, f"couldn't build a usable map: {e}")

    c.offset, c.length = warp.rescale_window(c.warp, pins, c.offset, c.length)
    c.warp = pins
    # now snap the anchor onto the grid by moving the clip, not the audio
    anchor_tl = c.start + (warp.src_to_dst(pins, dbs[anchor]) - c.offset)
    c.start = max(0.0, c.start + (_grid(p, anchor_tl, bar) - anchor_tl))
    t.clips.sort(key=lambda x: x.start)
    return {"pins": len(pins), "bar": round(bar, 4),
            "bpm": round(240.0 / bar, 2), "project": p.to_dict()}


@app.post("/api/clip/match-key")
def match_key(track: str, clip: str):
    """Transpose the clip into the project's key."""
    p = STATE["current"]
    t = p.track(track)
    c = t.clip(clip) if t else None
    if not c:
        raise HTTPException(404, "no such clip")
    if not p.key:
        raise HTTPException(400, "the project has no key yet")
    info = audio.analyze(_resolve(c.source, c.file))
    clip_key = (info.get("key") or {}).get("key", "")
    semis = warp.semitones_between(clip_key, p.key)
    if semis is None:
        raise HTTPException(400, f"couldn't read a key for this clip (got {clip_key!r})")
    snapshot("clip.match-key")
    c.pitch = float(semis)
    return {"from": clip_key, "to": p.key, "semitones": semis,
            "confidence": (info.get("key") or {}).get("confidence"),
            "project": p.to_dict()}


@app.post("/api/track/add")
def add_track(name: str = "Track", color: str = "#4da3ff"):
    snapshot("track.add")
    t = STATE["current"].add_track(name=name, color=color)
    return {"track": t.id, "project": STATE["current"].to_dict()}


@app.post("/api/track/remove")
def remove_track(track: str):
    snapshot("track.remove")
    if not STATE["current"].remove_track(track):
        raise HTTPException(404, "no such track")
    return STATE["current"].to_dict()


@app.post("/api/track/update")
def update_track(track: str, payload: dict = Body(...)):
    snapshot(f"track.update:{track}:{''.join(sorted(payload))}", coalesce=True)
    t = STATE["current"].track(track)
    if not t:
        raise HTTPException(404, "no such track")
    for k in ("name", "volume", "pan", "mute", "solo", "color"):
        if k in payload:
            setattr(t, k, payload[k])
    return STATE["current"].to_dict()


@app.post("/api/clip/add")
def add_clip(track: str, payload: dict = Body(...)):
    snapshot("clip.add")
    p = STATE["current"]
    t = p.track(track)
    if not t:
        raise HTTPException(404, "no such track")
    src = _resolve(payload["source"], payload["file"])
    info = audio.analyze(src)
    length = float(payload.get("length") or info["duration"])
    c = t.add_clip(name=payload.get("name") or Path(payload["file"]).stem,
                   source=payload["source"], file=payload["file"],
                   start=float(payload.get("start", 0.0)),
                   offset=float(payload.get("offset", 0.0)),
                   length=length)
    pins = payload.get("warp")
    if pins is None and "stretch" in payload:
        pins = warp.uniform(float(payload["stretch"]))
    c.warp, c.pitch, c.warp_mode = _warp_args(pins, payload.get("pitch"),
                                              payload.get("warp_mode", "crisp"))
    if not payload.get("length"):          # a whole-file clip spans the WARPED file
        c.length = warp.src_to_dst(c.warp, info["duration"])
    return {"clip": c.id, "project": p.to_dict()}


@app.post("/api/clip/update")
def update_clip(track: str, clip: str, payload: dict = Body(...)):
    snapshot(f"clip.update:{clip}:{''.join(sorted(payload))}", coalesce=True)
    t = STATE["current"].track(track)
    if not t:
        raise HTTPException(404, "no such track")
    c = t.clip(clip)
    if not c:
        raise HTTPException(404, "no such clip")
    if any(k in payload for k in ("warp", "stretch", "pitch", "warp_mode")):
        if "warp" in payload:
            new_pins = payload["warp"]
        elif "stretch" in payload:           # convenience: a plain stretch
            new_pins = warp.uniform(float(payload["stretch"]))
        else:
            new_pins = c.warp
        new_pins, new_pitch, new_mode = _warp_args(
            new_pins, payload.get("pitch", c.pitch), payload.get("warp_mode", c.warp_mode))
        # offset and length are measured on the WARPED file. A new map moves
        # that file's timeline, so re-find the same stretch of music on it.
        # start stays put: the clip grows or shrinks from its left edge.
        c.offset, c.length = warp.rescale_window(c.warp, new_pins, c.offset, c.length)
        c.warp, c.pitch, c.warp_mode = new_pins, new_pitch, new_mode
    for k in ("start", "offset", "length", "gain", "fade_in", "fade_out", "name"):
        if k in payload:
            setattr(c, k, payload[k])
    t.clips.sort(key=lambda x: x.start)
    return STATE["current"].to_dict()


@app.post("/api/clip/split")
def split_clip(track: str, clip: str, at: float):
    """Cut one clip into two at timeline position `at`.

    A clip is a window onto a file: (start, offset, length). Splitting keeps
    BOTH halves pointing at the same file and just divides the window:

        left  : start=start        offset=offset          length=at-start
        right : start=at           offset=offset+(at-start)  length=length-(at-start)

    The right half's offset advances by exactly the same amount its start did,
    which is what keeps the audio anchored — the same rule that makes trimming
    the left edge work.
    """
    MIN = 0.05
    snapshot("clip.split")
    p = STATE["current"]
    t_obj = p.track(track)
    if not t_obj:
        raise HTTPException(404, "no such track")
    c = t_obj.clip(clip)
    if not c:
        raise HTTPException(404, "no such clip")
    if not (c.start + MIN < at < c.end - MIN):
        raise HTTPException(400, f"split point {at:.3f} not inside clip "
                                 f"[{c.start:.3f}, {c.end:.3f}]")

    left_len = at - c.start
    right = t_obj.add_clip(
        name=c.name, source=c.source, file=c.file,
        start=at,
        offset=c.offset + left_len,
        length=c.length - left_len,
        gain=c.gain, fade_in=0.005, fade_out=c.fade_out,
        warp=list(c.warp), warp_mode=c.warp_mode, pitch=c.pitch,  # both halves share one map
    )
    c.length = left_len          # shrink the original into the left half
    c.fade_out = 0.005           # tiny fades at the seam so it doesn't click
    t_obj.clips.sort(key=lambda x: x.start)
    return {"left": c.id, "right": right.id, "project": p.to_dict()}


@app.post("/api/clip/remove")
def remove_clip(track: str, clip: str):
    snapshot("clip.remove")
    t = STATE["current"].track(track)
    if not t:
        raise HTTPException(404, "no such track")
    t.clips = [c for c in t.clips if c.id != clip]
    return STATE["current"].to_dict()


@app.post("/api/undo")
def undo():
    if not UNDO:
        raise HTTPException(400, "nothing to undo")
    REDO.append(STATE["current"].to_dict())
    STATE["current"] = Project.from_dict(UNDO.pop())
    _last_snap["key"] = None
    return {"project": STATE["current"].to_dict(),
            "undo": len(UNDO), "redo": len(REDO)}


@app.post("/api/redo")
def redo():
    if not REDO:
        raise HTTPException(400, "nothing to redo")
    UNDO.append(STATE["current"].to_dict())
    STATE["current"] = Project.from_dict(REDO.pop())
    _last_snap["key"] = None
    return {"project": STATE["current"].to_dict(),
            "undo": len(UNDO), "redo": len(REDO)}


@app.get("/api/history")
def history():
    return {"undo": len(UNDO), "redo": len(REDO)}


# ------------------------------------------------------------------ export
@app.post("/api/export/start")
def export_start(name: str = "mixr-export", fmt: str = "wav"):
    p = STATE["current"]
    if p.duration <= 0:
        raise HTTPException(400, "nothing to export — the project is empty")
    job = render.start(p, _resolve, name=name, fmt=fmt)
    return {"job": job}


@app.get("/api/export/status")
def export_status(job: str):
    return render.status(job)


@app.get("/api/export/download")
def export_download(file: str):
    p = (ROOT / "mixes" / file).resolve()
    if not str(p).startswith(str((ROOT / "mixes").resolve())) or not p.exists():
        raise HTTPException(404, "no such render")
    return FileResponse(p, media_type="application/octet-stream", filename=p.name)


@app.post("/api/project/save")
def save_project(name: str, rename: bool = True):
    """rename=False lets autosave write to its own slot without renaming the
    user's project to '__autosave'."""
    p = STATE["current"]
    if rename:
        p.name = name
    safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_.").strip()
    if not safe:
        raise HTTPException(400, "invalid project name")
    p.save(PROJECTS / f"{safe}.json")
    return {"saved": safe, "name": p.name}


@app.get("/api/project/list")
def list_projects():
    """Autosave is hidden from the normal list but reported separately."""
    items = []
    auto = None
    for f in sorted(PROJECTS.glob("*.json")):
        info = {"file": f.stem, "modified": f.stat().st_mtime,
                "size": f.stat().st_size}
        try:
            import json as _json
            d = _json.loads(f.read_text())
            info["name"] = d.get("name", f.stem)
            info["tracks"] = len(d.get("tracks", []))
        except Exception:
            info["name"] = f.stem
            info["tracks"] = 0
        if f.stem == "__autosave":
            auto = info
        else:
            items.append(info)
    items.sort(key=lambda x: -x["modified"])
    return {"projects": items, "autosave": auto}


@app.post("/api/project/delete")
def delete_project(name: str):
    f = PROJECTS / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "no such project")
    f.unlink()
    return {"deleted": name}


@app.post("/api/project/open")
def open_project(name: str):
    f = PROJECTS / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "no such project")
    STATE["current"] = Project.load(f)
    return STATE["current"].to_dict()


app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")
