# Jarvis-home

A fully local voice assistant running on an NVIDIA Jetson Orin Nano Super 8GB. Press the call button on a USB speakerphone or push-to-talk in a browser, and a British butler replies. STT, LLM, TTS, vision, smart-light control — all on-device. Zero cloud APIs.

<p align="center">
  <img src="https://miro.medium.com/1*2QlX10Yrh7qBcfzmLSv4Fg.gif" width="700" alt="Jarvis home assistant demo">
</p>

**Stack:** Gemma 4 E2B (LLM) · whisper.cpp (STT) · Piper Alba en_GB (TTS) · YOLO11n (vision) · Silero VAD · Python WebSocket server · ALSA + HID daemon for the hardware path.

## Two entry points, one pipeline

The Jetson runs everything. There is no Mac, no cloud, no other machine in the loop.

**Hardware path — the showcase.** An Anker PowerConf S3 speakerphone is plugged into the Jetson over USB. Press its call button: `local_input.py` reads the HID event, captures from the S3 mic with Silero VAD endpointing, runs the full pipeline, plays Alba's reply through the S3 speaker. No browser, no SSH session, no other device powered on.

**Browser path.** `server.py` exposes a WebSocket. Any device on the network (phone, Mac, laptop) opens the page, push-to-talks, gets audio back. Same `pipeline.py` under the hood.

## Architecture

```
┌────────────────────────┐         ┌──────────────────────────────────┐
│  Anker PowerConf S3    │   USB   │  Jetson Orin Nano Super 8GB      │
│  • mic + speaker       │◀───────▶│                                  │
│  • call button (HID)   │         │  local_input.py  (headless path) │
└────────────────────────┘         │     • HID button listener        │
                                   │     • ALSA capture + playback    │
┌────────────────────────┐         │                                  │
│  Browser (any device)  │   WS    │  server.py       (browser path)  │
│  • push-to-talk        │◀───────▶│     • WebSocket + on-demand webcam│
│  • webcam (on demand)  │  :8765  │                                  │
└────────────────────────┘         │  pipeline.py     (shared)        │
                                   │     1. lights  → WiZ UDP (LAN)   │
                                   │     2. weather → Open-Meteo      │
                                   │     3. vision  → YOLO11n         │
                                   │     4. fallback → llama.cpp :8080│
                                   │        Gemma 4 E2B Q4_K_M        │
                                   │     → Piper (Alba en_GB) → WAV   │
                                   └──────────────────────────────────┘
```

## Latency budget (Orin Nano Super, MAXN_SUPER)

| Stage | Time |
|---|---|
| STT (whisper.cpp base.en, CUDA) | ~300ms for 3s audio |
| LLM first token (Gemma 4 E2B Q4_K_M) | ~500ms |
| LLM full reply (~30 tokens) | 1–2s |
| TTS (Piper Alba) | ~500ms |
| Vision (YOLO11n on 640×480) | ~45ms |
| **End-to-end button-press to speech** | **~3–4s** |

## Memory footprint

| Component | RAM |
|---|---|
| Gemma 4 E2B Q4_K_M | ~3 GB (CUDA) |
| mmproj (vision projector) | ~1 GB (CUDA) |
| whisper.cpp base.en | ~200 MB (CUDA) |
| YOLO11n | ~150 MB (CUDA) |
| Piper Alba | ~60 MB (CPU) |
| Python runtime + Silero VAD | ~150 MB |
| **Total active** | **~4.6 GB of 7.4 GB** |

Swap rarely activates outside of model load.

## Design decisions

### Two entry points, one shared pipeline

`server.py` (browser) and `local_input.py` (S3 button) both call into `pipeline.py` for transcribe → route → synthesize. Either path can be running on its own; the hardware path doesn't need the browser path, and vice versa. Pull the network cable and the call button still works.

### llama.cpp `/completion` instead of `/v1/chat/completions`

