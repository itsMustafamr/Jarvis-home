"""
Silero VAD streaming wrapper.
Feeds 16kHz mono S16 audio in 30ms chunks, tracks speech/silence state,
returns endpoint signal when configured silence threshold is reached.
"""
import logging
from typing import Optional

import numpy as np
import torch

log = logging.getLogger("jarvis.vad")

# Silero v5 expects 16kHz audio in 512-sample chunks (32ms).
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512  # 32ms at 16kHz - Silero's native chunk size for v5
SPEECH_THRESHOLD = 0.5  # probability above which we consider it speech


class SileroEndpointer:
    """Stateful endpoint-of-speech detector.

    Usage:
        ep = SileroEndpointer(silence_ms=800, max_duration_s=15)
        ep.start()
        while True:
            chunk = read_16k_mono_s16(...)  # numpy int16 array of CHUNK_SAMPLES
            state = ep.process(chunk)
            if state == "endpoint":
                break
            if state == "timeout":
                break
    """
    def __init__(self, silence_ms: int = 800, max_duration_s: int = 15,
                 speech_threshold: float = SPEECH_THRESHOLD):
        from silero_vad import load_silero_vad
        log.info("Loading Silero VAD model...")
        self._model = load_silero_vad()
        self.silence_ms = silence_ms
        self.max_duration_s = max_duration_s
        self.speech_threshold = speech_threshold
        self._reset_state()
        log.info("Silero VAD ready.")

    def _reset_state(self):
        self._chunks_seen = 0
        self._last_speech_chunk = -1
        self._speech_started = False
        self._model.reset_states()

    def start(self):
        """Reset for a new capture session."""
        self._reset_state()

    def process(self, samples_int16: np.ndarray) -> str:
        """Feed one CHUNK_SAMPLES-length int16 numpy array.

        Returns:
            "listening"  - waiting for speech to start
            "speech"     - speech detected, still going
            "endpoint"   - silence threshold met after speech
            "timeout"    - max duration reached
        """
        audio_float = samples_int16.astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio_float)

        prob = self._model(tensor, SAMPLE_RATE).item()
        is_speech = prob >= self.speech_threshold

        self._chunks_seen += 1
        elapsed_s = (self._chunks_seen * CHUNK_SAMPLES) / SAMPLE_RATE

        if is_speech:
            self._last_speech_chunk = self._chunks_seen
            self._speech_started = True

        if elapsed_s >= self.max_duration_s:
            return "timeout"

        if not self._speech_started:
            return "listening"

        silence_chunks = self._chunks_seen - self._last_speech_chunk
        silence_ms = (silence_chunks * CHUNK_SAMPLES * 1000) / SAMPLE_RATE
        if silence_ms >= self.silence_ms:
            return "endpoint"
        return "speech"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ep = SileroEndpointer()
    print("VAD smoke test: model loaded successfully")
    silence = np.zeros(CHUNK_SAMPLES, dtype=np.int16)
    for _ in range(10):
        state = ep.process(silence)
    print(f"After 10 silence chunks: state = {state}")
