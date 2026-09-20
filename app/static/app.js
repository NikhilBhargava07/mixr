// mixr — multitrack timeline. Vanilla JS, no build step.
// Talks to the Python backend only over HTTP, so hosting later is a URL change.

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- state
let project = null;
let pxPerSec = 60;              // zoom
let scrollX = 0;                // seconds at the left edge
let follow = true;              // auto-scroll to keep the playhead on screen
const waveCache = new Map();    // "source/file" -> waveform json
const bufCache = new Map();     // "source/file" -> decoded AudioBuffer
let actx = null;
let playing = false, playStart = 0, playOffset = 0;
let liveNodes = [];
let buses = {}, master = null;  // per-track audio buses and the master, while playing
const meters = {};              // trackId (or "master") -> {peak, hold, holdUntil, clipped}
// `selection` is the truth: every selected clip. `selected` stays as the
// last-clicked one, which single-clip actions (split, the clip menu) use.
let selection = [];             // [{track, clip}]
let selected = null;            // {track, clip} — the primary
let clipboard = [];             // copied clips, positions relative to the earliest
const isSelected = (id) => selection.some(s => s.clip === id);
function selectOnly(track, clip) { selection = [{ track, clip }]; selected = selection[0]; }
function selectToggle(track, clip) {
  const i = selection.findIndex(s => s.clip === clip);
  if (i >= 0) { selection.splice(i, 1); selected = selection[selection.length - 1] || null; }
  else { selection.push({ track, clip }); selected = { track, clip }; }
}
function clearSelection() { selection = []; selected = null; }
// the live clip objects behind the selection, skipping anything since deleted
const selectedClips = () => selection.map(s => {
  const tr = project.tracks.find(x => x.id === s.track);
  const c = tr && tr.clips.find(x => x.id === s.clip);
  return c ? { tr, c } : null;
}).filter(Boolean);

const TRACK_H = 84, HEAD_W = 190, RULER_H = 30;
const PH_W = 8, PH_HEAD_H = 13;   // playhead handle: half-width, height
const PIN_W = 4, PIN_H = 11;      // warp-pin handle: half-width, height

// ---------------------------------------------------------------- helpers
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" },
              body: body === undefined ? undefined : JSON.stringify(body) });
// Clip.end is a Python @property, so it never survives the trip to JSON —
// reading c.end here silently gave undefined, and every comparison against it
// was false. That made clips unclickable: no select, drag, trim or fade.
// Run the audio graph at the project's rate (44.1 kHz), not the hardware's.
// Left to default, a Mac usually picks 48 kHz and every clip gets resampled on
// decode — so preview and export would be computed at different rates. The
// browser still converts the final output to the hardware rate, once, at the
// very end, which is unavoidable and changes nothing upstream.
const makeContext = () => new (window.AudioContext || window.webkitAudioContext)(
  { sampleRate: (project && project.sample_rate) || 44100 });
const clipEnd = (c) => c.start + c.length;

// ---------------------------------------------------------------- scrolling
// How far right the view can go: the end of the last clip plus a little room
// to work past it — never endlessly into empty timeline, which is how the view
// used to get lost off to the right.
const viewSeconds = () => Math.max(1, ($("timeline").clientWidth - HEAD_W) / pxPerSec);
function contentEnd() {
  let end = 0;
  if (project) for (const tr of project.tracks) for (const c of tr.clips) end = Math.max(end, clipEnd(c));
  return end + Math.max(8, viewSeconds() * 0.25);
}
const maxScroll = () => Math.max(0, contentEnd() - viewSeconds());
function setScroll(s) {
  scrollX = Math.max(0, Math.min(maxScroll(), s));
}

function updateScrollbar() {
  const bar = $("hscroll"), thumb = $("hthumb");
  if (!bar || !thumb) return;
  const total = Math.max(contentEnd(), viewSeconds()), w = bar.clientWidth;
  thumb.style.width = Math.max(24, (viewSeconds() / total) * w) + "px";
  thumb.style.left = Math.min(w - thumb.offsetWidth, (scrollX / total) * w) + "px";
  bar.style.visibility = maxScroll() > 0 ? "visible" : "hidden";
}
const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

// A clip's audio is identified by its file, its warp AND its track's channel
// strip: the same song under two warp maps, or through two strips, is two
// different files on the server, with two different waveforms.
// warpOf() pulls out just the clip's own fields, so they copy onto new clips.
const warpOf = (c) => ({ warp: c.warp || [], warp_mode: c.warp_mode || "crisp", pitch: c.pitch || 0 });
const isWarped = (c) => (c.warp && c.warp.length > 0) || Math.abs(c.pitch || 0) > 1e-6;
// The strip lives on the track, so look the clip's track up. Objects that
// aren't in the project yet (a file being added) have no strip.
function fxOf(c) {
  if (!project || !c.id) return [];
  for (const tr of project.tracks) if (tr.clips.some(x => x.id === c.id)) return tr.effects || [];
  return [];
}
const hasFx = (c) => fxOf(c).some(e => e.kind === "strip" && e.enabled !== false);
const needsRender = (c) => isWarped(c) || hasFx(c);
const key = (c) => `${c.source}/${c.file}` +
  (needsRender(c) ? `@${JSON.stringify(warpOf(c))}@${windowFor(c)}@${JSON.stringify(fxOf(c))}` : "");
const plainQuery = (c) => `source=${encodeURIComponent(c.source)}&name=${encodeURIComponent(c.file)}`;
// Must match WINDOW_PAD / WINDOW_STEP in app/core/warp.py. Only used for cache
// keys here — the server computes the real window and reports where it starts.
const WINDOW_PAD = 5, WINDOW_STEP = 15;
const windowFor = (c) => [
  Math.floor(Math.max(0, c.offset - WINDOW_PAD) / WINDOW_STEP) * WINDOW_STEP,
  Math.ceil((c.offset + c.length + WINDOW_PAD) / WINDOW_STEP) * WINDOW_STEP,
];
const warpBody = (c, extra) => JSON.stringify({
  source: c.source, name: c.file, ...warpOf(c), effects: fxOf(c),
  offset: c.offset, length: c.length, ...extra });

// Where a warp pin sits on the timeline. A pin is [src, dst] in warped-file
// seconds; the clip shows the window [offset, offset+length) of that file.
const pinX = (c, pin) => c.start + (pin[1] - c.offset);

// A plain stretch is stored as [[0,0],[1,s]] — two bookkeeping pins, not
// markers anyone placed. Drawing them put a draggable handle one second into
// every stretched clip that would warp only that first second. Neither the
// origin pin nor a plain stretch's second pin is shown or grabbable.
const isPlainStretch = (w) => w.length === 2 && w[0][0] === 0 && w[0][1] === 0 && w[1][0] === 1;
const pinsInWindow = (c) => {
  const w = c.warp || [];
  if (isPlainStretch(w)) return [];
  return w.map((pin, i) => ({ i, pin, t: pinX(c, pin) }))
          .filter(o => !(o.pin[0] === 0 && o.pin[1] === 0))
          .filter(o => o.t >= c.start - 1e-9 && o.t <= clipEnd(c) + 1e-9);
};

// Inverse of the warp map — the mirror of dst_to_src() in app/core/warp.py.
// Swapping each pin's two numbers inverts a monotonic piecewise-linear map.
function warpSrcToDst(pins, t) {
  if (!pins.length) return t;
  if (pins.length === 1) return t + (pins[0][1] - pins[0][0]);
  let i = 0;
  while (i < pins.length - 2 && t > pins[i + 1][0]) i++;
  const [as, ad] = pins[i], [bs, bd] = pins[i + 1];
  return ad + (t - as) * ((bd - ad) / (bs - as));
}
const warpDstToSrc = (pins, t) => warpSrcToDst(pins.map(([a, b]) => [b, a]), t);

// Overall speed of a clip, for labels. The server's maths lives in warp.py;
// this is only the slope from the first pin to the last.
function speedOf(c) {
  const w = c.warp || [];
  if (w.length < 2) return 1;
  const a = w[0], b = w[w.length - 1];
  return (b[0] - a[0]) / (b[1] - a[1]);          // source seconds per warped second
}

// Both take a clip (or anything with source/file and optional warp fields).
// The first request for a new warp makes the server run Rubber Band, ~5s.
async function getWave(c) {
  const k = key(c);
  if (!waveCache.has(k)) {
    waveCache.set(k, needsRender(c)
      ? await api("/api/warp/waveform", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: warpBody(c, { buckets: 1600 }) })
      : await api(`/api/waveform?${plainQuery(c)}&buckets=1600`));
  }
  return waveCache.get(k);
}
async function getBuffer(c) {
  const k = key(c);
  if (!bufCache.has(k)) {
    actx = actx || makeContext();
    const r = needsRender(c)
      ? await fetch("/api/warp/audio", { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: warpBody(c) })
      : await fetch(`/api/audio?${plainQuery(c)}`);
    if (!r.ok) throw new Error(`audio ${r.status}`);
    const base = parseFloat(r.headers.get("X-Warp-Base") || "0") || 0;
    bufCache.set(k, { buffer: await actx.decodeAudioData(await r.arrayBuffer()), base });
  }
  return bufCache.get(k);
}

// ---------------------------------------------------------------- browser
const sectionOpen = { mixes: true, media: true };   // remembers per-session

function fmtSize(b) {
  return b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1e3) + " KB";
}

