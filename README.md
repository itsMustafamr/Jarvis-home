Last login: Tue May 19 02:55:04 on ttys010
mohd7@Mohammeds-MacBook-Pro ~ % jet
Welcome to Ubuntu 22.04.5 LTS (GNU/Linux 5.15.185-tegra aarch64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

This system has been minimized by removing packages and content that are
not required on a system that users do not log into.

To restore this content, you can run the 'unminimize' command.

Expanded Security Maintenance for Applications is not enabled.

0 updates can be applied immediately.

50 additional security updates can be applied with ESM Apps.
Learn more about enabling ESM Apps service at https://ubuntu.com/esm

Last login: Tue May 19 02:55:14 2026 from 100.74.196.37
flash@flash-nano:~$ cd ~/jarvis
grep -in "password\|secret\|token\|10\.0\.0\|192\.168\|api_key" server.py prompts.py index.html
server.py:105:    # Strip any leaked thinking tokens just in case
flash@flash-nano:~/jarvis$ cd ~/jarvis
grep -in "password\|secret\|token\|10\.0\.0\|192\.168\|api_key" server.py prompts.py index.html
ls -la
server.py:105:    # Strip any leaked thinking tokens just in case
total 44
drwxrwxr-x  3 flash flash 4096 May 19 02:55 .
drwxr-x--- 26 flash flash 4096 May 18 03:36 ..
-rw-rw-r--  1 flash flash 3947 May 18 03:39 index.html
-rw-rw-r--  1 flash flash  696 May 18 23:16 prompts.py
drwxrwxr-x  2 flash flash 4096 May 18 23:17 __pycache__
-rw-rw-r--  1 flash flash 6801 May 19 02:55 server.py
-rw-rw-r--  1 flash flash 5881 May 18 16:51 server.py.bak
-rw-rw-r--  1 flash flash 7253 May 19 02:55 server.py.bak2
flash@flash-nano:~/jarvis$ cd ~/jarvis
cat > .gitignore <<'EOF'
# Backups
*.bak
*.bak2
*.bak3

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/

# Models and binaries (downloaded separately per README)
*.gguf
*.bin
*.onnx
*.onnx.json
piper_linux_*.tar.gz
models/
voices/

# OS
EOFt.wavudio
flash@flash-nano:~/jarvis$ cd ~/jarvis
cat > requirements.txt <<'EOF'
websockets>=12.0
aiohttp>=3.9.0
numpy>=1.24.0
EOF
flash@flash-nano:~/jarvis$ cd ~/jarvis
cat > LICENSE <<'EOF'
MIT License

Copyright (c) 2026 Mohammed Musthafa Rafi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
flash@flash-nano:~/jarvis$
flash@flash-nano:~/jarvis$ cd ~/jarvis
cat > README.md <<'EOF'
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
## Architectureith a browser and mic (Mac, phone, laptop) as the client
> ^C
flash@flash-nano:~/jarvis$ cd ~/jarvis
flash@flash-nano:~/jarvis$  at > README.md <<'EOF'
# jarvis-jetson             d ~/jarvis
cat > README.md <<'EOF'
# jarvis-jetsonoice assistant running on NVIDIA Jetson Orin Nano Super 8GB. Spea                                                                                A fully local voice assistant running on NVIDIA Jetson Orin Nano Super 8GB. Speak to it from any browser on your network, get spoken replies in a British accent. Vision-capable (the LLM has a vision projector loaded). Zero cloud APIs. glued                                                                                **Stack:** Gemma 4 E2B (multimodal LLM) + whisper.cpp (STT) + Piper (TTS), glued together with a Python WebSocket server and a minimal HTML push-to-talk frontend.Why this exists:** I wanted a JARVIS-style assistant that runs entirely on my                                                                                 **Why this exists:** I wanted a JARVIS-style assistant that runs entirely on my own hardware, hits the LLM, vision, STT, and TTS pipeline locally, and feels responsive (~3s end-to-end on Orin Nano in MAXN_SUPER mode).

## Latency budget (measured on Orin Nano Super)

| Stage | Time |pp base.en, CUDA) | ~300ms for 3s audio |
|---|---|
| STT (whisper.cpp base.en, CUDA) | ~300ms for 3s audio1-2~1-2s |
| TTS (irst token (Gemma 4 E2B Q4_K_M) | ~500m
| LLM full reply (one sentence, ~30 tokens) | ~1-25 ~50ms |
##TTS (Piper Alba) | ~50ech** | **~3-4s**nd mic (Mac, phone, laptop) as the c
  WebSocket round-trip | ~50ms
## Architectureith a browser and mic (Mac, phone, laptop) as the client
>
>
> ^C
flash@flash-nano:~/jarvis$ cd ~/jarvis
cat > README.md <<'EOF'
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
EOFlba voice from the Piper voices collectionand contributorsama → piper)rams ov
flash@flash-nano:~/jarvis$ cd ~/jarvis
rm -f server.py.bak server.py.bak2
rm -rf __pycache__

