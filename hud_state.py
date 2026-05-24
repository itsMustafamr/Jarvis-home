"""
Fire-and-forget HUD state publisher.

Any process that drives the pipeline (local_input.py for the Anker S3 path,
server.py for the browser path, or pipeline.py itself for the shared route /
synthesize phases) can call hud_state.publish(state, caption=None) at a state
transition. The publish() call is non-blocking and silent — it sends one UDP
packet to 127.0.0.1:8766 and returns immediately.

server.py owns the UDP listener on 8766 and forwards each packet over its
WebSocket to any HUD page that subscribed with
    {"type": "subscribe", "channel": "hud"}.

If server.py isn't running the packet is dropped — the HUD is decorative and
should never block or fail any other path.

states: "idle" | "listening" | "thinking" | "speaking" | "error"
"""
from __future__ import annotations

import json
import logging
import socket
from typing import Optional

log = logging.getLogger("jarvis.hud_state")

UDP_HOST = "127.0.0.1"
UDP_PORT = 8766

_sock: Optional[socket.socket] = None


def _sock_lazy() -> socket.socket:
    """Lazily create the UDP socket on first publish."""
    global _sock
    if _sock is None:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Non-blocking so a stalled receive queue can never delay us.
        _sock.setblocking(False)
    return _sock


def publish(state: str, caption: Optional[str] = None) -> None:
    """Send one state-change packet. Silent on any error.

    `state` is the HUD state name. `caption` is optional text that the HUD
    can show beneath the orb (typically Jarvis's reply during "speaking").
    """
    try:
        payload: dict = {"type": "state", "state": state}
        if caption is not None:
            payload["caption"] = caption
        _sock_lazy().sendto(
            json.dumps(payload).encode("utf-8"),
            (UDP_HOST, UDP_PORT),
        )
    except Exception:
        # HUD updates are best-effort. A missing listener (server.py not
        # running) or a transient socket error must never propagate.
        log.debug("hud_state.publish failed", exc_info=True)


if __name__ == "__main__":
    # python3 hud_state.py listening "..."
    import sys

    logging.basicConfig(level=logging.DEBUG)
    state = sys.argv[1] if len(sys.argv) > 1 else "idle"
    caption = sys.argv[2] if len(sys.argv) > 2 else None
    publish(state, caption)
    print(f"published state={state!r} caption={caption!r} to udp://{UDP_HOST}:{UDP_PORT}")