async function loadBrowser() {
  const groups = await api("/api/sources");
  const side = $("browser");
  side.innerHTML = "";

  for (const g of groups) {
    const sec = document.createElement("div");
    sec.className = "section";

    // ---- header: arrow + label + count (click anywhere to collapse)
    const head = document.createElement("div");
    head.className = "sechead" + (sectionOpen[g.source] ? " open" : "");
    head.innerHTML =
      `<span class="arrow">▸</span><span class="lbl">${g.label}</span>` +
      `<span class="cnt">${g.count}</span>`;
    head.onclick = () => {
      sectionOpen[g.source] = !sectionOpen[g.source];
      loadBrowser();
    };
    sec.appendChild(head);

    // ---- body
    const body = document.createElement("div");
    body.className = "secbody";
    if (!sectionOpen[g.source]) body.style.display = "none";

    if (!g.files.length) {
      const e = document.createElement("div");
      e.className = "empty";
      e.textContent = g.source === "mixes"
        ? "No mixes yet — export one and it lands here"
        : "No media yet — import audio to get started";
      body.appendChild(e);
    }
    for (const f of g.files) {
      const d = document.createElement("div");
      d.className = "file";
      d.title = `${f.file} · ${fmtSize(f.size)}`;
      d.innerHTML = `<span class="fname">${f.name}</span>` +
                    `<span class="fext">${f.ext}</span>`;
      d.onclick = () => addAsTrack(g.source, f.file);
      body.appendChild(d);
    }
    sec.appendChild(body);
    side.appendChild(sec);
  }

  // ---- import button, always at the bottom
  const imp = document.createElement("label");
  imp.className = "import";
  imp.innerHTML = `<input type="file" accept="audio/*" multiple hidden>+ Import audio`;
  imp.querySelector("input").onchange = async (e) => {
    const files = [...e.target.files];
    let done = 0; const failed = [];
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      setStatus(`importing ${f.name}…`);
      // fetch only rejects on a NETWORK failure — a 500 from the server still
      // resolves, so without checking res.ok a failed import reported success.
      try {
        const res = await fetch("/api/media/import", { method: "POST", body: fd });
        if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
        done++;
      } catch (err) { failed.push(`${f.name}: ${err.message}`); }
    }
    sectionOpen.media = true;
    await loadBrowser();
    setStatus(failed.length ? `imported ${done}/${files.length} — ${failed[0]}`
                            : `imported ${done} file${done > 1 ? "s" : ""}`);
  };
  side.appendChild(imp);
}

async function addAsTrack(source, file) {
  setStatus(`adding ${file.split("/").pop()}…`);
  const nice = file.split("/").pop().replace(/\.[^.]+$/, "");
  const { track } = await post(`/api/track/add?name=${encodeURIComponent(nice)}`);
  const r = await post(`/api/clip/add?track=${track}`, { source, file, start: 0 });
  project = r.project;
  await getWave({ source, file });
  // Adopt the grid from the FIRST track only. This used to fire whenever the
  // project had no downbeat list, so adding any later file silently replaced
  // the project's tempo and key with that file's — leaving the grid at one
  // tempo and every warped clip at another.
  if (project.tracks.length === 1 && project.tracks[0].clips.length === 1) {
    const q = `source=${encodeURIComponent(source)}&name=${encodeURIComponent(file)}`;
    const a = await api(`/api/analyze?${q}`);
    if (a.downbeats && a.downbeats.length) {
      project = await post("/api/project/tempo", { bpm: a.bpm_from_downbeats || a.bpm,
                                                   downbeats: a.downbeats,
                                                   key: (a.key && a.key.key) || "" });
    }
  }
  render(); setStatus("ready");
}

// ---------------------------------------------------------------- drawing
function render() {
  const cv = $("timeline");
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = Math.max(320, RULER_H + (project ? project.tracks.length : 0) * TRACK_H + 40);
  cv.style.height = H + "px";
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  if (!project) return;

  const x = (t) => HEAD_W + (t - scrollX) * pxPerSec;

  // ---- ruler + grid
  g.fillStyle = "#1c1f26"; g.fillRect(0, 0, W, RULER_H);
  const visT0 = scrollX, visT1 = scrollX + (W - HEAD_W) / pxPerSec;
  for (const { t: bt, i } of gridBars(visT0 - 1, visT1 + 1)) {
    const px = x(bt);
    if (px < HEAD_W) continue;                     // not over the header column
    g.strokeStyle = i % 4 === 0 ? "#5b6478" : "#333a48";
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(px, 0); g.lineTo(px, H); g.stroke();
    if (i % 4 === 0) {
      g.fillStyle = "#7c8697"; g.font = "10px system-ui";
      g.fillText(String(i + 1), px + 3, 12);
    }
  }
  for (let s = Math.ceil(visT0); s < visT1; s++) {
    if (s % 5) continue;
    g.fillStyle = "#7c8697"; g.font = "10px system-ui";
    g.fillText(fmt(s), x(s) + 3, 25);
  }

  // ---- tracks
  project.tracks.forEach((tr, i) => {
    const y = RULER_H + i * TRACK_H;
    g.fillStyle = i % 2 ? "#191c22" : "#1b1e25";
    g.fillRect(HEAD_W, y, W - HEAD_W, TRACK_H);
    g.strokeStyle = "#252a34"; g.beginPath();
    g.moveTo(0, y + TRACK_H); g.lineTo(W, y + TRACK_H); g.stroke();

    // header
    g.fillStyle = "#15181d"; g.fillRect(0, y, HEAD_W, TRACK_H);
    g.fillStyle = tr.mute ? "#5c6373" : "#e6e9ef";
    g.font = "600 12px system-ui";
    g.fillText(tr.name.slice(0, 22), 10, y + 20);
    g.fillStyle = tr.color; g.fillRect(0, y, 4, TRACK_H);
    // mute / solo pills
    drawPill(g, 10, y + 32, "M", tr.mute, "#ff6b6b");
    drawPill(g, 42, y + 32, "S", tr.solo, "#ffd43b");
    // volume bar
    g.fillStyle = "#2a2f3a"; g.fillRect(10, y + 62, 160, 6);
    g.fillStyle = tr.color;  g.fillRect(10, y + 62, 160 * Math.min(1, tr.volume), 6);
    // level meter, down the right edge of the header
    drawMeter(g, HEAD_W - 16, y + 10, 9, TRACK_H - 24, meterOf(tr.id));

    // clips — confined to the lane, so a clip scrolled partly off the left
    // edge can't paint over the track header (names, M/S, volume)
    g.save();
    g.beginPath(); g.rect(HEAD_W, y, W - HEAD_W, TRACK_H); g.clip();
    for (const c of tr.clips) {
      const cx = x(c.start), cw = Math.max(2, c.length * pxPerSec);
      if (cx + cw < HEAD_W || cx > W) continue;
      const isSel = isSelected(c.id);
      g.fillStyle = tr.color + "33";
      g.fillRect(cx, y + 4, cw, TRACK_H - 12);
      g.strokeStyle = isSel ? "#fff" : tr.color;
      g.lineWidth = isSel ? 2 : 1;
      g.strokeRect(cx + .5, y + 4.5, cw - 1, TRACK_H - 13);

      const wf = waveCache.get(key(c));
      if (wf) drawClipWave(g, wf, c, cx, cw, y + 8, TRACK_H - 20, tr.color);
      drawFades(g, c, cx, cw, y + 4, TRACK_H - 12, isSel);

      g.fillStyle = "#cfd6e4"; g.font = "10px system-ui";
      const w = c.warp || [];
      const semis = c.pitch ? `  ·  ${c.pitch > 0 ? "+" : ""}${c.pitch.toFixed(0)} st` : "";
      const tag = w.length > 2 ? `  ·  warped (${w.length} pins)`
                : w.length === 2 ? `  ·  ${(100 * speedOf(c)).toFixed(1)}% speed` : "";
      // the label sticks to the visible edge when the clip starts off-screen
      g.fillText(c.name.slice(0, 28) + tag + semis, Math.max(cx, HEAD_W) + 6, y + 16);
      drawWarpPins(g, c, y + 4, TRACK_H - 12);
    }
    g.restore();
  });

  // playhead
  const t = currentTime();
  const px = x(t);
  if (px >= HEAD_W) drawPlayhead(g, px, H, W);
  $("time").textContent = fmt(t);
  updateScrollbar();
  showBpm();
  drawMasterMeter();
}

// The playhead is a "funnel": a wide triangular handle sitting in the ruler
// that tapers into a long thin line running down the tracks. The bare 2px line
// was technically draggable and practically a dart throw — the handle gives you
// ~16px to aim at, and makes it look grabbable in the first place.
function drawPlayhead(g, px, H, W) {
  const held = drag && drag.mode === "playhead";
  const col = held ? "#4da3ff" : "#fff";
  g.save();
  // clip so the handle can't spill left over the track headers
  g.beginPath(); g.rect(HEAD_W, 0, W - HEAD_W, H); g.clip();

  g.strokeStyle = col; g.lineWidth = 2;              // the pipe
  g.beginPath(); g.moveTo(px, 0); g.lineTo(px, H); g.stroke();

  g.fillStyle = col;                                 // the funnel
  g.beginPath();
  g.moveTo(px - PH_W, 0);
  g.lineTo(px + PH_W, 0);
  g.lineTo(px, PH_HEAD_H);
  g.closePath(); g.fill();
  g.restore();
}

// Warp pins live in a strip along the bottom of the clip: a small handle with
// a hairline up through the waveform, so you can see what a pin is holding.
function drawWarpPins(g, c, y, h) {
  const list = pinsInWindow(c);
  if (!list.length) return;
  const base = y + h;
  for (const { t } of list) {
    const px = HEAD_W + (t - scrollX) * pxPerSec;
    if (px < HEAD_W - 6 || px > g.canvas.clientWidth + 6) continue;
    g.strokeStyle = "rgba(255,214,102,.35)"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(px, y); g.lineTo(px, base - PIN_H); g.stroke();
    g.fillStyle = "#ffd666";
    g.beginPath();                               // a house-shaped handle
    g.moveTo(px, base - PIN_H);
    g.lineTo(px + PIN_W, base - PIN_H + 5);
    g.lineTo(px + PIN_W, base);
    g.lineTo(px - PIN_W, base);
    g.lineTo(px - PIN_W, base - PIN_H + 5);
    g.closePath(); g.fill();
  }
}

function drawFades(g, c, cx, cw, y, h, isSel) {
  // A fade is drawn as the region the ramp silences: a wedge from the clip
  // edge up to where the fade completes. Dimming that area shows the shape
  // without hiding the waveform underneath.
  const fi = Math.min(c.fade_in  * pxPerSec, cw);
  const fo = Math.min(c.fade_out * pxPerSec, cw);
  g.save();
  g.fillStyle = "rgba(10,12,16,.60)";
  if (fi > 1) {
    g.beginPath(); g.moveTo(cx, y); g.lineTo(cx + fi, y); g.lineTo(cx, y + h);
    g.closePath(); g.fill();
  }
  if (fo > 1) {
    g.beginPath(); g.moveTo(cx + cw, y); g.lineTo(cx + cw - fo, y);
    g.lineTo(cx + cw, y + h); g.closePath(); g.fill();
  }
  // handles: small squares at the top corners, offset by the current fade
  const hs = isSel ? 7 : 5;
  g.fillStyle = isSel ? "#ffffff" : "rgba(255,255,255,.55)";
  g.fillRect(cx + fi - hs / 2, y - 1, hs, hs);
  g.fillRect(cx + cw - fo - hs / 2, y - 1, hs, hs);
  g.restore();
}

