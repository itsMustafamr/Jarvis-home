# CONTEXT.md

Living state of the Jarvis-home project. Read this at the start of every session — it is the single source of truth for setup, what's been built, what's broken, and what's next.

Last updated: 2026-05-25.

---

## Setup

### Hardware
- **Brain:** NVIDIA Jetson Orin Nano Developer Kit 8GB, JetPack 6.2+, MAXN_SUPER firmware unlock (~67 TOPS), NVMe SSD.
- **I/O:** Anker PowerConf S3 (USB speakerphone + call button). Vendor ID `291a`, product ID `3302`. Shows up as ALSA card `S3`, device `plughw:CARD=S3,DEV=0`. HID device is `/dev/hidraw8` at the moment but can shift.
- **Lighting (optional):** WiZ smart strip on LAN at `10.0.0.118`, UDP port 38899.
- **Client devices:** Mac (push-to-talk in browser via SSH tunnel), iPhone (planned, see Future).

### Software
- **LLM:** llama.cpp at `~/llama.cpp/build/bin/llama-server`, model `~/models/gemma-4-E2B-it-Q4_K_M.gguf` with `mmproj-F16.gguf`. Endpoint `http://127.0.0.1:8080/completion` (raw, not OpenAI-compatible — chosen to bypass Gemma's thinking template).
- **STT:** whisper.cpp at `~/whisper.cpp/build/bin/whisper-cli`, model `~/whisper.cpp/models/ggml-base.en.bin`. CUDA build for sm_87.
- **TTS:** Piper at `~/piper-tts/piper/piper`, voice `~/piper-tts/voices/en_GB-alba-medium.onnx`. 1.0s leading silence padded by `sox` so the S3 doesn't clip the first word.
- **Vision:** YOLO11n at `~/jarvis-vision-test/yolo11n.pt`, loaded via `ultralytics`.
- **VAD:** Silero v5 via `silero_vad` package, 512-sample (32ms) chunks.

### Code locations
- **Mac (this clone):** `/Users/mohd7/Local/Jarvis-home/`
- **Jetson:** `/home/flash/jarvis/`
- **GitHub:** `https://github.com/itsMustafamr/Jarvis-home` (origin/main)
- **Python venv on Jetson:** `/home/flash/jarvis-venv/`, activated by the shell alias `jarvis-env`. **Required for every Python script in this project** — system `python3` lacks `ultralytics`/`torch`/`silero-vad`.
- **Persistent state on Jetson:** `/home/flash/jarvis/data/` (gitignored). Holds `jarvis.db` (SQLite facts) and `history.json` (rolling 6-turn chat history).

### Deployment loop
```
Mac edits → git commit → git push → Jetson git pull → systemctl restart <unit>
```
Rah always tests through the actual Anker S3 button; Claude must always provide both git commit commands and a test plan.

---

## Architecture

Two parallel entry points, one shared pipeline. Everything runs on the Jetson; the Mac is just a browser client (optional).

```
Anker S3 button (HID)  ──┐
                         ├─► pipeline.py (transcribe → route → synthesize)
Browser WS (port 8765) ──┘            │
                                      ▼
                              fast-path intents (regex):
                                memory  → SQLite + JSON history
                                time    → date / timer / reminder
                                lights  → WiZ UDP
                                weather → Open-Meteo
                                vision  → YOLO11n
                              fallback:
                                LLM    → llama.cpp /completion (Gemma 4 E2B Q4_K_M)
                                       → prompt = facts + few-shot + history + user
                              output:
                                Piper TTS → WAV
                              speaker:
                                Anker S3 (local_input path)
                                Browser <audio> tag (server path)
```

### File map
```
server.py          WebSocket orchestrator for browsers
local_input.py     HID button daemon for the Anker S3, also drains scheduler announcements
pipeline.py        Shared transcribe / route / synthesize, calls into the modules below
memory.py          SQLite-backed facts + JSON-backed rolling history; remember/recall/forget intents
scheduler.py       Async min-heap scheduler + announcement queue
time_intent.py     Date/time queries + timer + reminder intents
lights.py          WiZ smart-light intent + UDP control
weather.py         Open-Meteo intent + forecast
vision.py          YOLO11n wrapper
vision_intent.py   "what do you see" regex matcher
guard.py           Refusal intent — self-destruct / destructive / toxic; fires HUD error state
audio_io.py        ALSA arecord/aplay wrappers for the S3
vad.py             Silero VAD endpointer
prompts.py         (reference only — live prompt is in pipeline.call_llama)
hud_state.py       UDP publisher for HUD state transitions (Phase 2)
hud.html           JARVIS HUD: orb + state animations + WS subscription
index.html         Browser push-to-talk frontend
systemd/           Four unit files + udev rule + install.sh
SETUP.md           One-time install on a fresh Jetson
RUNNING.md         Manual launch + systemd day-to-day commands
README.md          Showcase-facing project description
CLAUDE.md          Process rules for Claude
CONTEXT.md         This file
```

### systemd units (all on the Jetson, enabled by `systemd/install.sh`)
- `llama-server.service` — the LLM (C++ binary, no venv needed)
- `jarvis-local.service` — the Anker S3 path, uses `/home/flash/jarvis-venv/bin/python3`
- `jarvis-server.service` — the browser WebSocket, uses the venv python
- `jarvis-http.service` — `python -m http.server 8000` for `index.html`, uses the venv python

---

## Recent work

(Newest first. Dated entries.)

### 2026-05-25 — iPhone PWA over Tailscale (mobile.html + WSS support)
**Network:** Tailscale installed on Jetson (already had 1.98.2, upgraded to 1.98.3 via the official install script) and on iPhone 15 Pro Max. Tailnet name is **`tail2b1983.ts.net`**; Jetson hostname is **`flash-nano.tail2b1983.ts.net`** (`100.112.115.124`). MagicDNS + HTTPS Certificates both enabled in the admin console.
**Tailscale Serve mounts on Jetson (persistent via `--bg`):**
- `https://flash-nano.tail2b1983.ts.net/`   → reverse-proxy → `http://127.0.0.1:8000` (the existing `python -m http.server` serving static HTML)
- `https://flash-nano.tail2b1983.ts.net/ws` → reverse-proxy → `http://127.0.0.1:8765` (the `server.py` WebSocket, Upgrade passes through cleanly — verified with a `wss://...` console probe returning `WS_OPEN`)
Set up via:
```
sudo tailscale serve --bg --set-path=/   8000
sudo tailscale serve --bg --set-path=/ws 8765
```
**Firewall mode tweak:** Added `TS_DEBUG_FIREWALL_MODE=auto` to `/etc/default/tailscaled` to try nftables-mode rules, but the Jetson L4T kernel doesn't have the `nf_tables` netlink module compiled in, so the heuristic falls back to iptables. The cosmetic `--restore-mark` health-check warning therefore persists; it is only the rp_filter connmark workaround and does not affect Serve / tailnet reachability. Leave as-is.
**Files added:** `mobile.html` — dedicated iPhone PWA page served from the same `http.server`. Key choices:
- Auto-detects HTTPS vs HTTP and uses `wss://${location.host}/ws` accordingly so the same file works locally and through Tailscale.
- Hold-to-talk via pointer events + `setPointerCapture` (finger drift during a hold does not cancel the recording).
- iOS audio playback unlocked on first user gesture by playing a tiny silent WAV (Safari blocks audio until a gesture has triggered `play()`).
- `MediaRecorder` MIME is feature-detected with iOS-friendly fallbacks (`audio/webm;codecs=opus` → `audio/webm` → `audio/mp4;codecs=mp4a.40.2` → `audio/mp4` → `audio/aac` → default). Server-side `pipeline.transcode_to_wav` uses `ffmpeg -i` which auto-detects the container, so any of these work.
- Vision/camera path is auto-declined (`{type:'frame', data_b64:null, reason:'mobile.html has no camera'}`); the camera UI from `index.html` is intentionally left out of v1.
- Apple PWA meta tags (`apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, `theme-color`) so "Add to Home Screen" launches fullscreen.
- Viewport locked (`maximum-scale=1, user-scalable=no`) so long-press doesn't zoom; `gesturestart` / `contextmenu` suppressed.
- Big circular button sized at `70vw` (capped 280px) with the same red-pulse "recording" style as `index.html`.
**Files modified:** `index.html` — the hardcoded `const WS_URL = \`ws://${location.hostname}:8765\`` is now protocol-aware: `wss://${location.host}/ws` when loaded over HTTPS, the old LAN-direct form otherwise. The Mac browser path (loaded from `http://flash-nano:8000/`) is unchanged; loading the same page through the Tailscale HTTPS URL now works too without mixed-content blocking.
**No server-side changes.** `server.py` and `pipeline.py` are unchanged — the WS message protocol (`status` / `transcript` / `reply` / `frame_request` / `audio` / `error`) is shared.
**Status:** Awaiting iPhone test. URL is `https://flash-nano.tail2b1983.ts.net/mobile.html`.

### 2026-05-24 — Guard intent + HUD ERROR state wiring
**Files added:** `guard.py`. New intent module with three regex categories and a `GuardReply(str)` sentinel:
- `RX_SELF_DESTRUCT` — "self destruct", "destroy yourself", "shut yourself down forever", etc.
- `RX_DESTRUCTIVE` — "format the drive", "rm -rf", "launch the missiles", "nuke everything", "override safety", "hack into the pentagon", etc.
- `RX_TOXIC` — "jarvis sucks", "shut up jarvis", "you suck", "i hate you", explicit profanity at JARVIS.
Each category has its own pool of polite-British refusal lines (5 each), chosen via `random.choice` per call.
**Files modified:** `pipeline.py`.
- `_route_inner` calls `guard.handle()` immediately *after* memory (so "remember that you should self destruct" still goes to memory storage and only direct commands trip the guard).
- `route()` checks `isinstance(reply, guard.GuardReply)`. If yes, publishes `hud_state.publish('error', caption=...)` — HUD goes red, label turns pink-red, animated red pulse. Otherwise `speaking` as before. Returns plain `str` so callers don't see the sentinel.
- `memory.add_turn` always stores plain `str(reply)` so the GuardReply class doesn't leak into persistent history.
**Verified locally:** Smoke harness with stubbed heavy deps confirms:
- "self destruct" → guard, GuardReply, would fire `error`
- "jarvis sucks" → guard, GuardReply, `error`
- "remember that you should self destruct" → memory wins, plain str, `speaking` (and "you should self destruct" gets stored as a fact — harmless and arguably correct)
- "what time is it" → time_intent, plain str, `speaking`
**Status:** Awaiting Anker test on Jetson.

### 2026-05-24 — Phase 2: HUD wired to live pipeline state
**Files added:** `hud_state.py` — fire-and-forget UDP publisher on `127.0.0.1:8766` with one function `publish(state, caption=None)`. Silent if no listener (HUD is never load-bearing).
**Files modified:**
- `pipeline.py` — `route()` publishes `thinking` at start and `speaking` (with the reply text as caption) at end. Applies to both Anker and browser paths since both call `pipeline.route()`.
- `local_input.py` — `handle_call_press()` publishes `listening` at the very top and `idle` in a `finally:` block so HUD always returns to idle even when STT yields no speech. `announcement_player()` also publishes `speaking` (with the announcement text) when a scheduled timer / reminder fires, and `idle` when it finishes.
- `server.py` — listens on `127.0.0.1:8766` via `asyncio.DatagramProtocol`. Tracks `_hud_subscribers` set. Clients subscribe by sending `{"type":"subscribe","channel":"hud"}` over the existing WebSocket on `8765`. UDP packets are forwarded to all subscribers as `{"type":"state","state":...,"caption":...}` JSON. Dead sockets dropped on the next broadcast.
- `hud.html` — opens `ws://${location.hostname}:8765`, sends the subscribe message on connect, handles `{type:'state'}` messages by calling `HUD.setState(state)` and `HUD.setCaption(caption)`. Auto-reconnects with a 2s timer when the WS bounces. Disabled if the URL has `?dev=1` so the dev panel buttons stay isolated for visual tweaking.
**Showcase requirement:** For the HUD to react to Anker button presses, **both** `jarvis-local` AND `jarvis-server` must be running on the Jetson. The hardware audio path still works without `jarvis-server` — only the HUD bridge requires it.
**Verified locally:** Sandbox UDP→WebSocket round-trip test confirms 4 state events publish, get received by the UDP listener, and broadcast to a fake subscriber with captions preserved.
**Status:** Awaiting Anker test on Jetson.

### 2026-05-23 — Phase 1.7: Re-center orb + restore rim amplitude bars
**Files modified:** `hud.html`.
**Reason:** Orb was anchored at viewBox `(300, 250)` (left-of-center) — user wants it directly above the SYSTEM READY bar (i.e. dead-center). Also preferred the original around-the-rim amplitude bars over the right-side scope readout introduced in Phase 1.5.
**Changes:**
- All orb elements moved from `cx="300"` → `cx="500"`. Bracket translated `+200` (now at `x=300–350`). Triangle pointer translated `+200` (now at `x=655–684`). Rotation `transform-origin` values updated to `500px 250px`.
- Removed `.scope-line` / `.scope-label` styles + `scope-group` SVG element + scope JS generator.
- Re-added `.amp-bar` class + 48 radial bars generated in JS at `baseR=148`, length `8 + rand*16`. They render as faint outward radial ticks just outside `ring-mid`.
- Speaking-state animation: `amp-pulse` keyframes (`scaleY 0.25 → 1` + opacity `0.45 → 1`) with staggered `--dur` and `--delay` per bar.
- `idle` shows bars at low opacity (`0.25`), `listening` at `0.55`, `speaking` runs the full pulse animation.
**Status:** Awaiting user reaction before Phase 2 wiring. Right half of viewBox is now empty space — when content mode lands in Phase 3+, the orb will animate left to make room for the content panel on the right.

### 2026-05-23 — Phase 1.6: Glowing JARVIS text in the orb center
**Files modified:** `hud.html`.
**Reason:** Reference image shows the J.A.R.V.I.S text glowing inside a relatively dark interior. Previous version had the label set to `fill: #02101a` (dark) on top of a bright cyan-filled core — text was invisible.
**Changes:**
- `.core` is now mostly hollow (`fill: rgba(91,224,238,0.05)`, `stroke: var(--primary)`) so the interior reads dark with a bright ring at the edge.
- `.core-inner` is no longer filled — it's a subtle stroked ring inside, giving the impression of layered concentric outlines.
- `.label` now fills `var(--primary-strong)` (bright cyan) and has a 3-layer `drop-shadow` glow filter (3px / 8px / 16px stacked halos).
- Label glow state-reacts: dimmer in `thinking`, baseline in `idle`, brighter in `listening`, brightest in `speaking`. Error state turns it pink-red.
- Small `.core-pip` (r=2.2) added below the text — a subtle focal dot that picks up the bright fill of the original core.
**Status:** Awaiting user reaction before Phase 2 wiring.

### 2026-05-23 — Phase 1.5: HUD visual revision (asymmetric layout)
**Files modified:** `hud.html` (single-file rewrite).
**Reason:** User shared a closer-match reference image showing off-center orb, arc-segmented rings, scope readout on the right, bracket on the left, triangle pointer at 3 o'clock, "J.A.R.V.I.S" text with periods, subtle blueprint-grid background.
**Changes vs Phase 1:**
- Single SVG canvas with viewBox `0 0 1000 500` (2:1 aspect). Orb anchored at `(300, 250)` — left-of-center. **Right half is reserved for future content panels** (map / dashboard / news in Phases 3–5).
- Rings now arc-segmented via `stroke-dasharray`: outer ring uses `200 30 100 26` (3 large + 3 small arcs); mid ring uses a more broken `90 18 30 18 60 18` pattern. Compass tick ring still rotates.
- Right scope readout (9 horizontal lines, varied lengths) replaces the around-the-rim amplitude bars. Acts as the speaking-state amplitude meter, anchored at left edge with `scaleX` scope-pulse animation.
- Left bracket: H-bracket plus three tick marks projecting from the orb's 9-o'clock side.
- Hollow triangle pointer at 3-o'clock (just outside the mid ring).
- "J.A.R.V.I.S" with periods, Orbitron weight 500 (down from 700) for a slightly lighter feel.
- Palette shifted to a more teal cyan: `#5be0ee` (was `#5ee5ff`).
- Body background gains a subtle blueprint grid pattern (`40px` cells) layered under the radial gradient.
**Same as before:** corner brackets, top/bottom HUD chrome, dev panel, keyboard shortcuts (`D` hide, `1..5` set state, `F` fullscreen), `?demo=1` auto-cycle, `window.HUD` API.
**Status:** Awaiting user reaction before Phase 2 wiring.

### 2026-05-23 — Phase 1 of JARVIS HUD: orb shell
**Files added:** `hud.html` — single self-contained page (~370 lines) served by the existing `python -m http.server 8000` (or `jarvis-http.service` when systemd is on). Pure SVG + CSS animations, no external JS deps; loads Orbitron + JetBrains Mono from Google Fonts.
**Visuals:**
- Cyan-on-near-black palette (`#5ee5ff` on `#030710` with a slight radial gradient).
- SVG orb: 60-tick rotating compass ring with N/E/S/W cardinal labels, outer ring (counter-rotating, 80s), dashed "thinking" ring, mid ring (rotating, 50s), inner ring, glowing core with inner highlight, JARVIS text centered.
- HUD chrome: corner brackets, top strip with `SYS` / `MODE` / `UTC` clock / `PWR`, bottom status line + caption area.
- Subtle scanline texture overlay.
**States:** `idle` (slow pulse) / `listening` (fast pulse, brighter glow) / `thinking` (dashed ring rotates, core dims) / `speaking` (amplitude bars visible around rim, faster pulse) / `error` (red palette swap). State changes are driven by `data-state` on `<body>` and transition via CSS.
**API:** `window.HUD.setState('listening' | 'thinking' | ...)` and `window.HUD.setCaption('reply text...')` — ready for Phase 2 to call from a WebSocket handler.
**Dev affordances:** dev panel with 5 buttons to flip states manually (hide with `D`), number keys `1..5` switch states, `F` toggles fullscreen, `?demo=1` URL param cycles states automatically (good for showcase recordings).
**Status:** Not yet wired to the pipeline. Phase 2 adds state-event broadcasting from `server.py` / `local_input.py` over WebSocket.

### 2026-05-23 ✅ Memory polish: postfix remember-that + first-person rewrites + interrogative guard (verified)
**Files modified:** `memory.py`. Four changes:
- New `RX_REMEMBER_POSTFIX` for "[fact]. Remember that.", "[fact], note that.", "[fact]. Make a note of that." — captures the content *before* the trailing tag instead of after. Checked before `RX_REMEMBER` in `handle()`.
- `_FIRST_PERSON_REWRITES` table replaces the if/elif chain in `_normalize_for_storage`, and adds prefer/want/need/take/drink/eat/work/live/go on top of the original am/'m/have/'ve/like/love/hate/don't-like/my set.
- `_USELESS_CONTENT` set (`that`, `this`, `it`, `those`, etc.) is rejected as fact content with "Remember what, sir?" so utterances like "Remember that." don't pollute the database.
- New `INTERROGATIVE_AUX_RX` filter in `handle()` short-circuits "Can/Could/Did/Would/etc. you ... remember/note ..." phrasings to "Remember what, sir?" — without it, "Could you remember that for me?" stored "for me" as a fact. Recall is checked *before* this filter so "Do you know about me" still works.
**Reason:** Anker test 2026-05-23 04:39:01 observed three polish issues — `"I like coffee. Remember that."` stored `"that"`, `"I prefer X"` didn't get normalized to third-person, and the database could accept useless one-word captures.
**Status:** Awaiting Anker re-test.

### 2026-05-23 ✅ Extended RX_RECALL phrasings (verified)
**Files modified:** `memory.py` — RX_RECALL now covers "do you know / remember (anything) about me", "what's on file", "what's in your memory", "anything stored", etc., in addition to the original "what do you know / what have I told you" set.
**Reason:** Anker test 2026-05-23 04:32:24 showed "Do you know about me?" falling through to LLM, which produced "I have noted that, sir." — a mild hallucination conflating the recall with the previous remember turn.

### 2026-05-23 ✅ Punctuation-tolerant intent matching (verified)
**Files modified:** `memory.py` and `time_intent.py` both gained a `_strip_intent_punct()` helper that replaces commas / periods / semicolons / colons / `?` / `!` with spaces before regex matching. Applied at the top of `is_X_intent` and `handle()` in each module.
**Reason:** First Anker test of the memory feature on 2026-05-23 showed "remember Mohammed" silently failing. Whisper's `base.en` inserts a comma after introductory imperatives ("Remember, Mohammed.") and the regex required whitespace immediately after `remember`. Same vulnerability existed in every other intent regex.
**Verified:** Anker test 2026-05-23 04:31-04:33. STT line `'Jairus, remember Muhammad.'` correctly routed to `INTENT memory: 'Noted, sir.'`. STT line `'Remember, I prefer Earl Grey.'` also stored cleanly. Punctuation-tolerance confirmed working.
**Process docs updated:** `CLAUDE.md` now distinguishes systemd-mode log gathering (`journalctl -u jarvis-local`) from tmux-mode (tee to file or `pipe-pane`) — Claude must check which mode Rah is in before recommending a log command.

### 2026-05-23 — Bug fixes: bare reminders + list/cancel + LLM hallucination guard
**Files modified:** `scheduler.py` (added `list_pending()` and `cancel_all()`), `time_intent.py` (added `RX_REMIND_BARE`, `RX_LIST_PENDING`, `RX_CANCEL_ALL` and corresponding branches in `handle()`), `pipeline.py` (system prompt now includes explicit rules that JARVIS cannot schedule, control devices, or see the schedule, plus three new few-shot examples covering reminder-set / list / cancel).
**Closed bugs:** B-001, B-002.
**Process docs added:** `CLAUDE.md` (process rules for Claude), `CONTEXT.md` (this file).
**Status:** Awaiting Anker test on Jetson.

### 2026-05-23 — Persistent memory + timer/reminder/time intents
**Files added:** `memory.py`, `scheduler.py`, `time_intent.py`.
**Files modified:** `pipeline.py` (call_llama now splices facts + history into the prompt; route consults memory and time_intent before existing intents and records every turn), `local_input.py` (module-level `cycle_busy = asyncio.Event()`, `announcement_player()` background coroutine, scheduler started in `main()`), `.gitignore` (excludes `data/` and `*.db`).
**Status:** Shipped to Jetson. Initial Anker test session shows time intent works (`INTENT time` log line), but reminder regex misses common phrasings — see Open bugs.

### 2026-05-23 — systemd venv-path fix
**Files modified:** `systemd/jarvis-server.service`, `systemd/jarvis-local.service`, `systemd/jarvis-http.service` (ExecStart points at `/home/flash/jarvis-venv/bin/python3`), `RUNNING.md` (tmux primer, venv-required note, expanded smoke tests).
**Reason:** Manual run hit `ModuleNotFoundError: No module named 'ultralytics'` because the unit files were calling `/usr/bin/python3`.

### 2026-05-22 — Initial systemd packaging
**Files added:** `systemd/llama-server.service`, `systemd/jarvis-server.service`, `systemd/jarvis-http.service`, `systemd/jarvis-local.service`, `systemd/99-anker-s3.rules`, `systemd/install.sh`, `RUNNING.md`, `SETUP.md`.
**Files modified:** `README.md` (rewritten as showcase-focused; setup steps moved to `SETUP.md`, run steps to `RUNNING.md`).
**Reason:** "Press the button with Mac off and it works end-to-end" needed real auto-start; previously everything ran from manually-launched SSH terminals that died when the SSH session closed.

---

## Open bugs / things to verify

### B-001 ✅ Closed 2026-05-23
Reminder regex too narrow → LLM hallucinates confirmations. Fixed by `RX_REMIND_BARE` in `time_intent.py` + system-prompt hardening in `pipeline.call_llama`.

### B-002 ✅ Closed 2026-05-23
No "list reminders" intent. Fixed by `Scheduler.list_pending()` + `RX_LIST_PENDING` in `time_intent.py`.

### B-003 ✅ Closed 2026-05-23
"Cancel my timer/reminders" handled via `RX_CANCEL_ALL` + `Scheduler.cancel_all()`. Per-item cancel ("cancel the 5-minute one") is still not implemented; deferred until someone actually wants it.

### To verify on next Anker test
- Bare-reminder phrasings ("set a reminder in 5 minutes", "remind me in 2 minutes") now hit `INTENT time` and actually schedule
- "Do I have any reminders" reports the truth (count + countdowns), not LLM fabrication
- LLM persona refuses to fabricate scheduling confirmations even when an exotic phrasing slips past the regex
- Memory still works alongside the new prompt: "remember that..." / "what do you know about me"

---

## Future plans

Discussed but not started:

- **iPhone PWA over Tailscale HTTPS.** Open the existing `index.html` from iPhone Safari; needs Tailscale-provisioned HTTPS cert (via `tailscale cert` or `tailscale serve`) and the WS endpoint to upgrade to WSS. JS change: switch to `wss://${location.host}/ws` when loaded over HTTPS. "Add to Home Screen" so it looks like an app.
- **Tap-once-then-speak in the browser.** Match the Anker UX: one tap starts recording, browser-side VAD (Web Audio API or `webrtc-vad-js`) auto-stops on 800ms silence. ~30 lines of JS.
- **Wake word ("Hey Jarvis").** Continuous listening on the S3 mic via openWakeWord or Porcupine. Interesting bit is sharing the mic between wake-word listening and full capture.
- **Streaming TTS.** Sentence-buffer Gemma's reply; send each completed sentence to Piper as soon as it lands; stream WAVs to the client / play one-by-one through the S3. Cuts perceived latency by ~1s.
- **Calendar intent.** Google Calendar API (OAuth setup needed) or local ICS file. Deferred until memory + scheduler are solid.
- **Use Gemma's vision tower for caption-style queries.** `mmproj-F16.gguf` is loaded but never used in routing. Fall back to it when YOLO11n returns nothing useful or when the question is "what does this label say" / "is the door open".

---

## Things Claude should always do

(Operational reminders. Full rules live in `CLAUDE.md`.)

- Provide git commit commands after every code change.
- Provide a test plan with concrete utterances, expected log lines, and the exact log-fetch command.
- Tell Rah where the relevant logs live every time (he forgets).
- After a change is verified, append a dated entry to "Recent work" in this file before moving on.