Gemma 4 ships with a "thinking" chat template that wraps replies in planning text. Through the OpenAI-compatible endpoint, the model emits internal monologue ("The user is asking my name. I need to respond briefly…") as the final answer. Under tight constraints it sometimes switches to Chinese mid-plan.

The fix is to use the raw `/completion` endpoint, hand-build a prompt with few-shot User/JARVIS examples, stop on `\nUser:` and `\n\n`, and cap `n_predict` at 60. Rock-solid one-sentence British-butler replies, no thinking-mode leaks. (See `pipeline.call_llama`.)

### Regex intent router before the LLM

`pipeline.route` checks lights, weather, and vision intents *before* calling Gemma. "Turn off the lights" never hits the LLM — it goes to a UDP packet to the WiZ strip on the LAN (`lights.py`) and replies with a hand-written one-liner. Common cases land in ~50ms; the full 3s pipeline only fires when we actually need to think.

### Silero VAD for endpointing on the hardware path

On the S3 path one tap starts capture; Silero VAD decides when the user is done (800ms of silence ends the turn, 15s hard cap). No second click, no fixed-window guesses.

### Piper instead of Coqui / XTTS / Bark

CPU-only, <500ms per sentence, intelligible British female (Alba en_GB). Frees the GPU for whisper + Gemma + YOLO. Quality is not OpenAI tier but more than enough for a butler. Voice is one path constant away from being swappable.

### whisper `base.en` over larger models

~11x realtime on Orin Nano with CUDA. `small.en` would be slightly more accurate but ~3x slower; for short voice commands `base.en` is near-perfect on clean speech.

### YOLO11n for vision instead of Gemma's vision tower

On "what do you see?"-style queries YOLO11n returns object detections in ~45ms, which we format into "I see a person and two cups." Much faster than asking Gemma to caption, and accurate enough for ambient awareness.

### Why not Ollama

llama.cpp's native build supports Gemma 4 on Orin Nano with CUDA at sm_87. Ollama (at the time of writing) didn't. llama.cpp also exposes the raw `/completion` endpoint needed to bypass the chat-template's thinking mode. NVIDIA's Jetson AI Lab explicitly recommends llama.cpp for E2B on Orin Nano.

## File layout

```
Jarvis-home/
├── server.py            WebSocket orchestrator (browser path)
├── local_input.py       HID button daemon (Anker S3 path)
├── pipeline.py          Shared transcribe / route / synthesize
├── audio_io.py          ALSA capture + playback for the S3
├── vad.py               Silero VAD endpointer
├── lights.py            WiZ smart-light intent + UDP control
├── weather.py           Open-Meteo intent + forecast
├── vision.py            YOLO11n wrapper
├── vision_intent.py     "what do you see" regex matcher
├── prompts.py           JARVIS persona (live prompt lives in pipeline.py)
├── index.html           Browser push-to-talk frontend
├── requirements.txt     Python deps
├── systemd/             Unit files + udev rule + install.sh for 24/7 operation
├── SETUP.md             One-time install on a fresh Jetson
└── RUNNING.md           Manual launch + systemd day-to-day commands
```

## Hardware

- NVIDIA Jetson Orin Nano Developer Kit 8GB, JetPack 6.2+, Super firmware unlock (~67 TOPS)
- NVMe SSD (microSD works but slow)
- Anker PowerConf S3 (USB mic + speaker + call button, vendor `291a`, product `3302`)
- WiZ smart light strip on the LAN (optional)
- Any device with a browser and mic, as a client (optional)

## Credits

llama.cpp / whisper.cpp by Georgi Gerganov and contributors · Gemma 4 by Google DeepMind · Piper TTS by Michael Hansen (rhasspy) · Alba voice from the Piper voices collection · YOLO11 by Ultralytics · Silero VAD by silero-team · WiZ Connected lights (local UDP protocol) · Built with patient pair-programming assistance from Claude.

MIT licensed.