function drawPill(g, px, py, label, on, color) {
  g.fillStyle = on ? color : "#2a2f3a";
  g.beginPath(); g.roundRect(px, py, 24, 16, 4); g.fill();
  g.fillStyle = on ? "#111" : "#8b93a3";
  g.font = "600 10px system-ui";
  g.fillText(label, px + 8, py + 12);
}

function drawClipWave(g, wf, c, cx, cw, y, h, color) {
  const mid = y + h / 2, amp = h / 2 - 2;
  const n = wf.min.length;
  const base = wf.base || 0;
  const i0 = Math.floor(((c.offset - base) / wf.duration) * n);
  const i1 = Math.ceil(((c.offset - base + c.length) / wf.duration) * n);
  const span = Math.max(1, i1 - i0);
  g.fillStyle = color + "cc";
  const step = Math.max(1, Math.floor(span / Math.max(1, cw)));
  for (let px = 0; px < cw; px++) {
    const i = i0 + Math.floor((px / cw) * span);
    if (i < 0 || i >= n) continue;
    let lo = wf.min[i], hi = wf.max[i];
    for (let k = 1; k < step && i + k < n; k++) {
      lo = Math.min(lo, wf.min[i + k]); hi = Math.max(hi, wf.max[i + k]);
    }
    g.fillRect(cx + px, mid - hi * amp, 1, Math.max(1, (hi - lo) * amp));
  }
}

// ---------------------------------------------------------------- playback
function currentTime() {
  if (!playing) return playOffset;
  return playOffset + (actx.currentTime - playStart);
}

// Build and start one clip's nodes: source -> gain (with fades) -> pan -> out.
// Live playback and the offline check (previewOffline) both call this, so the
// check measures the real code path, not a re-implementation of it.
// One bus per audible track: every clip on it feeds the same gain -> pan
// chain, so volume and pan act on the track as a whole and the meter reads
// exactly what you hear. (Volume used to be multiplied into each clip's own
// gain node, which left nowhere to measure the track.)
function makeBus(ctx, tr, dest, metered) {
  const gain = ctx.createGain(); gain.gain.value = tr.volume;
  const pan = ctx.createStereoPanner(); pan.pan.value = tr.pan;
  gain.connect(pan);
  let analyser = null;
  if (metered) {
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;          // 46 ms — longer than a frame, so no peak slips past
    pan.connect(analyser); analyser.connect(dest);
  } else {
    pan.connect(dest);
  }
  return { gain, pan, analyser, data: analyser ? new Float32Array(analyser.fftSize) : null };
}

function scheduleClip(ctx, out, tr, c, t0, startTime) {
  const { buffer, base } = bufCache.get(key(c));
  const sr = buffer.sampleRate;
  const skip = Math.max(0, t0 - c.start);            // how far into the clip we begin
  const dur = c.length - skip;
  if (dur <= 0) return null;

  const src = ctx.createBufferSource();
  src.buffer = buffer;
  const gain = ctx.createGain();
  src.connect(gain).connect(out);                    // `out` is the track's bus

  // The rendered audio starts at `base` in warped-file time, not at 0.
  // Both the offset and the clip's position are whole samples, the same way
  // the export reads them (render.py _read_clip).
  const into = Math.max(0, Math.round((c.offset - base + skip) * sr) / sr);
  const at = startTime + Math.round(Math.max(0, c.start - t0) * sr) / sr;

  // Fades: the same straight-line ramps render.py applies.
  const g = c.gain;                                  // track volume lives on the bus
  const fi = Math.min(c.fade_in || 0, c.length), fo = Math.min(c.fade_out || 0, c.length);
  const envAt = (x) => Math.max(0, Math.min(1, fi > 0 ? x / fi : 1, fo > 0 ? (c.length - x) / fo : 1));
  gain.gain.setValueAtTime(g * envAt(skip), at);
  if (skip < fi) gain.gain.linearRampToValueAtTime(g, at + (fi - skip));
  if (fo > 0) {
    if (skip < c.length - fo) gain.gain.setValueAtTime(g, at + (c.length - fo - skip));
    gain.gain.linearRampToValueAtTime(0, at + dur);
  }
  src.start(at, into, dur);
  return src;
}

// Render what live playback would produce, offline, through scheduleClip.
// Used to prove preview == export against the browser's real audio engine.
async function previewOffline(seconds, sr = 44100) {
  const soloed = project.tracks.some(t => t.solo);
  const ctx = new OfflineAudioContext(2, Math.ceil(seconds * sr), sr);
  const masterOut = ctx.createGain();
  masterOut.gain.value = Math.pow(10, (project.master_db || 0) / 20);
  masterOut.connect(ctx.destination);
  for (const tr of project.tracks) {
    if (tr.mute || (soloed && !tr.solo)) continue;
    const bus = makeBus(ctx, tr, masterOut, false);
    for (const c of tr.clips) { await getBuffer(c); scheduleClip(ctx, bus.gain, tr, c, 0, 0); }
  }
  return ctx.startRendering();
}

let starting = false;   // true while play() is waiting on buffers

async function play() {
  if (!project || playing || starting) return;   // a second press mid-load would double the audio
  follow = true;      // pressing play means "show me what's playing"
  actx = actx || makeContext();
  await actx.resume();
  const t0 = playOffset;
  const soloed = project.tracks.some(t => t.solo);
  const jobs = [];
  for (const tr of project.tracks) {
    if (tr.mute || (soloed && !tr.solo)) continue;
    for (const c of tr.clips) if (c.start + c.length > t0) jobs.push({ tr, c });
  }
  const pending = jobs.filter(j => !bufCache.has(key(j.c))).length;
  if (pending) setStatus(`loading ${pending} clip${pending > 1 ? "s" : ""}…`);
  starting = true;
  try { await Promise.all(jobs.map(j => getBuffer(j.c))); }
  catch (e) { setStatus(`can't play: ${e.message}`); return; }
  finally { starting = false; }
  if (pending) setStatus("ready");

  playStart = actx.currentTime;
  playing = true;
  liveNodes = [];

  master = (() => {
    const gain = actx.createGain();
    gain.gain.value = Math.pow(10, (project.master_db || 0) / 20);
    const analyser = actx.createAnalyser(); analyser.fftSize = 2048;
    gain.connect(analyser); analyser.connect(actx.destination);
    return { gain, analyser, data: new Float32Array(analyser.fftSize) };
  })();
  buses = {};
  for (const { tr } of jobs) if (!buses[tr.id]) buses[tr.id] = makeBus(actx, tr, master.gain, true);
  for (const { tr, c } of jobs) {
    const src = scheduleClip(actx, buses[tr.id].gain, tr, c, t0, playStart);
    if (src) liveNodes.push(src);
  }
  $("play").textContent = "Pause";
  tick();
}

function pause() {
  if (!playing) return;
  playOffset = currentTime();
  liveNodes.forEach(n => { try { n.stop(); } catch (e) {} });
  liveNodes = [];
  buses = {}; master = null;
  playing = false;
  silenceMeters();                 // nothing is playing; don't leave bars frozen mid-air
  $("play").textContent = "Play";
  render();
}

function stopAll() {
  // Stop returns the playhead to the start — so the view goes with it,
  // rather than leaving you staring at wherever playback had paged to.
  pause(); playOffset = 0; setScroll(0); render();
}

// Jump to the top and play. Because audio nodes are single-use, "seeking"
// always means: tear the old ones down, move the marker, build new ones.
async function restart() {
  pause();            // stop + destroy the current nodes
  playOffset = 0;     // move the marker to the beginning
  await play();       // build fresh nodes starting from 0
}

// Keep the playhead visible while playing. This "pages" the view the way
// Ableton does: when the playhead crosses the right edge we jump the window
// forward so it reappears near the LEFT, rather than sliding the timeline
// continuously under it. Paging redraws once every screenful instead of every
// frame, and a timeline that slides on every frame is hard to read.
function followPlayhead() {
  if (!follow) return;
  const viewW = ($("timeline").clientWidth - HEAD_W) / pxPerSec;  // seconds on screen
  if (viewW <= 0) return;
  const t = currentTime();
  const lead = viewW * 0.08;      // leave a little context behind the playhead

  if (t > scrollX + viewW - lead) scrollX = Math.max(0, t - lead);
  else if (t < scrollX) scrollX = Math.max(0, t - lead);  // seeked/scrolled behind it
}

/* ================================================================
   LEVEL METERS
   Peak metering, read straight off the audio graph. Numbers chosen the way
   hardware meters behave: the bar falls at a fixed rate so you can read it,
   and the loudest recent peak hangs for a moment so a brief spike doesn't
   vanish before you see it.
   ================================================================ */
const METER_FLOOR = -60;        // dB at the bottom of the bar
const METER_FALL = 0.6;         // dB per frame ≈ 36 dB/s
const HOLD_MS = 1200;

function meterOf(id) {
  return meters[id] || (meters[id] = { peak: -Infinity, hold: -Infinity, holdUntil: 0, clipped: false });
}

function readMeter(id, bus, now) {
  const m = meterOf(id);
  if (!bus || !bus.analyser) { m.peak = Math.max(METER_FLOOR, m.peak - METER_FALL * 3); return m; }
  bus.analyser.getFloatTimeDomainData(bus.data);
  let pk = 0;
  for (let i = 0; i < bus.data.length; i++) { const v = Math.abs(bus.data[i]); if (v > pk) pk = v; }
  const db = pk > 0 ? 20 * Math.log10(pk) : -Infinity;
  m.peak = Math.max(db, m.peak - METER_FALL);       // instant attack, slow fall
  if (db >= m.hold || now > m.holdUntil) { m.hold = db; m.holdUntil = now + HOLD_MS; }
  if (pk >= 0.999) m.clipped = true;                // latches until you click it
  return m;
}

function readMeters() {
  const now = performance.now();
  for (const tr of project ? project.tracks : []) readMeter(tr.id, buses[tr.id], now);
  readMeter("master", master, now);
}

function silenceMeters() {
  for (const m of Object.values(meters)) { m.peak = -Infinity; m.hold = -Infinity; }
}

// dB -> 0..1 up the bar
const meterFrac = (db) => Math.max(0, Math.min(1, (db - METER_FLOOR) / -METER_FLOOR));
const meterColor = (db) => db >= -3 ? "#ff6b6b" : db >= -12 ? "#ffd43b" : "#3ddc84";

