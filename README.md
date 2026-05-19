# jarvis-jetson

A fully local voice assistant running on NVIDIA Jetson Orin Nano Super 8GB. Speak to it from any browser on your network, get spoken replies in a British accent. Vision-capable (the LLM has a vision projector loaded). Zero cloud APIs.

**Stack:** Gemma 4 E2B (multimodal LLM) + whisper.cpp (STT) + Piper (TTS), glued together with a Python WebSocket server and a minimal HTML push-to-talk frontend.

**Why this exists:** I wanted a JARVIS-style assistant that runs entirely on my own hardware, hits the LLM, vision, STT, and TTS pipeline locally, and feels responsive (~3s end-to-end on Orin Nano in MAXN_SUPER mode).

## Latency budget (measured on Orin Nano Super)

| Stage | Time |
|---|---|
| STT (whisper.cpp base.en, CUDA) | ~300ms for 3s audio |
| LLM first token (Gemma 4 E2B Q4_K_M) | ~500ms |
| LLM full reply (one sentence, ~30 tokens) | ~1-2s |
| TTS (Piper Alba) | ~500ms |
| WebSocket round-trip | ~50ms |
| **End-to-end click-to-speech** | **~3-4s** |

## Hardware

- NVIDIA Jetson Orin Nano Developer Kit (8GB)
- JetPack 6.2+ with Super firmware unlock (~67 TOPS)
- NVMe SSD strongly recommended (microSD will work but slow)
- Any machine with a browser and mic (Mac, phone, laptop) as the client

