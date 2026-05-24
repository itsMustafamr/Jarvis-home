"""
Jarvis WebSocket server.
Browser sends audio (WebM/Opus) -> we transcode to WAV -> whisper -> intent-router OR llama -> piper -> WAV back.
Vision intents trigger an on-demand frame request to the browser.

This is the BROWSER path. The S3/hidraw path lives in local_input.py.
Both share pipeline.py for the actual transcribe/route/synthesize logic.
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
from pathlib import Path

import websockets

import lights
import weather
import pipeline

# ---- Config ----
WS_HOST = "0.0.0.0"
WS_PORT = 8765
FRAME_REQUEST_TIMEOUT = 15.0  # seconds to wait for browser to send a frame

# HUD bridge: server.py listens on this local UDP port for state events
# published by hud_state.publish() in any process (local_input.py, pipeline.py,
# or here in server.py). Each packet is broadcast over WebSocket to every
# client that subscribed with {"type": "subscribe", "channel": "hud"}.
HUD_UDP_HOST = "127.0.0.1"
HUD_UDP_PORT = 8766

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis")

# Per-connection state for pending frame requests.
_pending_frames: dict = {}

# All WebSocket clients that have subscribed to HUD state events.
_hud_subscribers: set = set()


async def request_frame(websocket) -> bytes | None:
    """Ask the browser for a webcam frame. Returns JPEG bytes or None on failure/denial/timeout."""
    ws_id = id(websocket)
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending_frames[ws_id] = future
    try:
        await websocket.send(json.dumps({"type": "frame_request"}))
        try:
            frame_msg = await asyncio.wait_for(future, timeout=FRAME_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("frame request timed out")
            return None
        if frame_msg.get("data_b64") is None:
            log.info(f"client declined frame: {frame_msg.get('reason', 'unknown')}")
            return None
        try:
            return base64.b64decode(frame_msg["data_b64"])
        except Exception as e:
            log.error(f"bad base64 frame: {e}")
            return None
    finally:
        _pending_frames.pop(ws_id, None)


async def handle_audio(websocket, audio_bytes: bytes):
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.webm")
        wav_path = os.path.join(tmp, "in.wav")
        out_wav = os.path.join(tmp, "out.wav")

        with open(in_path, "wb") as f:
            f.write(audio_bytes)
        log.info(f"received {len(audio_bytes)} bytes")

        await websocket.send(json.dumps({"type": "status", "msg": "transcribing"}))
        if not pipeline.transcode_to_wav(in_path, wav_path):
            await websocket.send(json.dumps({"type": "error", "msg": "transcode failed"}))
            return

        transcript = await asyncio.to_thread(pipeline.transcribe, wav_path)
        if not transcript:
            await websocket.send(json.dumps({"type": "error", "msg": "no speech detected"}))
            return
        await websocket.send(json.dumps({"type": "transcript", "text": transcript}))

        # Route. Pass a frame_provider that asks THIS browser for a frame on vision intents.
        async def frame_provider():
            await websocket.send(json.dumps({"type": "status", "msg": "looking"}))
            return await request_frame(websocket)

        await websocket.send(json.dumps({"type": "status", "msg": "thinking"}))
        reply = await pipeline.route(transcript, frame_provider=frame_provider)
        await websocket.send(json.dumps({"type": "reply", "text": reply}))

        # TTS
        await websocket.send(json.dumps({"type": "status", "msg": "speaking"}))
        ok = await asyncio.to_thread(pipeline.synthesize, reply, out_wav)
        if not ok:
            await websocket.send(json.dumps({"type": "error", "msg": "TTS failed"}))
            return

        if not os.path.exists(out_wav):
            await websocket.send(json.dumps({"type": "error", "msg": "TTS produced no audio"}))
            return
        with open(out_wav, "rb") as f:
            wav_b64 = base64.b64encode(f.read()).decode("ascii")
        await websocket.send(json.dumps({"type": "audio", "wav_b64": wav_b64}))
        await websocket.send(json.dumps({"type": "status", "msg": "idle"}))


async def _broadcast_to_hud(msg: dict) -> None:
    """Send one JSON payload to every HUD subscriber. Drops dead sockets."""
    if not _hud_subscribers:
        return
    payload = json.dumps(msg)
    dead = []
    for ws in list(_hud_subscribers):
        try:
            await ws.send(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _hud_subscribers.discard(ws)


class _HudUdpProtocol(asyncio.DatagramProtocol):
    """Receives UDP packets from hud_state.publish() and forwards them to
    all WebSocket HUD subscribers."""

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            log.warning(f"bad HUD UDP packet from {addr}: {data[:80]!r}")
            return
        # Fire-and-forget broadcast; schedule on the running loop.
        asyncio.create_task(_broadcast_to_hud(msg))


async def handler(websocket):
    log.info(f"client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await handle_audio(websocket, message)
            else:
                try:
                    msg = json.loads(message)
                except json.JSONDecodeError:
                    log.warning(f"non-JSON text message ignored: {message[:100]}")
                    continue
                msg_type = msg.get("type")
                if msg_type == "frame":
                    fut = _pending_frames.get(id(websocket))
                    if fut and not fut.done():
                        fut.set_result(msg)
                    else:
                        log.warning("frame received but no pending request")
                elif msg_type == "subscribe" and msg.get("channel") == "hud":
                    _hud_subscribers.add(websocket)
                    log.info(f"HUD subscriber added (total: {len(_hud_subscribers)})")
                    # Send the current state so the freshly-connected HUD
                    # doesn't sit blank waiting for the next event.
                    await websocket.send(json.dumps({"type": "state", "state": "idle"}))
                else:
                    log.info(f"unhandled text message: {msg_type}")
    except websockets.ConnectionClosed:
        log.info("client disconnected")
    finally:
        _pending_frames.pop(id(websocket), None)
        if websocket in _hud_subscribers:
            _hud_subscribers.discard(websocket)
            log.info(f"HUD subscriber removed (total: {len(_hud_subscribers)})")


async def main():
    log.info(f"jarvis ws server starting on {WS_HOST}:{WS_PORT}")
    log.info(f"  whisper: {pipeline.WHISPER_BIN}")
    log.info(f"  llama:   {pipeline.LLAMA_URL}")
    log.info(f"  piper:   {pipeline.PIPER_BIN} (voice: {pipeline.PIPER_VOICE.name})")
    log.info(f"  lights:  WiZ at {lights.WIZ_IP}:{lights.WIZ_PORT}")
    log.info(f"  weather: Open-Meteo (default city: {weather.DEFAULT_CITY})")
    log.info(f"  vision:  YOLO11n loaded")

    # HUD UDP listener: receives state events from any process in the system.
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        lambda: _HudUdpProtocol(),
        local_addr=(HUD_UDP_HOST, HUD_UDP_PORT),
    )
    log.info(f"  HUD bridge: listening on udp://{HUD_UDP_HOST}:{HUD_UDP_PORT}")

    async with websockets.serve(handler, WS_HOST, WS_PORT, max_size=10_000_000):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