function drawMeter(g, x, y, w, h, m, vertical = true) {
  g.fillStyle = "#101318";
  g.fillRect(x, y, w, h);
  const f = meterFrac(m.peak);
  if (f > 0) {
    g.fillStyle = meterColor(m.peak);
    if (vertical) g.fillRect(x, y + h * (1 - f), w, h * f);
    else g.fillRect(x, y, w * f, h);
  }
  if (isFinite(m.hold) && m.hold > METER_FLOOR) {          // the recent loudest, held
    const hf = meterFrac(m.hold);
    g.fillStyle = meterColor(m.hold);
    if (vertical) g.fillRect(x, y + h * (1 - hf) - 1, w, 2);
    else g.fillRect(x + w * hf - 2, y, 2, h);
  }
  if (m.clipped) {                                          // click it to clear
    g.fillStyle = "#ff3b3b";
    if (vertical) g.fillRect(x, y, w, 3); else g.fillRect(x + w - 3, y, 3, h);
  }
}

// Click the master meter: set the fader, or have mixr measure the mix and
// set it for you. Peak is measured by rendering the project offline through
// the very same graph playback uses, so the number is the real one.
async function masterMenu(px, py) {
  const cur = project.master_db || 0;
  openMenu(px, py, [
    { slider: true, label: "Master", min: -24, max: 12, step: 0.5, value: cur,
      fmt: v => (v > 0 ? "+" : "") + v.toFixed(1) + " dB",
      oninput: (v) => { pendingMaster = v; } },
    { sep: true },
    { label: "Fit to −1 dBFS (measure the mix)", run: fitMaster },
    { label: "Reset to 0 dB", disabled: cur === 0, run: () => setMaster(0) },
    { sep: true },
    { label: "Clear clip warnings", run: () => { for (const m of Object.values(meters)) m.clipped = false; render(); } },
  ], "Master level");
}

let pendingMaster = null;
window.addEventListener("mouseup", async () => {
  if (pendingMaster === null) return;
  const v = pendingMaster; pendingMaster = null;
  await setMaster(v);
});

async function setMaster(db) {
  project = await post("/api/project/master", { db });
  if (master) master.gain.gain.value = Math.pow(10, (project.master_db || 0) / 20);
  render();
  setStatus(`master ${project.master_db > 0 ? "+" : ""}${project.master_db.toFixed(1)} dB`);
}

async function fitMaster() {
  if (!project.tracks.some(t => t.clips.length)) return;
  setStatus("measuring the mix…");
  const end = Math.max(...project.tracks.flatMap(t => t.clips.map(clipEnd)), 1);
  const buf = await previewOffline(end + 0.2);
  let pk = 0;
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < d.length; i++) { const v = Math.abs(d[i]); if (v > pk) pk = v; }
  }
  if (pk <= 0) { setStatus("silence — nothing to measure"); return; }
  const current = project.master_db || 0;
  const target = current + (-1 - 20 * Math.log10(pk));      // peak -> -1 dBFS
  await setMaster(Math.max(-24, Math.min(12, target)));
  setStatus(`mix peaked at ${(20 * Math.log10(pk)).toFixed(1)} dBFS → master ${project.master_db.toFixed(1)} dB`);
}

function drawMasterMeter() {
  const cv = $("mastermeter");
  if (!cv) return;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawMeter(g, 0, 0, w, h, meterOf("master"), false);
}

function tick() {
  if (!playing) return;
  readMeters();
  followPlayhead();
  render();
  requestAnimationFrame(tick);
}

// ---------------------------------------------------------------- hit test
function hit(mx, my) {
  if (!project) return null;
  const i = Math.floor((my - RULER_H) / TRACK_H);
  if (i < 0 || i >= project.tracks.length) return null;
  const tr = project.tracks[i];
  const y = RULER_H + i * TRACK_H;
  if (mx < HEAD_W) {
    if (my >= y + 32 && my <= y + 48) {
      if (mx >= 10 && mx <= 34) return { kind: "mute", track: tr };
      if (mx >= 42 && mx <= 66) return { kind: "solo", track: tr };
    }
    if (my >= y + 58 && my <= y + 72 && mx >= 10 && mx <= 170)
      return { kind: "volume", track: tr };
    if (mx >= HEAD_W - 20) return { kind: "meter", track: tr };
    return { kind: "header", track: tr };
  }
  const t = scrollX + (mx - HEAD_W) / pxPerSec;
  for (const c of tr.clips) {
    if (t >= c.start && t <= clipEnd(c)) {
      const edge = 6 / pxPerSec;
      // top strip of the clip = fade handles (checked BEFORE trim so the
      // corners aren't ambiguous)
      // bottom strip = warp pins, checked first: it's their only grab area
      if (my - y > TRACK_H - 26) {
        const grab = 7 / pxPerSec;
        const near = pinsInWindow(c).find(o => Math.abs(t - o.t) < grab);
        if (near) return { kind: "warp-pin", track: tr, clip: c, t, pin: near.i };
        return { kind: "pin-strip", track: tr, clip: c, t };
      }
      const topStrip = my - y < 18;
      if (topStrip) {
        const grab = 9 / pxPerSec;
        if (Math.abs(t - (c.start + c.fade_in)) < grab)
          return { kind: "fade-in", track: tr, clip: c, t };
        if (Math.abs(t - (clipEnd(c) - c.fade_out)) < grab)
          return { kind: "fade-out", track: tr, clip: c, t };
      }
      if (t < c.start + edge) return { kind: "trim-left", track: tr, clip: c, t };
      if (t > clipEnd(c) - edge) return { kind: "trim-right", track: tr, clip: c, t };
      return { kind: "clip", track: tr, clip: c, t };
    }
  }
  return { kind: "empty", track: tr, t };
}

// ---------------------------------------------------------------- mouse
let drag = null;

$("timeline").addEventListener("mousedown", async (e) => {
  const r = e.target.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  if (my < RULER_H) {
    // TOUCH POINT 1 of 3 — begin a playhead drag.
    // Remember whether we were playing so mouseup can resume, then stop audio
    // for the duration of the drag (re-seeking every frame would stutter).
    playheadDragStart(mx);
    return;
  }
  const h = hit(mx, my);
  if (!h) return;

  if (h.kind === "mute" || h.kind === "solo") {
    const patch = h.kind === "mute" ? { mute: !h.track.mute } : { solo: !h.track.solo };
    project = await post(`/api/track/update?track=${h.track.id}`, patch);
    if (playing) { pause(); play(); }
    render(); return;
  }
  if (h.kind === "meter") {                 // clear a latched clip warning
    meterOf(h.track.id).clipped = false;
    meterOf("master").clipped = false;
    render(); return;
  }
  if (h.kind === "volume") {
    const v = Math.max(0, Math.min(1.5, (mx - 10) / 160));
    project = await post(`/api/track/update?track=${h.track.id}`, { volume: v });
    render(); return;
  }
  if (h.kind === "warp-pin") {
    selectOnly(h.track.id, h.clip.id);
    if (e.altKey) {                               // alt-click removes a pin
      const pins = h.clip.warp.filter((_, i) => i !== h.pin);
      await applyWarp(h.track, h.clip, { warp: pins });
      return;
    }
    // Dragging re-renders audio (seconds), so the map is only sent on mouseup.
    drag = { mode: "warp-pin", track: h.track, clip: h.clip, pin: h.pin,
             before: JSON.parse(JSON.stringify(h.clip.warp)) };
    render(); return;
  }
  if (h.kind === "pin-strip") {
    selectOnly(h.track.id, h.clip.id);
    render(); return;
  }
  if (h.kind === "clip") {
    if (e.shiftKey) { selectToggle(h.track.id, h.clip.id); render(); return; }
    // clicking a clip that's already in a multi-selection keeps the group,
    // so you can drag several clips at once
    if (!isSelected(h.clip.id)) selectOnly(h.track.id, h.clip.id);
    else selected = { track: h.track.id, clip: h.clip.id };
    drag = { mode: "move", track: h.track, clip: h.clip,
             grab: h.t - h.clip.start, startVal: h.clip.start,
             group: selectedClips().map(({ c }) => ({ c, start: c.start })) };
    render(); return;
  }
  if (h.kind === "fade-in" || h.kind === "fade-out") {
    selectOnly(h.track.id, h.clip.id);
    drag = { mode: h.kind, track: h.track, clip: h.clip,
             startVal: { fade_in: h.clip.fade_in, fade_out: h.clip.fade_out } };
    render(); return;
  }
  // --- clip edges ---
  if (h.kind === "trim-left" || h.kind === "trim-right") {
    selectOnly(h.track.id, h.clip.id);
    drag = { mode: h.kind, track: h.track, clip: h.clip,
             startVal: { start: h.clip.start, offset: h.clip.offset, length: h.clip.length },
             grabT: h.t };
    render(); return;
  }
  clearSelection(); render();
});

// Hover feedback. The window-level mousemove below only runs mid-drag, so the
// canvas cursor never changed; over the ruler it should read as scrubbable.
$("timeline").addEventListener("mousemove", (e) => {
  if (drag) return;                       // mid-drag the cursor stays put
  const r = $("timeline").getBoundingClientRect();
  $("timeline").style.cursor = (e.clientY - r.top) < RULER_H ? "ew-resize" : "default";
});

window.addEventListener("mousemove", (e) => {
  if (!drag) return;
  const r = $("timeline").getBoundingClientRect();
  const mx = e.clientX - r.left;
  const t = scrollX + (mx - HEAD_W) / pxPerSec;

  // TOUCH POINT 2 of 3 — while dragging the playhead, just move the marker.
  if (drag.mode === "playhead") { playheadDragMove(t); return; }

  if (drag.mode === "warp-pin") {
    // Move this pin only. Its neighbours hold, so the audio either side of it
    // stretches — which is exactly what a warp marker does.
    const c = drag.clip;
    const dst = snap(t) - c.start + c.offset;
    const lo = drag.pin > 0 ? c.warp[drag.pin - 1][1] + 0.05 : -1e9;
    const hi = drag.pin < c.warp.length - 1 ? c.warp[drag.pin + 1][1] - 0.05 : 1e9;
    c.warp[drag.pin][1] = Math.max(lo, Math.min(hi, dst));
    render();
    return;
  }
  if (drag.mode === "move") {
    let ns = Math.max(0, t - drag.grab);
    ns = snap(ns);
    // everything selected moves together, by the same amount
    const delta = ns - drag.startVal;
    for (const g of drag.group) g.c.start = Math.max(0, g.start + delta);
    render();
  } else if (drag.mode === "trim-left" || drag.mode === "trim-right") {
    trimDrag(drag, t);
    render();
  } else if (drag.mode === "fade-in" || drag.mode === "fade-out") {
    fadeDrag(drag, t);
    render();
  }
});

