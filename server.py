"""
Jarvis WebSocket server.
Browser sends audio (WebM/Opus) -> we transcode to WAV -> whisper -> intent-router OR llama -> piper -> WAV back.
"""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import aiohttp
import websockets

from prompts import JARVIS_SYSTEM_PROMPT
import lights
import weather

# ---- Config ----
HOME = Path.home()
WHISPER_BIN = HOME / "whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = HOME / "whisper.cpp/models/ggml-base.en.bin"
PIPER_BIN = HOME / "piper-tts/piper/piper"
PIPER_VOICE = HOME / "piper-tts/voices/en_GB-alba-medium.onnx"
LLAMA_URL = "http://127.0.0.1:8080/completion"
WS_HOST = "0.0.0.0"
WS_PORT = 8765

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis")


def transcode_to_wav(input_path: str, output_path: str) -> bool:
    """Browser sends webm/opus. Whisper wants 16kHz mono WAV. ffmpeg handles it."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1",
         "-acodec", "pcm_s16le", output_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"ffmpeg failed: {result.stderr[-500:]}")
        return False
    return True


def transcribe(wav_path: str) -> str:
    """Run whisper-cli on a WAV, return the transcript."""
    t0 = time.time()
    result = subprocess.run(
        [str(WHISPER_BIN), "-m", str(WHISPER_MODEL), "-f", wav_path,
         "-nt", "-l", "en"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"whisper failed: {result.stderr[-500:]}")
        return ""
    transcript = result.stdout.strip()
    log.info(f"STT ({time.time()-t0:.2f}s): {transcript!r}")
    return transcript


async def call_llama(user_text: str) -> str:
    """Use raw /completion endpoint with hand-built prompt.
    Bypasses chat template's thinking-mode entirely."""
    t0 = time.time()

    prompt = f"""You are JARVIS, a calm British butler. You always reply in ONE short sentence directly to the user. You never narrate, plan, or describe what you are doing. Always reply in English.

User: How are you?
JARVIS: Operational, sir.

User: What is your name?
JARVIS: JARVIS, sir.

User: What is the capital of France?
JARVIS: Paris, sir.

User: Tell me a joke.
JARVIS: I would, sir, but humour requires an audience prepared to laugh.

User: Turn off the kettle.
JARVIS: I'm afraid that's beyond my reach, sir.

User: Open the door.
JARVIS: I haven't the hands for that, sir.

User: {user_text}
JARVIS:"""

    payload = {
        "prompt": prompt,
        "n_predict": 60,
        "temperature": 0.6,
        "top_p": 0.9,
        "stop": ["\nUser:", "\n\n", "User:", "JARVIS:"],
        "stream": False,
        "cache_prompt": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(LLAMA_URL, json=payload, timeout=60) as r:
            data = await r.json()

    reply = data.get("content", "").strip()
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    if not reply:
        reply = "Apologies sir, I missed that."
    log.info(f"LLM ({time.time()-t0:.2f}s): {reply!r}")
    return reply


def synthesize(text: str, output_wav: str) -> bool:
    """Run piper, write WAV to disk."""
    t0 = time.time()
    result = subprocess.run(
        [str(PIPER_BIN), "--model", str(PIPER_VOICE), "--output_file", output_wav],
        input=text, capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"piper failed: {result.stderr[-500:]}")
        return False
    log.info(f"TTS ({time.time()-t0:.2f}s): wrote {output_wav}")
    return True


async def handle_audio(websocket, audio_bytes: bytes):
    """Full pipeline for one user utterance."""
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.webm")
        wav_path = os.path.join(tmp, "in.wav")
        out_wav = os.path.join(tmp, "out.wav")

        with open(in_path, "wb") as f:
            f.write(audio_bytes)
        log.info(f"received {len(audio_bytes)} bytes")

        # 1. webm -> wav
        await websocket.send(json.dumps({"type": "status", "msg": "transcribing"}))
        if not transcode_to_wav(in_path, wav_path):
            await websocket.send(json.dumps({"type": "error", "msg": "transcode failed"}))
            return

        # 2. STT
        transcript = await asyncio.to_thread(transcribe, wav_path)
        if not transcript:
            await websocket.send(json.dumps({"type": "error", "msg": "no speech detected"}))
            return
        await websocket.send(json.dumps({"type": "transcript", "text": transcript}))

        # 3a. Intent router — bypass LLM for known commands
        lights_reply = await asyncio.to_thread(lights.handle, transcript)
        weather_reply = None
        if lights_reply is None:
            weather_reply = await asyncio.to_thread(weather.handle, transcript)

        if lights_reply is not None:
            log.info(f"INTENT lights: {lights_reply!r}")
            reply = lights_reply
            await websocket.send(json.dumps({"type": "reply", "text": reply}))
        elif weather_reply is not None:
            log.info(f"INTENT weather: {weather_reply!r}")
            reply = weather_reply
            await websocket.send(json.dumps({"type": "reply", "text": reply}))
        else:
            # 3b. LLM (everything we can't shortcut)
            await websocket.send(json.dumps({"type": "status", "msg": "thinking"}))
            try:
                reply = await call_llama(transcript)
            except Exception as e:
                log.exception("llama failed")
                await websocket.send(json.dumps({"type": "error", "msg": f"LLM error: {e}"}))
                return
            await websocket.send(json.dumps({"type": "reply", "text": reply}))

        # 4. TTS
        await websocket.send(json.dumps({"type": "status", "msg": "speaking"}))
        ok = await asyncio.to_thread(synthesize, reply, out_wav)
        if not ok:
            await websocket.send(json.dumps({"type": "error", "msg": "TTS failed"}))
            return

        # 5. Send WAV back, base64 encoded inside JSON
        if not os.path.exists(out_wav):
            await websocket.send(json.dumps({"type": "error", "msg": "TTS produced no audio"}))
            return
        with open(out_wav, "rb") as f:
            wav_b64 = base64.b64encode(f.read()).decode("ascii")
        await websocket.send(json.dumps({"type": "audio", "wav_b64": wav_b64}))
        await websocket.send(json.dumps({"type": "status", "msg": "idle"}))


async def handler(websocket):
    log.info(f"client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await handle_audio(websocket, message)
            else:
                log.info(f"text message: {message[:100]}")
    except websockets.ConnectionClosed:
        log.info("client disconnected")


async def main():
    log.info(f"jarvis ws server starting on {WS_HOST}:{WS_PORT}")
    log.info(f"whisper: {WHISPER_BIN}")
    log.info(f"llama:   {LLAMA_URL}")
    log.info(f"piper:   {PIPER_BIN} (voice: {PIPER_VOICE.name})")
    log.info(f"lights:  WiZ at {lights.WIZ_IP}:{lights.WIZ_PORT}")
    log.info(f"weather: Open-Meteo (default city: {weather.DEFAULT_CITY})")
    async with websockets.serve(handler, WS_HOST, WS_PORT, max_size=10_000_000):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
