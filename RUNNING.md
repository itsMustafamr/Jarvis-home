# Running Jarvis

Two ways to run it on the Jetson: **manual** (four terminals, for testing and dev) or **systemd** (one command, runs forever, survives reboots).

All commands assume the user is `flash` and the repo is at `/home/flash/jarvis`. Adjust paths if yours differ.

---

## Manual start (four terminals via tmux or ssh)

```bash
ssh flash@<jetson-ip>
tmux new -s jarvis
# Ctrl-b " to split, Ctrl-b o to switch panes
```

**Pane 1 — llama-server (the LLM)**

```bash
cd ~/llama.cpp && ./build/bin/llama-server \
  -m ~/models/gemma-4-E2B-it-Q4_K_M.gguf \
  --mmproj ~/models/mmproj-F16.gguf \
  --host 0.0.0.0 --port 8080 \
  -c 4096 -ngl 99 \
  --image-min-tokens 70 --image-max-tokens 70 -t 4 \
  --reasoning-budget 0
```

Wait until you see `main: HTTP server listening` before starting the others.

**Pane 2 — Jarvis WebSocket server (browser path)**

```bash
cd ~/jarvis && python3 server.py
```

**Pane 3 — HTTP server (only needed for browser frontend)**

```bash
cd ~/jarvis && python3 -m http.server 8000
```

**Pane 4 — Anker S3 button daemon (the headless path)**

```bash
cd ~/jarvis && python3 local_input.py
```

This is the one that makes "Mac off, press the button, it works" true. It listens for HID events from the S3 over USB, captures audio from the S3 mic, runs the full pipeline, and plays the reply through the S3 speaker.

**Quick smoke tests**

```bash
# LLM is up?
curl -s http://127.0.0.1:8080/health

# WebSocket is up?
ss -tlnp | grep -E '8765|8080|8000'

# S3 plugged in and recognized?
arecord -l | grep -i powerconf
ls /dev/hidraw*
```

---

## Browser access from another machine

The page needs HTTPS or `localhost` to get mic permission. Cheapest fix: SSH tunnel from the client.

```bash
# From your Mac, phone-over-USB, laptop, whatever:
ssh -L 8000:localhost:8000 -L 8765:localhost:8765 flash@<jetson-ip>
# then open http://localhost:8000 in the browser
```

For phone access without an SSH tunnel, use Tailscale + `tailscale cert` to get a real `*.ts.net` HTTPS cert, then put Caddy or nginx in front of 8000 and 8765 as a TLS reverse proxy.

---

## Run as systemd services (24/7, survives reboots)

Once on the Jetson:

```bash
cd ~/jarvis/systemd
./install.sh
```

That copies the four `.service` files into `/etc/systemd/system/`, installs a udev rule so the `plugdev` group can read the S3's hidraw device, adds `flash` to `plugdev`, then enables and starts everything in the right order.

**Day-to-day commands**

```bash
# Status
sudo systemctl status llama-server jarvis-server jarvis-http jarvis-local

# Restart one
sudo systemctl restart jarvis-local

# Restart everything
sudo systemctl restart llama-server jarvis-server jarvis-http jarvis-local

# Stop / disable
sudo systemctl disable --now jarvis-local

# Live logs
journalctl -u llama-server -f
journalctl -u jarvis-local -f
journalctl -u jarvis-server -f
```

After this point you should be able to:

1. Reboot the Jetson (`sudo reboot`).
2. Wait ~30s.
3. Press the Anker S3 call button.
4. Hear Alba reply — with the Mac off and no SSH session anywhere.

---

## Troubleshooting

**`llama-server` won't start under systemd**
Run the ExecStart command manually as `flash` first to see the real error. Most common: model file path wrong, or CUDA not visible because the unit is running under a stripped environment. If CUDA is the issue, add `Environment=PATH=/usr/local/cuda/bin:/usr/bin:/bin` to the unit.

**`jarvis-local` errors with `Permission denied` on `/dev/hidrawX`**
The udev rule didn't take effect. Re-run `sudo udevadm control --reload-rules && sudo udevadm trigger`, unplug and replug the S3, and confirm `flash` is in `plugdev` (`groups flash`).

**`jarvis-local` errors with `arecord: no such PCM` or similar ALSA error**
The S3 isn't showing up as ALSA card "S3". Check `arecord -l`. If the card name differs, update `S3_DEVICE` in `audio_io.py` and `S3_ALSA_CARD` in `local_input.py`.

**Jarvis replies with planning text or in Chinese**
`--reasoning-budget 0` isn't being passed. Check the unit file's `ExecStart`, or run `systemctl cat llama-server`.

**Jetson IP keeps changing**
Use Tailscale (the `100.x.x.x` address never changes) or set a static DHCP reservation in your router.