window.addEventListener("mouseup", async () => {
  if (!drag) return;

  // TOUCH POINT 3 of 3 — a playhead drag has no clip to save, so handle it
  // here and return BEFORE the clip-update code below (which would crash).
  if (drag.mode === "playhead") { await playheadDragEnd(); return; }

  if (drag.mode === "warp-pin") {
    const { track, clip, before } = drag;
    const pins = clip.warp;
    drag = null;
    clip.warp = before;                    // let the server be the one to change it
    await applyWarp(track, clip, { warp: pins });
    return;
  }

  const { track, clip, mode, group } = drag;
  drag = null;
  if (mode === "move" && group && group.length > 1) {
    project = await post("/api/clips/update", {
      updates: group.map(({ c }) => ({
        track: project.tracks.find(t2 => t2.clips.some(x => x.id === c.id)).id,
        clip: c.id, patch: { start: c.start } })) });
    render(); return;
  }
  const payload = { start: clip.start, offset: clip.offset, length: clip.length,
                    fade_in: clip.fade_in, fade_out: clip.fade_out };
  project = await post(`/api/clip/update?track=${track.id}&clip=${clip.id}`, payload);
  render();
});

/* Dragging a clip edge resizes the WINDOW, never the audio.

   Right edge: only `length` changes.
   Left edge: `start` moves, `offset` moves by the same amount so the audio
   stays put, and `length` shrinks by that amount. Guarded against negative
   length, negative offset, and dragging an edge past its opposite. */
function trimDrag(d, t) {
  const MIN = 0.05;  // minimum length of a clip in seconds
  const ns = Math.max(0, snap(t));    // clamp FIRST
  const delta = ns - d.startVal.start;        // now everything derives from the same number
  if (d.mode === "trim-left") {
    d.clip.start = ns;
    d.clip.offset = d.startVal.offset + delta;
    d.clip.length = d.startVal.length - delta;
    if (d.clip.length < MIN) {
      d.clip.length = MIN;
      d.clip.offset = d.startVal.offset + d.startVal.length;
    }
    if (d.clip.offset < 0) {
      d.clip.offset = 0;
      d.clip.start = d.startVal.start - d.startVal.offset;
      d.clip.length = d.startVal.length - (d.clip.start - d.startVal.start);
    }
  } else if (d.mode === "trim-right") {
    const newLength = snap(t) - d.clip.start;
    d.clip.length = Math.max(MIN, newLength);
  }
}

/* Dragging the playhead, in the usual three phases: mousedown captures state,
   mousemove updates it, mouseup commits it. Audio is stopped for the duration
   of the drag because re-seeking every frame would stutter. */
function playheadDragStart(mx) {
  const seconds = scrollX + (mx - HEAD_W) / pxPerSec;
  // Snapshot BEFORE pause() — it sets playing = false, so reading `playing`
  // afterwards always yields false and playback would never resume.
  const wasPlaying = playing;
  if (wasPlaying) pause();

  playOffset = Math.max(0, seconds);
  drag = { mode: "playhead", wasPlaying };
  render();
}

function playheadDragMove(t) {
  playOffset = Math.max(0, t);
  render();
}

async function playheadDragEnd() {
  if (drag.wasPlaying) {          // resume from where it was dropped
    await play();
  }
  drag = null;
  render();
}



/* ================================================================
   UNDO / REDO
   The server owns history — it already owns the project, so keeping the two
   together means the browser can never disagree about what "one step back" is.
   ================================================================ */
async function doUndo() {
  try {
    const r = await post("/api/undo");
    project = r.project; clearSelection(); render();
    await ensureWaves();
    setStatus(`undo · ${r.undo} left`);
  } catch (e) { setStatus("nothing to undo"); }
}

async function doRedo() {
  try {
    const r = await post("/api/redo");
    project = r.project; clearSelection(); render();
    await ensureWaves();
    setStatus(`redo · ${r.redo} left`);
  } catch (e) { setStatus("nothing to redo"); }
}

// undo can resurrect a clip whose waveform we never fetched (or dropped)
async function ensureWaves() {
  const seen = new Set();
  for (const tr of project.tracks) for (const c of tr.clips) {
    const k = key(c);
    if (seen.has(k) || waveCache.has(k)) continue;
    seen.add(k);
    try { await getWave(c); render(); } catch (e) {}
  }
}

/* ================================================================
   SAVE / OPEN / AUTOSAVE
   The project lives in server memory, so it survives a page reload but NOT a
   server restart. These write it to disk as JSON — which is cheap, because a
   project is just numbers and file references, never audio.
   ================================================================ */
let lastAutosave = "";          // serialized project at the last autosave

async function saveProject(askName = false) {
  if (!project) return;
  let name = project.name;
  if (askName || !name || name === "Untitled") {
    name = prompt("Save project as:", name === "Untitled" ? "My mix" : name);
    if (!name) return;
  }
  try {
    const r = await post(`/api/project/save?name=${encodeURIComponent(name)}`);
    project.name = r.name;
    lastAutosave = JSON.stringify(project);
    setStatus(`saved "${r.saved}"`);
    updateTitle();
  } catch (e) { setStatus(`save failed: ${e.message}`); }
}

async function openProjectByName(file) {
  stopAll();
  project = await post(`/api/project/open?name=${encodeURIComponent(file)}`);
  clearSelection(); scrollX = 0; playOffset = 0;
  bufCache.clear();
  render();
  setStatus(`loading waveforms…`);
  // pull the waveform for every distinct file so clips draw
  const seen = new Set();
  for (const tr of project.tracks) {
    for (const c of tr.clips) {
      const k = key(c);
      if (seen.has(k)) continue;
      seen.add(k);
      try { await getWave(c); } catch (e) { /* missing file */ }
      render();
    }
  }
  lastAutosave = JSON.stringify(project);
  updateTitle();
  setStatus(`opened "${project.name}"`);
}

async function openMenuProjects(px, py) {
  const { projects, autosave } = await api("/api/project/list");
  const items = [];
  if (!projects.length && !autosave) {
    items.push({ label: "No saved projects yet", disabled: true });
  }
  if (autosave) {
    items.push({ label: `↺ Restore autosave (${autosave.tracks} tracks)`,
                 run: () => openProjectByName("__autosave") });
    items.push({ sep: true });
  }
  for (const pr of projects) {
    const when = new Date(pr.modified * 1000);
    const ago = when.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    items.push({
      label: `${pr.name}  ·  ${pr.tracks} tracks  ·  ${ago}`,
      run: () => openProjectByName(pr.file),
    });
  }
  items.push({ sep: true });
  items.push({ label: "Save as…", run: () => saveProject(true) });
  if (projects.length) {
    items.push({ label: "Delete a project…", danger: true, run: async () => {
      const which = prompt("Delete which project? (exact name)\n\n" +
                           projects.map(p => p.file).join("\n"));
      if (!which) return;
      try {
        await post(`/api/project/delete?name=${encodeURIComponent(which)}`);
        setStatus(`deleted "${which}"`);
      } catch (e) { setStatus(`delete failed: ${e.message}`); }
    }});
  }
  // Disk. The cache is only rebuildable audio, so clearing it costs time, not
  // work — worth saying out loud, since the number gets big.
  try {
    const cs = await api("/api/cache");
    items.push({ sep: true });
    items.push({ label: `Cache: ${(cs.bytes / 1e9).toFixed(2)} GB of rebuildable audio`,
                 disabled: true });
    items.push({ label: "Free up disk (keeps every project and stem)", run: async () => {
      setStatus("clearing cached audio…");
      const r = await post("/api/cache/clear?kind=renders");
      bufCache.clear(); waveCache.clear();
      await ensureWaves(); render();
      setStatus(`freed ${(r.freed / 1e9).toFixed(2)} GB — clips will re-render as you play them`);
    }});
  } catch (e) { /* disk info is a nicety; never block opening a project */ }

  openMenu(px, py, items, "Projects");
}

function updateTitle() {
  $("projName").textContent = project ? project.name : "—";
  document.title = project && project.name !== "Untitled"
    ? `${project.name} — mixr` : "mixr";
}

// Autosave: only writes when something actually changed, so it is nearly free.
setInterval(async () => {
  if (!project || !Array.isArray(project.tracks) || !project.tracks.length) return;
  const snap = JSON.stringify(project);
  if (snap === lastAutosave) return;
  lastAutosave = snap;
  try {
    await post("/api/project/save?name=__autosave&rename=false");
    $("saved").textContent = "autosaved";
    setTimeout(() => { $("saved").textContent = ""; }, 1600);
  } catch (e) { /* keep quiet; the manual Save button reports errors */ }
}, 8000);

// cmd/ctrl+S saves
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const mod = e.metaKey || e.ctrlKey;
  if (mod && (e.key === "s" || e.key === "S")) { e.preventDefault(); saveProject(); }
  if (mod && (e.key === "z" || e.key === "Z")) {
    e.preventDefault();
    e.shiftKey ? doRedo() : doUndo();
  }
  if (mod && (e.key === "y" || e.key === "Y")) { e.preventDefault(); doRedo(); }
  if (mod && (e.key === "a" || e.key === "A")) { e.preventDefault(); selectAll(); }
  if (mod && (e.key === "c" || e.key === "C")) { e.preventDefault(); copySelection(); }
  if (mod && (e.key === "x" || e.key === "X")) { e.preventDefault(); copySelection(true); }
  if (mod && (e.key === "v" || e.key === "V")) { e.preventDefault(); pasteClipboard(); }
  if (mod && (e.key === "d" || e.key === "D")) { e.preventDefault(); duplicateSelection(); }
  if (e.key === "Home") {                     // back to the top
    e.preventDefault();
    if (playing) restart(); else { playOffset = 0; }
    setScroll(0); render();
  }
  if (e.key === "End") { e.preventDefault(); setScroll(maxScroll()); follow = false; render(); }
});

/* ================================================================
   ARRANGEMENT EDITING
   Multi-clip actions go through the batch endpoints, so each one is a single
   undo step: pasting six clips undoes as "paste", not six separate adds.
   ================================================================ */
// One bar if the project has a tempo, otherwise a second.
const gridStep = () => (project && project.bpm ? 240 / project.bpm : 1);

// The fields that make a clip what it is — everything except where it sits.
const clipBody = (c) => ({
  source: c.source, file: c.file, name: c.name, offset: c.offset, length: c.length,
  warp: c.warp, warp_mode: c.warp_mode, pitch: c.pitch,
  gain: c.gain, fade_in: c.fade_in, fade_out: c.fade_out,
});

