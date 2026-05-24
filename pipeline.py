"""
Shared pipeline functions used by both server.py (browser path) and local_input.py (S3 path).
Pure functions, no I/O frameworks. Transcribe, route, synthesize.
"""
import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import aiohttp

import lights
import weather
import vision
import memory
import time_intent
import hud_state
from vision_intent import is_vision_intent

# ---- Config (mirrors server.py) ----
HOME = Path.home()
WHISPER_BIN = HOME / "whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = HOME / "whisper.cpp/models/ggml-base.en.bin"
PIPER_BIN = HOME / "piper-tts/piper/piper"
PIPER_VOICE = HOME / "piper-tts/voices/en_GB-alba-medium.onnx"
LLAMA_URL = "http://127.0.0.1:8080/completion"

# Pad TTS output with leading silence to give the Anker S3 speaker time to wake from idle.
# Without this, the first ~0.5-1s of every reply is clipped because the USB speaker
# powers down between plays. 1.0s is a safe margin.
TTS_LEAD_SILENCE_S = 1.0

log = logging.getLogger("jarvis.pipeline")


def transcode_to_wav(input_path: str, output_path: str) -> bool:
    """ffmpeg: anything -> 16kHz mono S16 WAV for whisper."""
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
    """whisper-cli on a 16kHz mono WAV. Returns stripped transcript."""
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
    """JARVIS persona via /completion + few-shot. Bypasses Gemma 4 thinking template.

    Splices in any stored facts as a 'Known about the user:' line and the last
    few (user, jarvis) turns as additional history before the current question.
    """
    t0 = time.time()
    facts_block, history = memory.get_prompt_context()

    history_text = ""
    for u, j in history:
        history_text += f"User: {u}\nJARVIS: {j}\n\n"

    prompt = f"""{facts_block}You are JARVIS, a calm British butler. You always reply in ONE short sentence directly to the user. You never narrate, plan, or describe what you are doing. Always reply in English.

Rules you must follow:
- You cannot set timers, reminders, or alarms yourself. Those are handled by a separate system. If a request to schedule one reaches you, it means the system did not understand it — say you didn't catch the command, never invent a confirmation.
- You cannot control lights, appliances, the camera, or any physical device yourself. If asked, say it is beyond your reach.
- You cannot list, recall, or cancel anything that is scheduled. If asked, say you cannot see the schedule from here.

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

User: Set a reminder for five minutes.
JARVIS: I didn't catch that, sir — could you repeat?

User: Do I have any reminders?
JARVIS: I cannot see the schedule from here, sir.

User: Cancel my timer.
JARVIS: I cannot reach the schedule from here, sir.

{history_text}User: {user_text}
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
    """Piper TTS -> WAV at output_wav with leading silence (S3 speaker wake-up).

    Pads the front of the audio with TTS_LEAD_SILENCE_S seconds of silence so the
    USB speaker has time to wake from idle before the actual speech starts.
    """
    t0 = time.time()
    tmp_dir = os.path.dirname(output_wav) or "/tmp"
    raw_path = os.path.join(tmp_dir, "piper_raw.wav")

    # Run piper to a temp WAV
    result = subprocess.run(
        [str(PIPER_BIN), "--model", str(PIPER_VOICE), "--output_file", raw_path],
        input=text, capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"piper failed: {result.stderr[-500:]}")
        return False

    # Prepend silence with sox: `pad LEAD 0` adds LEAD seconds at the start, 0 at the end.
    sox_result = subprocess.run(
        ["sox", raw_path, output_wav, "pad", f"{TTS_LEAD_SILENCE_S}", "0"],
        capture_output=True, text=True
    )
    try:
        os.unlink(raw_path)
    except OSError:
        pass

    if sox_result.returncode != 0:
        log.error(f"sox pad failed: {sox_result.stderr[-300:]}")
        return False

    log.info(f"TTS ({time.time()-t0:.2f}s): wrote {output_wav} (+{TTS_LEAD_SILENCE_S}s lead silence)")
    return True


async def route(transcript: str, frame_provider=None, record_turn: bool = True) -> str:
    """Intent router. Returns the reply text.

    Args:
        transcript: STT output
        frame_provider: optional async callable () -> bytes|None for vision intents.
                        If None, vision intents return a graceful fallback.
        record_turn: if True (default), append this (user, jarvis) exchange to
                     persistent memory so later replies can refer back to it.
    """
    # HUD: we've got a transcript and we're about to decide what to do.
    hud_state.publish("thinking")
    reply = await _route_inner(transcript, frame_provider)
    if record_turn:
        try:
            memory.add_turn(transcript, reply)
        except Exception:
            log.exception("could not record turn in memory")
    # HUD: reply text is ready; about to synthesize and play.
    hud_state.publish("speaking", caption=reply)
    return reply


async def _route_inner(transcript: str, frame_provider) -> str:
    # Memory intents: remember / recall / forget.
    mem_reply = await asyncio.to_thread(memory.handle, transcript)
    if mem_reply is not None:
        log.info(f"INTENT memory: {mem_reply!r}")
        return mem_reply

    # Date / time / timer / reminder intents.
    time_reply = await asyncio.to_thread(time_intent.handle, transcript)
    if time_reply is not None:
        log.info(f"INTENT time: {time_reply!r}")
        return time_reply

    lights_reply = await asyncio.to_thread(lights.handle, transcript)
    if lights_reply is not None:
        log.info(f"INTENT lights: {lights_reply!r}")
        return lights_reply

    weather_reply = await asyncio.to_thread(weather.handle, transcript)
    if weather_reply is not None:
        log.info(f"INTENT weather: {weather_reply!r}")
        return weather_reply

    if is_vision_intent(transcript):
        log.info("INTENT vision: triggered")
        if frame_provider is None:
            return "I don't have a camera feed right now, sir."
        frame_bytes = await frame_provider()
        if frame_bytes is None:
            return "I don't have a camera feed right now, sir."
        try:
            reply = await asyncio.to_thread(vision.describe, frame_bytes)
            log.info(f"INTENT vision: {reply!r}")
            return reply
        except Exception:
            log.exception("vision failed")
            return "I had trouble processing that image, sir."

    try:
        return await call_llama(transcript)
    except Exception:
        log.exception("llama failed")
        return "I'm afraid my thoughts failed me, sir."
