# Running mixr without starting it by hand

Three options, cheapest first. Measured context: a single clip fetch is
5–20 MB, Demucs takes ~21 s and a warp 1.5–6 s on this Mac. Those numbers are
what make option 1 the right default — every one of them gets worse the moment
the audio has to cross a network.

## 1. Always-on, on your own Mac (recommended)

Starts at login, restarts itself if it crashes, costs nothing, and the audio
never leaves the machine.

    cp deploy/com.mixr.server.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.mixr.server.plist

Then http://localhost:8765 is simply always there. Logs: /tmp/mixr.log

    launchctl unload ~/Library/LaunchAgents/com.mixr.server.plist   # to stop
    launchctl kickstart -k gui/$(id -u)/com.mixr.server             # to restart

Note: no `--reload`. A background service shouldn't restart itself on every
file edit — run the dev command by hand when you're editing code.

## 2. Reach it from anywhere, without moving anything

Install Tailscale on the Mac and on your laptop/phone; mixr is then reachable
at the Mac's Tailscale address from any of your devices. The files, the CPU and
the latency all stay at home, and nothing is exposed publicly. Free for
personal use. Cloudflare Tunnel does the same job.

The Mac has to be awake: System Settings → Battery → prevent sleeping when
plugged in.

## 3. Actually hosting it (AWS)

Only worth it when OTHER PEOPLE need their own mixr — the original goal of
teammates not paying for Ableton. It is not a deployment job; it needs real
work first:

- **Authentication.** There is none today; every endpoint is open, including
  file upload and Demucs.
- **Per-user state.** `STATE["current"]` is one global project. Two people
  would edit the same session.
- **Storage.** Audio to S3, with the cache either on fast local disk or
  regenerated per instance.
- **A job queue.** Demucs and exports must not run inside a request on a
  shared box.
- **Hardware.** Demucs on a plain CPU instance is minutes, not seconds. A GPU
  instance is fast but expensive; a CPU instance is cheap but slow.
- **Rights.** Competition mixes and commercial tracks on a shared server is
  distribution, not personal use. Keep any deployment private and
  authenticated, and prefer per-user uploads over a shared library.

Rough shape if you do it: Docker image, ECS/Fargate or a single EC2 box,
EBS for the cache, S3 for audio, Caddy in front for HTTPS + auth.