async function deleteSelection() {
  const items = selection.map(s => ({ track: s.track, clip: s.clip }));
  project = await post("/api/clips/remove", { items });
  const n = items.length;
  clearSelection(); render();
  setStatus(`removed ${n} clip${n > 1 ? "s" : ""}`);
}

async function nudgeSelection(dt) {
  const moved = selectedClips();
  if (!moved.length) return;
  if (dt < 0 && moved.some(({ c }) => c.start + dt < 0)) return;   // don't pile up at zero
  for (const { c } of moved) c.start += dt;
  render();
  project = await post("/api/clips/update", {
    coalesce: true,                       // a run of nudges is one undo step
    updates: moved.map(({ tr, c }) => ({ track: tr.id, clip: c.id, patch: { start: c.start } })),
  });
  render();
}

function copySelection(cut = false) {
  const picked = selectedClips();
  if (!picked.length) return;
  const anchor = Math.min(...picked.map(({ c }) => c.start));
  clipboard = picked.map(({ tr, c }) => ({ track: tr.id, dt: c.start - anchor, ...clipBody(c) }));
  setStatus(`${cut ? "cut" : "copied"} ${picked.length} clip${picked.length > 1 ? "s" : ""}`);
  if (cut) return deleteSelection();
}

// Paste lands at the playhead, keeping the clips' spacing. A clip whose track
// is gone goes to the track of the last thing you clicked, or the first track.
async function pasteClipboard(at = null, from = clipboard) {
  if (!from.length || !project.tracks.length) return;
  const start = at !== null ? at : currentTime();
  const fallback = (selected && selected.track) || project.tracks[0].id;
  const clips = from.map(c => ({
    ...c, track: project.tracks.some(t2 => t2.id === c.track) ? c.track : fallback,
    start: Math.max(0, start + c.dt),
  }));
  const r = await post("/api/clips/add", { clips });
  project = r.project;
  selection = r.clips.map((id, i) => ({ track: clips[i].track, clip: id }));
  selected = selection[selection.length - 1] || null;
  render();
  await ensureWaves(); render();
  setStatus(`pasted ${clips.length} clip${clips.length > 1 ? "s" : ""}`);
}

// Duplicate drops a copy immediately after the selection, the way Ableton does.
async function duplicateSelection() {
  const picked = selectedClips();
  if (!picked.length) return;
  const anchor = Math.min(...picked.map(({ c }) => c.start));
  const span = Math.max(...picked.map(({ c }) => clipEnd(c))) - anchor;
  const copies = picked.map(({ tr, c }) => ({ track: tr.id, dt: c.start - anchor, ...clipBody(c) }));
  await pasteClipboard(anchor + span, copies);
}

function selectAll() {
  selection = project.tracks.flatMap(tr => tr.clips.map(c => ({ track: tr.id, clip: c.id })));
  selected = selection[selection.length - 1] || null;
  render();
  setStatus(`${selection.length} clips selected`);
}

/* ================================================================
   EXPORT
   Rendering runs on a background thread server-side (a long mix can take a
   while), so we poll — same pattern as stem separation.
   ================================================================ */
async function exportMix() {
  if (!project || !project.tracks.some(t => t.clips.length)) {
    setStatus("nothing to export yet"); return;
  }
  const name = (project.name && project.name !== "Untitled")
    ? project.name : "mixr-export";
  $("export").disabled = true;
  setStatus("rendering…");
  try {
    const { job } = await post(`/api/export/start?name=${encodeURIComponent(name)}&fmt=wav`);
    let st;
    for (let i = 0; i < 600; i++) {
      st = await api(`/api/export/status?job=${job}`);
      if (st.state === "done") break;
      if (st.state === "error") throw new Error(st.error);
      setStatus(`rendering… ${Math.round((st.progress || 0) * 100)}%`);
      await new Promise(r => setTimeout(r, 700));
    }
    if (!st || st.state !== "done") throw new Error("render timed out");

    // hand the file to the browser as a download
    const a = document.createElement("a");
    a.href = `/api/export/download?file=${encodeURIComponent(st.file)}`;
    a.download = st.file;
    document.body.appendChild(a); a.click(); a.remove();
    sectionOpen.mixes = true;
    await loadBrowser();          // the new mix appears under Mixes
    const over = st.clipped ? `  ⚠ clipped ${st.clipped} samples — lower the master` : "";
    setStatus(`exported ${st.file} (${fmt(st.seconds)}) peak ${st.peak_db} dBFS → saved under Mixes${over}`);
  } catch (e) {
    setStatus(`export failed: ${e.message}`);
  } finally {
    $("export").disabled = false;
  }
}

/* ================================================================
   CONTEXT MENU
   A plain HTML overlay rather than canvas drawing — real DOM gives us
   hover states, inputs and sliders for free, and it sits above the canvas.
   ================================================================ */
const menuEl = () => $("menu");
let menuTarget = null;          // {kind:"track"|"clip", track, clip}

function closeMenu() {
  menuEl().classList.remove("open");
  menuTarget = null;
}

function openMenu(px, py, items, title) {
  const m = menuEl();
  m.innerHTML = "";
  if (title) {
    const h = document.createElement("div");
    h.className = "mtitle"; h.textContent = title;
    m.appendChild(h);
  }
  for (const it of items) {
    if (it.sep) { const d = document.createElement("div"); d.className = "sep"; m.appendChild(d); continue; }
    if (it.slider) {
      const row = document.createElement("div"); row.className = "row";
      const lab = document.createElement("label"); lab.textContent = it.label;
      const inp = document.createElement("input");
      inp.type = "range"; inp.min = it.min; inp.max = it.max; inp.step = it.step;
      inp.value = it.value;
      const val = document.createElement("span");
      val.className = "val"; val.textContent = it.fmt(it.value);
      inp.oninput = () => { val.textContent = it.fmt(+inp.value); it.oninput(+inp.value); };
      row.append(lab, inp, val); m.appendChild(row); continue;
    }
    if (it.text) {
      const row = document.createElement("div"); row.className = "row";
      const lab = document.createElement("label"); lab.textContent = it.label;
      const inp = document.createElement("input");
      inp.type = "text"; inp.value = it.value;
      inp.onkeydown = (e) => {
        e.stopPropagation();                       // don't trigger S / space shortcuts
        if (e.key === "Enter") { it.onenter(inp.value); closeMenu(); }
      };
      row.append(lab, inp); m.appendChild(row); continue;
    }
    const d = document.createElement("div");
    d.className = "item" + (it.danger ? " danger" : "") + (it.disabled ? " disabled" : "");
    d.innerHTML = `<span>${it.label}</span>` + (it.key ? `<span class="k">${it.key}</span>` : "");
    if (!it.disabled) d.onclick = async () => { closeMenu(); await it.run(); };
    m.appendChild(d);
  }
  m.classList.add("open");
  // keep it on screen
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(px, window.innerWidth  - r.width  - 8) + "px";
  m.style.top  = Math.min(py, window.innerHeight - r.height - 8) + "px";
}

function trackMenu(tr, px, py) {
  const busy = stemJobs.has(tr.id);
  openMenu(px, py, [
    { text: true, label: "Name", value: tr.name,
      onenter: async (v) => { project = await post(`/api/track/update?track=${tr.id}`, { name: v }); render(); } },
    { slider: true, label: "Volume", min: 0, max: 1.5, step: 0.01, value: tr.volume,
      fmt: v => v.toFixed(2),
      oninput: async (v) => { tr.volume = v; render();
        project = await post(`/api/track/update?track=${tr.id}`, { volume: v }); } },
    { slider: true, label: "Pan", min: -1, max: 1, step: 0.02, value: tr.pan,
      fmt: v => (v === 0 ? "C" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100)),
      oninput: async (v) => { tr.pan = v; render();
        project = await post(`/api/track/update?track=${tr.id}`, { pan: v }); } },
    { sep: true },
    { label: tr.mute ? "Unmute" : "Mute", key: "M", run: async () => {
        project = await post(`/api/track/update?track=${tr.id}`, { mute: !tr.mute });
        if (playing) { pause(); play(); } render(); } },
    { label: tr.solo ? "Unsolo" : "Solo", key: "S", run: async () => {
        project = await post(`/api/track/update?track=${tr.id}`, { solo: !tr.solo });
        if (playing) { pause(); play(); } render(); } },
    { sep: true },
    { label: "Sound…  (low end, punch, drive, compress)", run: () => soundMenu(tr, px, py) },
    { sep: true },
    { label: busy ? "Separating…" : "Separate into stems", disabled: busy || !tr.clips.length,
      run: () => separateStems(tr) },
    { sep: true },
    { label: "Delete track", danger: true, run: async () => {
        project = await post(`/api/track/remove?track=${tr.id}`);
        selection = selection.filter(s => s.track !== tr.id);
        if (selected && selected.track === tr.id) selected = selection[selection.length - 1] || null;
        render(); } },
  ], tr.name);
}

// Change a clip's warp and wait for the server to build the stretched audio.
// The server rescales offset/length itself (see /api/clip/update), so this
// only sends the new numbers, then fetches the new waveform. That fetch is what
// makes the server run Rubber Band, so when it returns, playback is instant.
async function applyWarp(tr, c, warp) {
  setStatus("warping… (~5s for a full song)");
  try {
    project = await post(`/api/clip/update?track=${tr.id}&clip=${c.id}`, warp);
    render();                                    // new length draws immediately
    const fresh = project.tracks.find(t => t.id === tr.id).clips.find(x => x.id === c.id);
    await getWave(fresh);
    render();
    setStatus(`${fresh.name}: ${(100 * speedOf(fresh)).toFixed(1)}% speed, ${fresh.warp_mode} mode`);
  } catch (e) {
    setStatus(`warp failed: ${e.message}`);
  }
}