ls -la
total 48
drwxrwxr-x  2 flash flash 4096 May 19 03:02 .
drwxr-x--- 26 flash flash 4096 May 18 03:36 ..
-rw-rw-r--  1 flash flash  301 May 19 03:00 .gitignore
-rw-rw-r--  1 flash flash 3947 May 18 03:39 index.html
-rw-rw-r--  1 flash flash 1079 May 19 03:00 LICENSE
-rw-rw-r--  1 flash flash  696 May 18 23:16 prompts.py
-rw-rw-r--  1 flash flash 9174 May 19 03:02 README.md
-rw-rw-r--  1 flash flash   46 May 19 03:00 requirements.txt
-rw-rw-r--  1 flash flash 6801 May 19 02:55 server.py
flash@flash-nano:~/jarvis$ cd ~/jarvis

git init
git branch -M main
hint: Using 'master' as the name for the initial branch. This default branch name
hint: is subject to change. To configure the initial branch name to use in all
hint: of your new repositories, which will suppress this warning, call:
hint:
hint: 	git config --global init.defaultBranch <name>
hint:
hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
hint: 'development'. The just-created branch can be renamed via this command:
hint:
hint: 	git branch -m <name>
Initialized empty Git repository in /home/flash/jarvis/.git/
flash@flash-nano:~/jarvis$ git config user.name itsMustafamr
flash@flash-nano:~/jarvis$ git config user.email mr.mohdmustafa007@gmail.com
flash@flash-nano:~/jarvis$ git add .
flash@flash-nano:~/jarvis$ git status
On branch main

No commits yet

Changes to be committed:
  (use "git rm --cached <file>..." to unstage)
	new file:   .gitignore
	new file:   LICENSE
	new file:   README.md
	new file:   index.html
	new file:   prompts.py
	new file:   requirements.txt
	new file:   server.py

flash@flash-nano:~/jarvis$ git commit -m "Initial commit: local voice assistant on Jetson Orin Nano

- Gemma 4 E2B via llama.cpp (CUDA, sm_87)
- whisper.cpp base.en for STT
- Piper Alba (en_GB) for TTS
- Python WebSocket orchestrator
- Browser push-to-talk frontend
- Uses /completion endpoint to bypass Gemma's thinking chat template"
[main (root-commit) 6d0a8a5] Initial commit: local voice assistant on Jetson Orin Nano
 7 files changed, 656 insertions(+)
 create mode 100644 .gitignore
 create mode 100644 LICENSE
 create mode 100644 README.md
 create mode 100644 index.html
 create mode 100644 prompts.py
 create mode 100644 requirements.txt
 create mode 100644 server.py
flash@flash-nano:~/jarvis$ cd ~/jarvis
flash@flash-nano:~/jarvis$ git remote add origin https://github.com/itsMustafamr
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
"README.md" 259L, 9174B                                       1,1           Top
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
"README.md" 259L, 9174B                                       1,1           Top# jarvis-jetson

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
