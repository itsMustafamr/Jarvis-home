"""
Same as before, but with buffer drain after each cycle to ignore queued events.
"""
import asyncio
import fcntl
import glob
import logging
import os
import tempfile
import time
from pathlib import Path

import audio_io
import pipeline
from scheduler import get_scheduler
from vad import SileroEndpointer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("jarvis.local")

# ---- Config ----
S3_VENDOR_ID = "291a"
S3_PRODUCT_ID = "3302"
S3_ALSA_CARD = 2

VAD_SILENCE_MS = 800
VAD_MAX_DURATION_S = 15

HID_CALL_PRESS = b"\x02\x01"
HID_VOL_UP = b"\x01\x01"
HID_VOL_DOWN = b"\x01\x02"

# Set while a call-button cycle is in progress; the announcement player waits
# on this to avoid talking over the user mid-conversation.
cycle_busy = asyncio.Event()
# How long to wait between polite-check ticks when a cycle is in flight.
ANNOUNCEMENT_WAIT_TICK_S = 0.2


def find_s3_hidraw() -> str:
    for hidraw_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent_path = os.path.join(hidraw_path, "device", "uevent")
        if not os.path.exists(uevent_path):
            continue
        try:
            with open(uevent_path) as f:
                content = f.read()
        except OSError:
            continue
        if (f":0000{S3_VENDOR_ID.upper()}:0000{S3_PRODUCT_ID.upper()}" in content
                or f":{S3_VENDOR_ID.upper()}:{S3_PRODUCT_ID.upper()}" in content
                or f"0000{S3_VENDOR_ID}:0000{S3_PRODUCT_ID}".upper() in content.upper()):
            hidraw_name = os.path.basename(hidraw_path)
            return f"/dev/{hidraw_name}"
    raise FileNotFoundError(
        f"S3 hidraw device not found (vendor={S3_VENDOR_ID} product={S3_PRODUCT_ID}). "
        "Is the speaker plugged in and powered on?"
    )


def drain_hidraw(fd: int) -> int:
    """Read and discard any pending HID reports without blocking.

    Returns count of bytes drained, for logging.
    """
    drained = 0
    try:
        # Briefly set non-blocking
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        while True:
            try:
                chunk = os.read(fd, 256)
                if not chunk:
                    break
                drained += len(chunk)
            except BlockingIOError:
                break
    finally:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags)
    return drained


async def announcement_player():
    """Drain the scheduler queue and speak announcements through the S3.

    Waits politely while `cycle_busy` is set so an alert never interrupts a
    conversation. Items remain queued in the scheduler — there is no time-out
    or drop policy, so even hours-long timers do fire eventually.
    """
    sched = get_scheduler()
    while True:
        text = await sched.get_announcement()

        # Politely wait out any in-progress conversation cycle.
        while cycle_busy.is_set():
            await asyncio.sleep(ANNOUNCEMENT_WAIT_TICK_S)

        log.info(f"ANNOUNCE: {text!r}")
        with tempfile.TemporaryDirectory() as tmp:
            out_wav = os.path.join(tmp, "ann.wav")
            ok = await asyncio.to_thread(pipeline.synthesize, text, out_wav)
            if not ok:
                log.error("announcement TTS failed; dropping")
                continue
            await asyncio.to_thread(audio_io.play_wav, out_wav)


async def handle_call_press(endpointer: SileroEndpointer):
    t_press = time.time()
    log.info("=" * 60)
    log.info("CALL BUTTON: starting capture")

    with tempfile.TemporaryDirectory() as tmp:
        in_wav = os.path.join(tmp, "in.wav")
        out_wav = os.path.join(tmp, "out.wav")

        def on_vad_state(state):
            log.debug(f"vad: {state}")
        state = await asyncio.to_thread(
            audio_io.capture_until_silence, in_wav, endpointer,
            audio_io.S3_DEVICE, on_vad_state
        )
        if state == "no_speech":
            log.info("no speech detected; ignoring press")
            return
        if state == "timeout":
            log.info("capture hit timeout (15s); proceeding anyway")

        transcript = await asyncio.to_thread(pipeline.transcribe, in_wav)
        if not transcript:
            log.warning("STT returned empty; aborting")
            return

        reply = await pipeline.route(transcript)

        ok = await asyncio.to_thread(pipeline.synthesize, reply, out_wav)
        if not ok:
            log.error("TTS failed; aborting")
            return

        await asyncio.to_thread(audio_io.play_wav, out_wav)

    log.info(f"cycle complete in {time.time()-t_press:.2f}s")


async def hid_event_loop(hidraw_path: str, endpointer: SileroEndpointer):
    log.info(f"opening {hidraw_path} for HID events")
    fd = os.open(hidraw_path, os.O_RDONLY)
    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await loop.run_in_executor(None, os.read, fd, 8)
            if not data:
                log.warning("hidraw EOF; speaker may have disconnected")
                break

            for i in range(0, len(data) - 1, 2):
                report = data[i:i+2]
                if report == HID_CALL_PRESS:
                    if cycle_busy.is_set():
                        log.info("call pressed but cycle in progress; ignoring")
                        continue
                    cycle_busy.set()
                    try:
                        await handle_call_press(endpointer)
                    finally:
                        # Discard any button presses that arrived during the cycle
                        drained = drain_hidraw(fd)
                        if drained:
                            log.info(f"drained {drained} bytes of queued HID events")
                        cycle_busy.clear()
                elif report == HID_VOL_UP:
                    log.info("vol up")
                    audio_io.volume_up(card=S3_ALSA_CARD)
                elif report == HID_VOL_DOWN:
                    log.info("vol down")
                    audio_io.volume_down(card=S3_ALSA_CARD)
                else:
                    log.debug(f"unhandled HID report: {report.hex()}")
    finally:
        os.close(fd)


async def main():
    log.info("jarvis local-input daemon starting")
    log.info(f"  S3 USB: vendor={S3_VENDOR_ID} product={S3_PRODUCT_ID}")
    log.info(f"  VAD: {VAD_SILENCE_MS}ms silence, {VAD_MAX_DURATION_S}s max")

    try:
        hidraw_path = find_s3_hidraw()
        log.info(f"  hidraw: {hidraw_path}")
    except FileNotFoundError as e:
        log.error(str(e))
        return

    endpointer = SileroEndpointer(
        silence_ms=VAD_SILENCE_MS,
        max_duration_s=VAD_MAX_DURATION_S,
    )

    # Background tasks: scheduler ticks pending timers/reminders into a queue;
    # announcement_player drains the queue and speaks each one through the S3.
    sched = get_scheduler()
    await sched.start()
    asyncio.create_task(announcement_player(), name="announcement_player")

    log.info("ready. Press the call button on the S3 to talk.")
    await hid_event_loop(hidraw_path, endpointer)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("interrupted; exiting")