// Stretch a clip so its tempo matches the project's.
//
// `stretch` is a DURATION ratio, so the direction is easy to get backwards:
// a 100 BPM song matched to a 93 BPM project has to become LONGER (slower),
// and 100/93 = 1.075 > 1. Hence clipBpm / projectBpm, not the other way up.
//
// The ratio is always computed from the ORIGINAL file's tempo, so running this
// twice gives the same answer instead of compounding.
async function matchProjectTempo(tr, c) {
  const target = project.bpm;
  if (!target) { setStatus("the project has no tempo yet"); return; }

  setStatus(`analysing ${c.name}…`);
  let a;
  try {
    a = await api(`/api/analyze?source=${encodeURIComponent(c.source)}` +
                  `&name=${encodeURIComponent(c.file)}`);
  } catch (e) { setStatus(`couldn't analyse ${c.name}: ${e.message}`); return; }

  let clipBpm = a.bpm_from_downbeats || a.bpm;     // addAsTrack prefers the same one
  if (!clipBpm) { setStatus(`no tempo could be detected in ${c.name}`); return; }

  // Detectors routinely hear half or double time (kuthu at 84 comes back as
  // 168). Fold the reading into the octave nearest the project before giving
  // up on it — an out-of-range ratio is usually this, not a real mismatch.
  while (clipBpm / target > 1.5) clipBpm /= 2;
  while (clipBpm / target < 0.67) clipBpm *= 2;

  const stretch = clipBpm / target;
  if (Math.abs(stretch - 1) < 0.001) {
    setStatus(`${c.name} is already at ${target.toFixed(2)} BPM`);
    return;
  }
  if (stretch < 0.5 || stretch > 2) {
    setStatus(`${clipBpm.toFixed(1)} → ${target.toFixed(1)} BPM is too far to stretch`);
    return;
  }
  await applyWarp(tr, c, { stretch });
  setStatus(`${c.name}: ${clipBpm.toFixed(1)} → ${target.toFixed(2)} BPM ` +
            `(${(100 * speedOf(project.tracks.find(x => x.id === tr.id)
                 .clips.find(x => x.id === c.id))).toFixed(1)}% speed)`);
}

// Warp every bar of the clip onto the project grid, and transposition.
async function warpToGrid(tr, c) {
  setStatus("finding downbeats…");
  try {
    const r = await post(`/api/clip/warp-to-grid?track=${tr.id}&clip=${c.id}`);
    project = r.project;
    render();
    const fresh = project.tracks.find(x => x.id === tr.id).clips.find(x => x.id === c.id);
    setStatus(`warping to grid (${r.pins} bars @ ${r.bpm} BPM)…`);
    await getWave(fresh);
    render();
    setStatus(`${c.name}: ${r.pins} bars pinned to the grid`);
  } catch (e) { setStatus(`warp to grid failed: ${e.message}`); }
}

async function matchProjectKey(tr, c) {
  setStatus("checking key…");
  try {
    const r = await post(`/api/clip/match-key?track=${tr.id}&clip=${c.id}`);
    project = r.project;
    render();
    const fresh = project.tracks.find(x => x.id === tr.id).clips.find(x => x.id === c.id);
    if (r.semitones !== 0) await getWave(fresh);
    render();
    setStatus(`${r.from} → ${r.to}: ${r.semitones > 0 ? "+" : ""}${r.semitones} semitones` +
              (r.confidence < 0.7 ? "  (low confidence — check by ear)" : ""));
  } catch (e) { setStatus(`match key failed: ${e.message}`); }
}

// The Transpose slider fires on every pixel of movement, and each distinct
// value is a fresh Rubber Band render. Hold the last value and apply it once
// the mouse comes up.
let pendingPitch = null;
window.addEventListener("mouseup", async () => {
  if (!pendingPitch) return;
  const { tr, c, v } = pendingPitch;
  pendingPitch = null;
  if ((c.pitch || 0) !== v) await applyWarp(tr, c, { pitch: v });
});

// What each warp mode does to the sound — measured, see app/core/stretch.py.
const WARP_MODES = {
  crisp:   { name: "Crisp",    hint: "general purpose · hits within ~4 ms" },
  tones:   { name: "Tones",    hint: "vocals & 808s · smoothest, keeps attacks sharp" },
  slice:   { name: "Slice",    hint: "drums · every hit unstretched, full punch" },
  repitch: { name: "Re-Pitch", hint: "like a record · slower is lower" },
};

function modeMenu(tr, c, px, py) {
  const cur = c.warp_mode || "crisp";
  openMenu(px, py, Object.entries(WARP_MODES).map(([id, m]) => ({
    label: `${id === cur ? "● " : "○ "}${m.name}  —  ${m.hint}`,
    run: () => id === cur ? null : applyWarp(tr, c, { warp_mode: id }),
  })), "Warp mode");
}

// ---------------------------------------------------------------- sound
// The track's channel strip. Ranges and presets come from the server
// (/api/fx), so the UI never disagrees with what the renderer will accept.
let FX = null;
const FX_LABELS = {
  low_db: ["Low boost", v => (v > 0 ? "+" : "") + v.toFixed(1) + " dB", 0.5],
  low_hz: ["   at", v => Math.round(v) + " Hz", 5],
  punch: ["Punch", v => (v > 0 ? "+" : "") + Math.round(v * 100) + "%", 0.05],
  drive_db: ["Drive", v => v.toFixed(1) + " dB", 0.5],
  comp: ["Compress", v => Math.round(v * 100) + "%", 0.05],
  hp_hz: ["High-pass", v => v <= 20 ? "off" : Math.round(v) + " Hz", 5],
  lp_hz: ["Low-pass", v => v >= 20000 ? "off" : Math.round(v) + " Hz", 10],
  gain_db: ["Output", v => (v > 0 ? "+" : "") + v.toFixed(1) + " dB", 0.5],
};

// Like Transpose: a slider fires every pixel and each value is a fresh
// render, so only the value you let go on gets sent.
let pendingFx = null;
window.addEventListener("mouseup", async () => {
  if (!pendingFx) return;
  const { tr, params } = pendingFx;
  pendingFx = null;
  await setSound(tr, { params });
});

async function setSound(tr, body) {
  setStatus("applying sound…");
  try {
    project = await post(`/api/track/effects?track=${tr.id}`, body);
    render();
    const t2 = project.tracks.find(x => x.id === tr.id);
    for (const c of t2.clips) await getWave(c);
    render();
    const on = (t2.effects || []).find(e => e.kind === "strip");
    setStatus(`${t2.name}: ${on ? (on.enabled ? "strip on" : "strip bypassed") : "clean"}`);
  } catch (e) { setStatus(`sound failed: ${e.message}`); }
}

async function soundMenu(tr, px, py) {
  FX = FX || await api("/api/fx");
  const strip = (tr.effects || []).find(e => e.kind === "strip");
  const cur = strip ? strip.params : {};
  const val = (k) => (k in cur ? cur[k] : FX.strip[k].off);
  const items = Object.keys(FX.presets).map(name => ({
    label: `Preset: ${name}`, run: () => setSound(tr, { preset: name }),
  }));
  items.push({ sep: true });
  for (const [k, [label, fmt, step]] of Object.entries(FX_LABELS)) {
    const r = FX.strip[k];
    items.push({ slider: true, label, min: r.min, max: r.max, step, value: val(k), fmt,
      oninput: (v) => { pendingFx = { tr, params: { ...(pendingFx ? pendingFx.params : {}), [k]: v } }; } });
  }
  items.push({ sep: true });
  if (strip) items.push({ label: strip.enabled ? "Bypass (hear it dry)" : "Turn strip back on",
                          run: () => setSound(tr, { enabled: !strip.enabled }) });
  openMenu(px, py, items, `Sound · ${tr.name}`);
}

function clipMenu(tr, c, px, py) {
  const at = currentTime();
  const canSplit = c.start + 0.05 < at && at < c.start + c.length - 0.05;
  openMenu(px, py, [
    { text: true, label: "Name", value: c.name,
      onenter: async (v) => {
        project = await post(`/api/clip/update?track=${tr.id}&clip=${c.id}`, { name: v }); render(); } },
    { slider: true, label: "Gain", min: 0, max: 2, step: 0.01, value: c.gain,
      fmt: v => v.toFixed(2),
      oninput: async (v) => { c.gain = v;
        project = await post(`/api/clip/update?track=${tr.id}&clip=${c.id}`, { gain: v }); } },
    { sep: true },
    { label: "Split at playhead", key: "S", disabled: !canSplit,
      run: async () => { selectOnly(tr.id, c.id); await splitSelected(); } },
    { label: "Duplicate", run: async () => {
        const r = await post(`/api/clip/add?track=${tr.id}`, {
          source: c.source, file: c.file, name: c.name,
          start: c.start + c.length, offset: c.offset, length: c.length,
          ...warpOf(c) });
        project = r.project; render(); } },
    { sep: true },
    { label: "Match project tempo", run: () => matchProjectTempo(tr, c) },
    { label: "Warp every bar to grid", run: () => warpToGrid(tr, c) },
    { label: "Match project key", disabled: !project.key,
      run: () => matchProjectKey(tr, c) },
    { slider: true, label: "Transpose", min: -12, max: 12, step: 1, value: c.pitch || 0,
      fmt: v => (v > 0 ? "+" : "") + v + " st",
      // applied on release, not per pixel: each change re-renders the audio
      oninput: (v) => { pendingPitch = { tr, c, v }; } },
    { label: "Reset speed", disabled: !(c.warp && c.warp.length),
      run: () => applyWarp(tr, c, { warp: [] }) },
    { label: `Warp mode: ${WARP_MODES[c.warp_mode || "crisp"].name}  ▸`,
      disabled: !isWarped(c),
      run: () => modeMenu(tr, c, px, py) },
    { sep: true },
    { label: "Delete clip", danger: true, key: "⌫", run: async () => {
        project = await post(`/api/clip/remove?track=${tr.id}&clip=${c.id}`);
        clearSelection(); render(); } },
  ], c.name);
}

// right-click anywhere on the timeline
// Double-click in a clip's pin strip drops a pin at that moment: it pins the
// music where it already is, so dragging it is what actually warps anything.
$("timeline").addEventListener("dblclick", async (e) => {
  const r = e.target.getBoundingClientRect();
  const h = hit(e.clientX - r.left, e.clientY - r.top);
  if (!h || (h.kind !== "pin-strip" && h.kind !== "warp-pin")) return;
  if (h.kind === "warp-pin") return;
  const c = h.clip;
  const dst = h.t - c.start + c.offset;
  const src = warpDstToSrc(c.warp || [], dst);
  const base = isPlainStretch(c.warp || []) ? [[0, 0]] : (c.warp || []);
  const pins = [...base, [src, dst]].sort((a, b) => a[0] - b[0]);
  await applyWarp(h.track, c, { warp: pins });
});

$("timeline").addEventListener("contextmenu", (e) => {
  e.preventDefault();
  const r = e.target.getBoundingClientRect();
  const h = hit(e.clientX - r.left, e.clientY - r.top);
  if (!h) { closeMenu(); return; }
  if (h.kind === "clip" || h.kind === "trim-left" || h.kind === "trim-right") {
    selected = { track: h.track.id, clip: h.clip.id };
    render();
    clipMenu(h.track, h.clip, e.clientX, e.clientY);
  } else {
    trackMenu(h.track, e.clientX, e.clientY);
  }
});
window.addEventListener("mousedown", (e) => {
  if (!menuEl().contains(e.target)) closeMenu();
});
window.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  closeMenu();
  if (selection.length) { clearSelection(); render(); }
});

