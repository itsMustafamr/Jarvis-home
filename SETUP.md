# Setup

One-time install on a fresh Jetson Orin Nano Super 8GB with JetPack 6.2+.

## 1. Jetson power and storage

```bash
sudo nvpmodel -q          # should show MAXN_SUPER
sudo jetson_clocks
dpkg -l | grep nvidia-jetpack
```

## 2. Swap file (Gemma 4 E2B is tight on 8GB)

Default ZRAM swap is too small and competes with model RAM. Add a 16GB disk-backed swap on the NVMe:

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

## 3. Build llama.cpp with CUDA for Orin (sm_87)

```bash
sudo apt install -y build-essential cmake git wget ffmpeg sox libcurl4-openssl-dev alsa-utils

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

`sm_87` is Orin's compute capability. Building generic ARM works but is much slower.

## 4. Download Gemma 4 E2B + vision projector

```bash
mkdir -p ~/models && cd ~/models

wget -O gemma-4-E2B-it-Q4_K_M.gguf \
    https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf

wget -O mmproj-F16.gguf \
    https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/mmproj-F16.gguf
```

## 5. Build whisper.cpp with CUDA

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

./models/download-ggml-model.sh base.en
```

Quick test:

```bash
./build/bin/whisper-cli -m models/ggml-base.en.bin -f samples/jfk.wav
```

## 6. Install Piper + en_GB voice

```bash
cd ~ && mkdir -p piper-tts && cd piper-tts
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz
tar -xvzf piper_linux_aarch64.tar.gz

mkdir -p voices && cd voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json
```

Other en_GB voices live in the same HF tree: `jenny_dioco`, `alan`, `cori/high`, `northern_english_male`. Swap by changing `PIPER_VOICE` in `pipeline.py`.

## 7. YOLO11n (vision)

```bash
pip3 install --user ultralytics
mkdir -p ~/jarvis-vision-test && cd ~/jarvis-vision-test
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
```

## 8. Clone Jarvis-home

```bash
cd ~
git clone https://github.com/itsMustafamr/Jarvis-home.git jarvis
cd jarvis
pip3 install --user -r requirements.txt
pip3 install --user silero-vad torch
```

If your paths differ from the defaults (`~/whisper.cpp`, `~/piper-tts`, `~/models`), edit the constants at the top of `pipeline.py`.

## 9. Anker PowerConf S3

Plug into a USB port on the Jetson. Verify:

```bash
arecord -l   # should list "PowerConf S3" as card S3
lsusb | grep 291a   # vendor 291a, product 3302
```

If the ALSA card name isn't `S3`, update `S3_DEVICE` in `audio_io.py`.

## 10. WiZ light strip (optional)

Find its LAN IP (router admin page or `nmap -p 38899 10.0.0.0/24`) and set `WIZ_IP` in `lights.py`. If you don't have one, the lights intent will simply time out and fall through to the LLM.

## 11. First run

Test manually with the commands in [`RUNNING.md`](RUNNING.md). Once it all works, install the systemd units:

```bash
cd ~/jarvis/systemd && ./install.sh
```
