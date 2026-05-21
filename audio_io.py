"""
ALSA capture/playback for the Anker PowerConf S3.
Streaming arecord -> VAD -> WAV. aplay for output.
"""
import logging
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from vad import SileroEndpointer, CHUNK_SAMPLES, SAMPLE_RATE

log = logging.getLogger("jarvis.audio_io")

# S3 ALSA addressing. Card name comes from `arecord -l` -> "PowerConf S3" -> card=S3.
S3_DEVICE = "plughw:CARD=S3,DEV=0"


def capture_until_silence(
    output_wav_path: str,
    endpointer: SileroEndpointer,
    device: str = S3_DEVICE,
    on_state_change=None,
) -> str:
    """Stream audio from `device` through `endpointer` until silence or timeout.

    Writes a 16kHz mono S16 WAV to `output_wav_path`.

    Args:
        output_wav_path: where to save the captured WAV.
        endpointer: pre-initialized SileroEndpointer (caller is responsible for .start()).
        device: ALSA device string.
        on_state_change: optional callable(new_state: str) called when VAD state transitions.

    Returns:
        Final state: "endpoint", "timeout", or "no_speech".
        - "endpoint" = normal completion, speech detected and silence threshold met
        - "timeout"  = hit max_duration_s without endpointing
        - "no_speech" = speech never started before timeout (treat as empty)
    """
    endpointer.start()
    bytes_per_chunk = CHUNK_SAMPLES * 2  # int16 = 2 bytes/sample, mono

    # arecord configured for raw S16_LE 16kHz mono going to stdout
    arecord_cmd = [
        "arecord",
        "-D", device,
        "-f", "S16_LE",
        "-c", "1",
        "-r", str(SAMPLE_RATE),
        "-t", "raw",
        "-q",  # quiet, no header chatter
    ]
    log.info(f"arecord starting: {' '.join(arecord_cmd)}")
    proc = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    last_state = "listening"
    if on_state_change:
        on_state_change(last_state)

    buffered_samples = bytearray()
    final_state = "timeout"

    try:
        while True:
            chunk = proc.stdout.read(bytes_per_chunk)
            if len(chunk) < bytes_per_chunk:
                log.warning(f"short read from arecord: {len(chunk)} bytes")
                break
            buffered_samples.extend(chunk)

            samples = np.frombuffer(chunk, dtype=np.int16)
            state = endpointer.process(samples)

            if state != last_state:
                log.debug(f"VAD state: {last_state} -> {state}")
                last_state = state
                if on_state_change:
                    on_state_change(state)

            if state == "endpoint":
                final_state = "endpoint"
                break
            if state == "timeout":
                if endpointer._speech_started:
                    final_state = "timeout"
                else:
                    final_state = "no_speech"
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        # Drain stderr for logging if anything went wrong
        err = proc.stderr.read().decode(errors="replace")
        if err and "Aborted by signal" not in err:
            log.warning(f"arecord stderr: {err[-200:]}")

    # Write the captured audio as a proper WAV file
    with wave.open(output_wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(buffered_samples))

    duration_s = len(buffered_samples) / 2 / SAMPLE_RATE
    log.info(f"captured {duration_s:.2f}s -> {output_wav_path} (state={final_state})")
    return final_state


def play_wav(wav_path: str, device: str = S3_DEVICE) -> bool:
    """Blocking aplay through the S3 speaker."""
    if not os.path.exists(wav_path):
        log.error(f"play_wav: file not found: {wav_path}")
        return False
    result = subprocess.run(
        ["aplay", "-D", device, "-q", wav_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"aplay failed: {result.stderr[-300:]}")
        return False
    return True


def volume_up(card: int = 2, step_pct: int = 5):
    """Bump S3 playback volume up by `step_pct`. Best-effort, swallows errors."""
    subprocess.run(["amixer", "-c", str(card), "sset", "PCM", f"{step_pct}%+"],
                   capture_output=True)


def volume_down(card: int = 2, step_pct: int = 5):
    """Bump S3 playback volume down by `step_pct`. Best-effort, swallows errors."""
    subprocess.run(["amixer", "-c", str(card), "sset", "PCM", f"{step_pct}%-"],
                   capture_output=True)


if __name__ == "__main__":
    # Smoke test: capture-and-play loop.
    # Talk into the S3 mic until silence, then hear it played back.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("audio_io smoke test: speak after the prompt; auto-stops on silence")
    ep = SileroEndpointer(silence_ms=800, max_duration_s=15)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name
    print("--> recording NOW")
    state = capture_until_silence(out_path, ep)
    print(f"--> finished with state={state}, playing back...")
    play_wav(out_path)
    os.unlink(out_path)
    print("done")