/* ================================================================
   STEM SEPARATION
   Demucs takes roughly real-time on CPU, so the backend runs it on a thread
   and we poll. The four stems land as new tracks aligned to the original clip.
   ================================================================ */
const stemJobs = new Set();     // track ids currently separating
const STEM_COLORS = { vocals: "#ff6b9d", drums: "#ffa94d",
                      bass: "#845ef7", other: "#38d9a9" };

async function separateStems(tr) {
  const c = tr.clips[0];
  if (!c) return;
  const already = project.tracks.some(t => t.name.startsWith(tr.name + " · "));
  if (already && !confirm(
        `"${tr.name}" already has stem tracks. Separate again and add another set?`)) return;
  const q = `source=${encodeURIComponent(c.source)}&name=${encodeURIComponent(c.file)}`;
  stemJobs.add(tr.id);
  setStatus(`separating "${tr.name}" — this can take a minute…`);
  render();
  try {
    await post(`/api/stems/start?${q}`);
    let st;
    for (let i = 0; i < 900; i++) {                 // ~15 min ceiling
      st = await api(`/api/stems/status?${q}`);
      if (st.state === "done" && st.stems) break;
      if (st.state === "error") throw new Error(st.error || "separation failed");
      await new Promise(r => setTimeout(r, 1500));
    }
    if (!st || !st.stems) throw new Error("timed out");

    for (const part of ["vocals", "drums", "bass", "other"]) {
      const rel = st.stems[part];
      if (!rel) continue;
      const name = `${tr.name} · ${part}`;
      const { track: tid } = await post(
        `/api/track/add?name=${encodeURIComponent(name)}` +
        `&color=${encodeURIComponent(STEM_COLORS[part])}`);
      // align to the original clip, and inherit its trim
      const r = await post(`/api/clip/add?track=${tid}`, {
        source: "stems", file: rel, name: part,
        start: c.start, offset: c.offset, length: c.length,
        ...warpOf(c) });
      project = r.project;
      await getWave({ source: "stems", file: rel, ...warpOf(c) });
      render();
    }
    // the original is now redundant — mute rather than delete, so it's recoverable
    project = await post(`/api/track/update?track=${tr.id}`, { mute: true });
    setStatus(`"${tr.name}" separated into 4 stems (original muted)`);
  } catch (err) {
    setStatus(`stem separation failed: ${err.message}`);
  } finally {
    stemJobs.delete(tr.id);
    render();
  }
}

function fadeDrag(d, t) {
  const c = d.clip;
  const MAXF = c.length * 0.9;          // a fade can't swallow the whole clip
  if (d.mode === "fade-in") {
    c.fade_in = Math.max(0, Math.min(MAXF - c.fade_out, t - c.start));
  } else {
    c.fade_out = Math.max(0, Math.min(MAXF - c.fade_in, c.start + c.length - t));
  }
}

// The bar lines between two times. An analysed downbeat list wins — it follows
// a song that drifts — but with only a tempo we still have a grid: bars from
// zero at 240/bpm. Snapping and the drawn grid both read from here, so what
// you see is what you snap to.
function gridBars(t0, t1) {
  const out = [];
  if (!project) return out;
  if (project.downbeats.length) {
    project.downbeats.forEach((t, i) => { if (t >= t0 && t <= t1) out.push({ t, i }); });
    return out;
  }
  if (!project.bpm) return out;
  const bar = 240 / project.bpm;
  for (let i = Math.max(0, Math.floor(t0 / bar)); i * bar <= t1; i++) out.push({ t: i * bar, i });
  return out;
}

function snap(t) {
  if (!project || !$("snap").checked) return t;
  let best = t, bd = Infinity;
  for (const b of gridBars(t - 8, t + 8)) {
    const dd = Math.abs(b.t - t);
    if (dd < bd) { bd = dd; best = b.t; }
  }
  return bd * pxPerSec < 14 ? best : t;
}

// ---------------------------------------------------------------- keys
async function splitSelected() {
  if (!selected) { setStatus("select a clip first"); return; }
  const at = currentTime();
  try {
    const r = await post(`/api/clip/split?track=${selected.track}` +
                         `&clip=${selected.clip}&at=${at}`);
    project = r.project;
    selectOnly(selected.track, r.right);                   // select the new half
    render();
    setStatus(`split at ${fmt(at)}`);
  } catch (err) {
    setStatus("playhead must be inside the selected clip");
  }
}

window.addEventListener("keydown", async (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") { e.preventDefault(); playing ? pause() : play(); }
  if (e.key === "s" || e.key === "S") { e.preventDefault(); await splitSelected(); }
  if ((e.key === "Delete" || e.key === "Backspace") && selection.length) {
    e.preventDefault();
    await deleteSelection();
  }
  // nudge: one grid step, or 10 ms with alt held
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && selection.length) {
    e.preventDefault();
    const step = e.altKey ? 0.01 : gridStep();
    await nudgeSelection((e.key === "ArrowLeft" ? -1 : 1) * step);
  }
});

// ---------------------------------------------------------------- wiring
$("play").onclick = () => (playing ? pause() : play());
$("stop").onclick = stopAll;
$("restart").onclick = restart;
$("export").onclick = exportMix;
$("bpm").onkeydown = (e) => {
  e.stopPropagation();                             // not a transport shortcut
  if (e.key === "Enter") { e.target.blur(); }
  if (e.key === "Escape") { showBpm(); e.target.blur(); }
};
$("bpm").onchange = (e) => applyBpm(e.target.value);
$("mastermeter").onclick = (e) => masterMenu(e.clientX, e.clientY);
$("undo").onclick = doUndo;
$("redo").onclick = doRedo;
$("save").onclick = () => saveProject();
$("open").onclick = (e) => openMenuProjects(e.clientX, e.clientY + 6);
$("newProj").onclick = async () => {
  if (project && project.tracks.length &&
      !confirm("Clear all tracks and start a new project?")) return;
  stopAll();
  project = await post("/api/project/new?name=Untitled");
  clearSelection(); scrollX = 0; playOffset = 0;
  bufCache.clear();
  lastAutosave = "";
  updateTitle();
  render(); setStatus("new project");
};
$("zoomIn").onclick = () => { pxPerSec = Math.min(400, pxPerSec * 1.4); setScroll(scrollX); render(); };
$("zoomOut").onclick = () => { pxPerSec = Math.max(6, pxPerSec / 1.4); setScroll(scrollX); render(); };
$("snap").onchange = render;
$("timeline").addEventListener("wheel", (e) => {
  // cmd/ctrl + wheel -> zoom the timeline
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    pxPerSec = Math.max(4, Math.min(400, pxPerSec * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
    setScroll(scrollX); render();
    return;
  }
  // A horizontal gesture (trackpad swipe, or shift+wheel) scrolls the timeline.
  // Anything else must fall through so the PAGE can scroll vertically — calling
  // preventDefault() unconditionally here is what blocked scrolling to tracks
  // below the fold.
  const horizontal = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY);
  if (horizontal) {
    e.preventDefault();
    // Shift+wheel: macOS reports the motion in deltaX, Windows in deltaY.
    // Reading only deltaY made it a dead zero on a Mac, in BOTH directions —
    // so once playback had paged the view right, a mouse couldn't bring it back.
    const d = Math.abs(e.deltaX) >= Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? $("timeline").clientWidth : 1;
    setScroll(scrollX + (d * unit) / pxPerSec);
    follow = false;   // you steered; don't yank the view back until next play
    render();
  }
}, { passive: false });
window.onresize = render;

// Drag the thumb to scroll; click the bar to jump the view there.
(() => {
  const bar = $("hscroll"), thumb = $("hthumb");
  let grab = null;
  const secPerPx = () => Math.max(contentEnd(), viewSeconds()) / bar.clientWidth;
  thumb.addEventListener("mousedown", (e) => {
    e.preventDefault(); e.stopPropagation();
    grab = { x: e.clientX, s: scrollX };
    thumb.classList.add("drag");
  });
  bar.addEventListener("mousedown", (e) => {
    if (e.target === thumb) return;
    const r = bar.getBoundingClientRect();
    setScroll((e.clientX - r.left) * secPerPx() - viewSeconds() / 2);   // centre the view there
    follow = false; render();
  });
  window.addEventListener("mousemove", (e) => {
    if (!grab) return;
    setScroll(grab.s + (e.clientX - grab.x) * secPerPx());
    follow = false; render();
  });
  window.addEventListener("mouseup", () => { grab = null; thumb.classList.remove("drag"); });
})();
// ---------------------------------------------------------------- tempo box
function showBpm() {
  const el = $("bpm");
  if (el && document.activeElement !== el && project) {
    el.value = (Math.round(project.bpm * 100) / 100).toString();
  }
}

// Changing the tempo re-stretches every warped clip (server side), so the
// audio has to be fetched again — same wait as any warp change.
async function applyBpm(v) {
  const bpm = parseFloat(v);
  if (!project || !isFinite(bpm) || Math.abs(bpm - project.bpm) < 0.005) { showBpm(); return; }
  const was = playing;
  if (was) pause();
  setStatus(`re-warping to ${bpm} BPM…`);
  try {
    const r = await post("/api/project/retempo", { bpm });
    project = r.project;
    render();
    await ensureWaves();
    render();
    setStatus(`${bpm} BPM — clips kept their place in the bar`);
  } catch (e) {
    setStatus(`tempo change failed: ${e.message}`);
  }
  showBpm();
  if (was) play();
}

function setStatus(s) { $("status").textContent = s; }

(async () => {
  project = await api("/api/project");
  await loadBrowser();
  updateTitle();
  render();

  // Cold start with an empty project? Offer whatever autosave has.
  if (!project.tracks.length) {
    try {
      const { autosave } = await api("/api/project/list");
      if (autosave && autosave.tracks) {
        setStatus(`autosave available (${autosave.tracks} tracks) — Open ▸ Restore autosave`);
      } else {
        setStatus("click a file to add it as a track");
      }
    } catch (e) { setStatus("click a file to add it as a track"); }
  } else {
    lastAutosave = JSON.stringify(project);
    setStatus("loading waveforms…");
    await ensureWaves();       // a reload used to leave every clip blank
    setStatus("ready");
  }
})();
