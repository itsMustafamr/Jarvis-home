#!/usr/bin/env bash
# Install Jarvis as a set of systemd services on the Jetson.
# Run this ON THE JETSON, from inside the systemd/ directory of the repo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Copying unit files to /etc/systemd/system/"
sudo install -m 0644 \
  "$HERE/llama-server.service" \
  "$HERE/jarvis-server.service" \
  "$HERE/jarvis-http.service" \
  "$HERE/jarvis-local.service" \
  /etc/systemd/system/

echo "==> Installing udev rule for Anker PowerConf S3 hidraw access"
sudo install -m 0644 "$HERE/99-anker-s3.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Making sure flash is in the plugdev group (for hidraw)"
sudo usermod -aG plugdev flash || true

echo "==> Reloading systemd"
sudo systemctl daemon-reload

echo "==> Enabling + starting services"
# Order matters: llama-server first so the others can talk to it.
sudo systemctl enable --now llama-server.service
sleep 3
sudo systemctl enable --now jarvis-server.service jarvis-http.service jarvis-local.service

echo
echo "==> Status:"
sudo systemctl --no-pager status \
  llama-server.service \
  jarvis-server.service \
  jarvis-http.service \
  jarvis-local.service || true

echo
echo "Done. Tail logs with:"
echo "  journalctl -u llama-server -f"
echo "  journalctl -u jarvis-local -f"
