# Running Jarvis

Two ways to run it on the Jetson: **manual** (tmux windows, for testing and dev) or **systemd** (one command, runs forever, survives reboots).

All commands assume the user is `flash`, the repo is at `/home/flash/jarvis`, and the Python venv is at `/home/flash/jarvis-venv` (activated by the `jarvis-env` shell alias). Adjust paths if yours differ.

> **Important:** Every Python script in this project requires the venv. Either run `jarvis-env` first in the shell, or call the scripts with the venv's interpreter directly: `/home/flash/jarvis-venv/bin/python3 server.py`. The system `python3` does not have `ultralytics`, `torch`, or `silero-vad`.

---

## tmux 90-second primer

```bash
tmux new -s jarvis              # create a session named "jarvis" (also attaches)
tmux ls                         # list running sessions
tmux attach -t jarvis           # reattach to it later
tmux kill-session -t jarvis     # nuke it
```

Inside a session, every shortcut starts with `Ctrl-b` (the "prefix") then a second key:

| Keys | Action |
|---|---|
| `Ctrl-b` `d` | Detach (session keeps running in background) |
| `Ctrl-b` `c` | Create a new window |
| `Ctrl-b` `0` … `9` | Switch to window N |
| `Ctrl-b` `n` / `p` | Next / previous window |
| `Ctrl-b` `,` | Rename current window |
| `Ctrl-b` `[` | Scrollback mode (arrows / PgUp, `q` to exit) |

Stick to windows; ignore splits/panes until you need them.

---

## Manual start (tmux windows)

```bash
ssh flash@<jetson-ip>
tmux new -s jarvis              # creates window 0
```

**Window 0 — llama-server (the LLM)**

```bash
cd ~/llama.cpp && ./build/bin/llama-server \
  -m ~/models/gemma-4-E2B-it-Q4_K_M.gguf \
  --mmproj ~/models/mmproj-F16.gguf \
  --host 0.0.0.0 --port 8080 \
  -c 4096 -ngl 99 \
  --image-min-tokens 70 --image-max-tokens 70 -t 4 \
  --reasoning-budget 0
```

Wait until you see `srv main: server is listening on http://0.0.0.0:8080` before starting the others. No venv needed — this is a C++ binary, not Python.

Then press `Ctrl-b c` to open window 1 and run the rest. Each window starts as a fresh shell, so the venv must be activated in each one.

**Window 1 — Anker S3 button daemon (the headless / Mac-off path)**

```bash
jarvis-env
cd ~/jarvis && python3 local_input.py
```

This is the one that makes "Mac off, press the button, it works" true. Listens for HID events from the S3 over USB, captures audio from the S3 mic, runs the full pipeline, plays the reply through the S3 speaker. For your two-process showcase setup, this plus llama-server is all you need.

**Window 2 — Jarvis WebSocket server (browser path, optional)**

```bash
jarvis-env
cd ~/jarvis && python3 server.py
```

**Window 3 — HTTP server for index.html (only if you want the browser frontend)**

```bash
jarvis-env
cd ~/jarvis && python3 -m http.server 8000
```

(The http.server module is in stdlib so technically the venv isn't required here, but it keeps the four windows symmetrical.)

When everything is up, press `Ctrl-b d` to detach. Close the SSH window. Everything keeps running. Come back later with `ssh flash@<jetson-ip>` then `tmux attach -t jarvis`.

**Quick smoke tests**

```bash
# LLM is up?
curl -s http://127.0.0.1:8080/health

# Which ports are listening?
ss -tlnp | grep -E '8765|8080|8000'

# S3 plugged in and recognized?
arecord -l | grep -i powerconf
ls /dev/hidraw*

# Venv has the right packages?
jarvis-env && python3 -c "import ultralytics, torch, silero_vad, websockets, aiohttp; print('OK')"
```

---

## Browser access from another machine

The page needs HTTPS or `localhost` to get mic permission. Cheapest fix: SSH tunnel from the client.

```bash
# From your Mac, laptop, etc:
ssh -L 8000:localhost:8000 -L 8765:localhost:8765 flash@<jetson-ip>
# then open http://localhost:8000 in the browser

jetson-ip = flash@10.0.0.188 or flash@10.0.0.187 mostly.
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

The Python units use `/home/flash/jarvis-venv/bin/python3` directly, so they pick up the venv's packages without anything to activate. If your venv lives somewhere else, edit `ExecStart=` in each `.service` file before running `install.sh`.

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

After this you should be able to:

1. Reboot the Jetson (`sudo reboot`).
2. Wait ~30s for the LLM to load.
3. Press the Anker S3 call button.
4. Hear Alba reply — with the Mac off and no SSH session anywhere.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'ultralytics'` (or `torch`, or `silero_vad`)**
You ran the script with system Python instead of the venv. Run `jarvis-env` first, then `python3 your_script.py`. For systemd, confirm `ExecStart=` points at `/home/flash/jarvis-venv/bin/python3` in the relevant `.service` file.

**`llama-server` won't start under systemd**
Run the ExecStart command manually as `flash` first to see the real error. Most common: model file path wrong, or CUDA not visible because the unit is running under a stripped environment. If CUDA is the issue, add `Environment=PATH=/usr/local/cuda/bin:/usr/bin:/bin` to the unit.

**`jarvis-local` errors with `Permission denied` on `/dev/hidrawX`**
The udev rule didn't take effect. Re-run `sudo udevadm control --reload-rules && sudo udevadm trigger`, unplug and replug the S3, and confirm `flash` is in `plugdev` (`groups flash`). A logout/login may be required for the group change.

**`jarvis-local` errors with `arecord: no such PCM` or similar ALSA error**
The S3 isn't showing up as ALSA card "S3". Check `arecord -l`. If the card name differs, update `S3_DEVICE` in `audio_io.py` and `S3_ALSA_CARD` in `local_input.py`.

**Jarvis replies with planning text or in Chinese**
`--reasoning-budget 0` isn't being passed. Check the unit file's `ExecStart`, or run `systemctl cat llama-server`.

**Jetson IP keeps changing**
Use Tailscale (the `100.x.x.x` address never changes) or set a static DHCP reservation in your router.
