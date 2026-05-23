# CONTEXT.md

Living state of the Jarvis-home project. Read this at the start of every session — it is the single source of truth for setup, what's been built, what's broken, and what's next.

Last updated: 2026-05-23.

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
audio_io.py        ALSA arecord/aplay wrappers for the S3
vad.py             Silero VAD endpointer
prompts.py         (reference only — live prompt is in pipeline.call_llama)
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
