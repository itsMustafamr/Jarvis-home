"""
WiZ smart light controller over local UDP (port 38899).
No cloud, no auth — just JSON-RPC packets to the strip's LAN IP.

The WiZ protocol is picky: each "mode" must be set independently.
- Power state: setPilot {state: true/false}
- Color:       setPilot {r, g, b, dimming}    (auto-exits scenes)
- White:       setPilot {temp, dimming}        (auto-exits scenes)
Do NOT mix state+sceneId+rgb in one packet — it returns Invalid params.
"""

import json
import logging
import re
import socket

log = logging.getLogger("jarvis.lights")

WIZ_IP = "10.0.0.118"   # Strip's LAN IP; rediscover if DHCP shifts.
WIZ_PORT = 38899
TIMEOUT_S = 1.0

# Named colors. Add freely.
COLORS = {
    "red":     (255,   0,   0),
    "orange":  (255, 120,   0),
    "yellow":  (255, 220,   0),
    "green":   (  0, 255,   0),
    "cyan":    (  0, 255, 255),
    "blue":    (  0,   0, 255),
    "purple":  (160,   0, 255),
    "pink":    (255,  80, 160),
    "white":   (255, 255, 255),
}


def _send(payload: dict) -> dict | None:
    """Send one JSON-RPC packet to the strip, return parsed response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT_S)
    try:
        sock.sendto(json.dumps(payload).encode(), (WIZ_IP, WIZ_PORT))
        data, _ = sock.recvfrom(1024)
        resp = json.loads(data.decode())
        log.debug(f"WiZ tx={payload} rx={resp}")
        if "error" in resp:
            log.warning(f"WiZ error: {resp['error']}")
        return resp
    except socket.timeout:
        log.warning(f"WiZ timeout to {WIZ_IP}:{WIZ_PORT}")
        return None
    except Exception as e:
        log.exception(f"WiZ send failed: {e}")
        return None
    finally:
        sock.close()


# ---- Primitives ----

def turn_on() -> bool:
    return _send({"method": "setPilot", "params": {"state": True}}) is not None


def turn_off() -> bool:
    return _send({"method": "setPilot", "params": {"state": False}}) is not None


def set_color(r: int, g: int, b: int, dimming: int = 80) -> bool:
    return _send({"method": "setPilot",
                  "params": {"r": r, "g": g, "b": b, "dimming": dimming}}) is not None


def set_white(temp_k: int = 2700, dimming: int = 60) -> bool:
    return _send({"method": "setPilot",
                  "params": {"temp": temp_k, "dimming": dimming}}) is not None


def set_brightness(dimming: int) -> bool:
    dimming = max(10, min(100, int(dimming)))
    return _send({"method": "setPilot", "params": {"dimming": dimming}}) is not None


# ---- Intent router ----

# Trigger words that mean "this is a lights command, route here"
LIGHT_NOUNS = ("light", "lights", "lamp", "strip", "led", "leds")

# Compiled patterns for actions
# OFF: "lights off", "light off", "light's off", "turn off the lights",
#      "turn the lights off", "shut off the lamp", etc.
RX_OFF = re.compile(
    r"(turn\s+(?:the\s+)?(?:lights?|lamp|strip|leds?)\s*'?s?\s+off"
    r"|(?:lights?|lamp|strip|leds?)\s*'?s?\s+off"
    r"|(?:switch|shut|kill|cut)\s+off\s+(?:the\s+)?(?:lights?|lamp|strip|leds?)"
    r"|turn\s+off\s+(?:the\s+)?(?:lights?|lamp|strip|leds?))",
    re.IGNORECASE)
# ON: same shape, opposite verb.
RX_ON = re.compile(
    r"(turn\s+(?:the\s+)?(?:lights?|lamp|strip|leds?)\s+on"
    r"|(?:lights?|lamp|strip|leds?)\s+on"
    r"|(?:switch|turn)\s+on\s+(?:the\s+)?(?:lights?|lamp|strip|leds?))",
    re.IGNORECASE)
RX_DIM = re.compile(r"\bdim (?:the )?(?:lights?|lamp|strip|leds?)\b", re.IGNORECASE)
RX_BRIGHT = re.compile(r"\b(bright|brighten|max(?:imum)?\s+bright)\b", re.IGNORECASE)
RX_WARM = re.compile(
    r"\b(warm\s*(?:white)?|soft\s*white|cozy|cosy|reading\s+light|standby)\b",
    re.IGNORECASE)


# Strong phrases that imply lights even without the word "lights"
STRONG_LIGHT_PHRASES = (
    "warm white", "soft white", "cool white", "reading light",
    "standby", "movie mode", "night mode",
)


def is_lights_intent(text: str) -> bool:
    """Does this utterance look like a lights command?
    Two paths:
      1. Contains a light-noun (lights/lamp/strip/led) — anything goes
      2. Contains a strong phrase that only makes sense for lights
    """
    t = text.lower()
    if any(n in t for n in LIGHT_NOUNS):
        return True
    if any(p in t for p in STRONG_LIGHT_PHRASES):
        return True
    return False


def handle(text: str) -> str | None:
    """
    Try to handle a lights command. Returns a reply string if handled,
    None if this wasn't a lights command after all (caller falls through to LLM).
    """
    if not is_lights_intent(text):
        return None

    t = text.lower()

    # Order matters! Check more specific phrases before generic ones.
    # 1. Off (before on, so "turn off" doesn't match "on")
    if RX_OFF.search(t):
        return "Lights off, sir." if turn_off() else "I couldn't reach the lights, sir."

    # 2. Warm/soft/cool white presets BEFORE color loop, so "warm white" beats "white"
    if RX_WARM.search(t):
        ok = set_white(2700, 50)
        return "Warm white, sir." if ok else "The lights aren't responding, sir."
    if re.search(r"\bcool white\b", t):
        ok = set_white(5500, 80)
        return "Cool white, sir." if ok else "The lights aren't responding, sir."

    # 3. Named colors. "white" only matches if NOT preceded by warm/soft/cool/off.
    for name, (r, g, b) in COLORS.items():
        if name == "white":
            # Standalone "white" only — guard against "warm/soft/cool white"
            if re.search(r"(?<!warm )(?<!soft )(?<!cool )\bwhite\b", t):
                ok = set_color(r, g, b, dimming=80)
                return "White, sir." if ok else "The lights aren't responding, sir."
        elif re.search(rf"\b{name}\b", t):
            ok = set_color(r, g, b, dimming=80)
            return f"{name.capitalize()}, sir." if ok else "The lights aren't responding, sir."

    # 4. Dim / bright
    if RX_DIM.search(t):
        ok = set_brightness(25)
        return "Dimmed, sir." if ok else "The lights aren't responding, sir."
    if RX_BRIGHT.search(t):
        ok = set_brightness(100)
        return "Full brightness, sir." if ok else "The lights aren't responding, sir."

    # 5. Plain "lights on" (also catches "turn the lights on")
    if RX_ON.search(t):
        return "Lights on, sir." if turn_on() else "I couldn't reach the lights, sir."

    # We thought it was a lights command but didn't recognize the verb.
    # Fall through to the LLM rather than guessing.
    return None


if __name__ == "__main__":
    # Manual smoke test from CLI: `python3 lights.py "lights blue"`
    import sys
    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "turn the lights on"
    print(f"input: {msg!r}")
    print(f"reply: {handle(msg)!r}")