## Architecture
Browser (Mac/phone)                    Jetson Orin Nano
─────────────────                      ────────────────
[click-to-record button]
↓ WebM/Opus audio
↓ WebSocket (port 8765)
────────→  server.py (orchestrator)
↓
ffmpeg: webm → 16kHz mono WAV
↓
whisper.cpp (CUDA, base.en)
↓ transcript
llama.cpp /completion endpoint
(Gemma 4 E2B Q4_K_M, port 8080)
↓ reply text
Piper TTS (Alba en_GB voice)
↓ WAV
←──────────────── WebSocket (base64 WAV)
[<audio> tag plays Alba's voice]

## Setup

### 1. Jetson power and storage

```bash
# Confirm Super mode
sudo nvpmodel -q   # Should show MAXN_SUPER
sudo jetson_clocks

# Confirm JetPack 6.x+
dpkg -l | grep nvidia-jetpack
```

### 2. Swap file (Gemma 4 E2B is tight on 8GB)

Default Jetson ZRAM swap is too small. Add a 16GB disk-backed swap on the NVMe:

```bash
sudo systemctl disable nvzramconfig
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl vm.swappiness=10
```

### 3. Build llama.cpp with CUDA for Orin (sm_87)

```bash
sudo apt install -y build-essential cmake git wget ffmpeg libcurl4-openssl-dev

cd ~
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="87" \
    -DGGML_NATIVE=ON \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j4
```

The `sm_87` target is critical — Orin's compute capability. Building generic ARM will work but be much slower.

### 4. Download Gemma 4 E2B + vision projector

```bash
mkdir -p ~/models
cd ~/models

# Main model (~3GB)
wget -O gemma-4-E2B-it-Q4_K_M.gguf \
    https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf

# Vision projector (~940MB) — required even if you only use text
# Note: the ggml-org mirror has had 404 issues; use the unsloth one
wget -O mmproj-F16.gguf \
    https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/mmproj-F16.gguf
```

### 5. Build whisper.cpp with CUDA

```bash
cd ~
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="87" \
    -DGGML_NATIVE=ON \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j4

# Download English-only base model
./models/download-ggml-model.sh base.en
```

Test: `./build/bin/whisper-cli -m models/ggml-base.en.bin -f samples/jfk.wav`

### 6. Install Piper + en_GB voice

```bash
cd ~
mkdir -p piper-tts && cd piper-tts
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz
tar -xvzf piper_linux_aarch64.tar.gz

mkdir -p voices && cd voices
# Alba — Scottish/British female (swap with any en_GB voice you prefer)
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json
```

Other voice options: `jenny_dioco` (Irish accent, warm), `alan` (male, BBC-ish), `cori/high`, `northern_english_male`. All at the same HuggingFace tree.

### 7. Clone this repo and install Python deps

```bash
cd ~
git clone https://github.com/<your-user>/jarvis-jetson.git jarvis
cd jarvis
pip3 install --user -r requirements.txt
```

If your paths differ from the defaults, edit the path constants at the top of `server.py`.

## Running

You need four terminals. (Or `tmux`. Or a `systemd` service — see "Next steps.")

**Terminal 1 — llama-server (the LLM)**

```bash
cd ~/llama.cpp && ./build/bin/llama-server \
  -m ~/models/gemma-4-E2B-it-Q4_K_M.gguf \
  --mmproj ~/models/mmproj-F16.gguf \
  --host 0.0.0.0 --port 8080 \
  -c 4096 -ngl 99 \
  --image-min-tokens 70 --image-max-tokens 70 -t 4 \
  --reasoning-budget 0
```

`--reasoning-budget 0` is essential. Without it, Gemma 4 emits internal planning monologue instead of replies.

**Terminal 2 — Jarvis WebSocket server**

```bash
cd ~/jarvis && python3 server.py
```

**Terminal 3 — HTTP server for the HTML frontend**

```bash
cd ~/jarvis && python3 -m http.server 8000
```

**Terminal 4 (on your client machine) — SSH tunnel**

Modern browsers block `getUserMedia` (microphone access) on non-HTTPS, non-localhost origins. SSH-forward both ports to your client as `localhost`:

```bash
ssh -L 8000:localhost:8000 -L 8765:localhost:8765 flash@<jetson-ip>
```

Then open `http://localhost:8000` in your browser. Click the button, speak, click again, hear Jarvis reply.

## Design decisions and lessons learned

### Why llama.cpp's `/completion` instead of `/v1/chat/completions`

Gemma 4 ships with a "thinking" chat template that wraps replies in planning text. Even with `--reasoning-budget 0`, the system prompt + chat template combo causes the model to emit internal monologue ("The user is asking my name. I need to respond briefly...") as the final answer instead of the actual reply. We bypass this by:

1. Using the raw `/completion` endpoint
2. Hand-building the prompt with four few-shot User/JARVIS examples
3. Setting stop tokens at `\nUser:` and `\n\n` so the model can't drift
4. Capping `n_predict` at 60 tokens

The result is rock-solid one-sentence replies in the JARVIS persona.

### Why Piper instead of Coqui/XTTS/Bark

Piper runs on CPU only, takes <500ms to synthesize a sentence on Orin Nano, and is good enough for a butler. CPU TTS frees the GPU for whisper + Gemma. Voice quality is decent (not OpenAI tier but very intelligible). The en_GB voices give it the right vibe.

### Why whisper base.en instead of larger

`base.en` runs at ~11x realtime on Orin Nano with CUDA. `small.en` would be slightly more accurate but ~3x slower. For short voice commands, `base.en` is more than enough — accuracy on clean speech is near-perfect.

### Why not Ollama

llama.cpp's native build supports Gemma 4 on Orin Nano; Ollama (as of writing) does not. llama.cpp also exposes the `/completion` endpoint which we need to bypass the chat template's thinking mode.

### Memory footprint at runtime

| Component | RAM |
|---|---|
| Gemma 4 E2B Q4_K_M | ~3 GB (CUDA) |
| mmproj (vision) | ~1 GB (CUDA) |
| whisper.cpp base.en | ~200 MB (CUDA) |
| Piper Alba | ~60 MB (CPU) |
| Python WebSocket server | ~50 MB |
| **Total active** | **~4.5 GB of 7.4 GB** |

Comfortable headroom. Swap rarely activates outside of model load.

## What's not in v1

These are deferred, not impossible:

- **Wake word** ("Hey Jarvis") — requires a USB mic, deferred until I get the Anker S330
- **Streaming TTS** — currently waits for full LLM reply before speaking. Sentence-buffered streaming would cut perceived latency by ~1s
- **Intent router** — currently every query hits the full LLM. A regex router could send "what time is it" to a 5ms fast path
- **Persistent memory** — Jarvis has no recollection across conversations
- **Local mic/speaker** — currently I/O happens in the browser, audio streams over the WebSocket. With real USB audio hardware we'd skip the browser layer
- **Multi-user** — single conversation slot, no isolation

## File layout
jarvis-jetson/
├── server.py          # WebSocket orchestrator (whisper → llama → piper)
├── prompts.py         # JARVIS persona definition
├── index.html         # Browser frontend (push-to-talk)
├── requirements.txt   # Python deps
├── .gitignore         # Excludes models, binaries, backups
├── README.md          # this file
└── LICENSE            # MIT

## Credits

- llama.cpp / whisper.cpp by Georgi Gerganov and contributors
- Gemma 4 by Google DeepMind
- Piper TTS by Michael Hansen (rhasspy)
- Alba voice from the Piper voices collection
