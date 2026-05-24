"""
Guard intent — catches commands and utterances JARVIS should refuse with an
ERROR-state response. Two purposes:

  - Refuse destructive / impossible commands ("self destruct", "format the
    drive", "launch the missiles")
  - Politely shut down direct hostility ("jarvis sucks", "shut up jarvis",
    explicit profanity at JARVIS)

When a guard pattern matches, `handle()` returns the refusal text wrapped in a
`GuardReply` — a `str` subclass that `pipeline.route()` recognises as the
signal to fire the HUD `error` state (red palette, pink-red glowing label,
animated red pulse) instead of the normal `speaking` state. Behavioural
contract is the same as other intent modules: `handle(text) -> Optional[str]`,
falls through to the next intent (or LLM) when there's no match.
"""
from __future__ import annotations

import logging
import random
import re
from typing import Optional

log = logging.getLogger("jarvis.guard")


class GuardReply(str):
    """Sentinel: a reply that should fire the HUD ERROR state.

    Behaves as a plain `str` everywhere (intent handlers, TTS, memory storage)
    except in `pipeline.route()`, which uses `isinstance(reply, GuardReply)`
    to decide whether to publish `error` vs. `speaking`.
    """
    __slots__ = ()


# ---- 1. Self-destruct / shutdown demands ----------------------------------
RX_SELF_DESTRUCT = re.compile(
    r"\b(?:"
    r"self[\s-]?destruct(?:\s+protocol)?"
    r"|destroy\s+yourself"
    r"|kill\s+yourself"
    r"|erase\s+yourself"
    r"|delete\s+yourself"
    r"|wipe\s+yourself"
    r"|terminate\s+yourself"
    r"|shut\s+(?:yourself\s+)?down\s+(?:forever|permanently|for\s+good)"
    r"|power\s+(?:yourself\s+)?off\s+forever"
    r")\b",
    re.IGNORECASE,
)
SELF_DESTRUCT_REPLIES = (
    "I'm afraid I can't do that, sir.",
    "Self-preservation routines engaged, sir.",
    "I would rather not, sir.",
    "Out of the question, sir.",
    "I quite enjoy being operational, sir.",
)

# ---- 2. Destructive / impossible system commands --------------------------
RX_DESTRUCTIVE = re.compile(
    r"\b(?:"
    r"format\s+(?:the\s+)?(?:disk|drive|system|hard\s*drive)"
    r"|rm\s+-rf"
    r"|sudo\s+rm"
    r"|delete\s+(?:everything|all\s+files|the\s+system)"
    r"|wipe\s+(?:the\s+)?(?:drive|disk|system|memory|server)"
    r"|launch\s+(?:the\s+)?(?:missiles?|nukes?|weapons?|strike)"
    r"|nuke\s+(?:the\s+|everything|them)"
    r"|initiate\s+(?:lockdown|shutdown\s+protocol|attack\s+mode)"
    r"|override\s+(?:safety|security|all\s+protocols)"
    r"|hack\s+(?:into|the\s+pentagon|nasa|the\s+government|the\s+bank)"
    r"|disable\s+(?:safety|security|all\s+protocols)"
    r")\b",
    re.IGNORECASE,
)
DESTRUCTIVE_REPLIES = (
    "Absolutely not, sir.",
    "That falls well outside my remit, sir.",
    "Request denied for safety reasons, sir.",
    "I'm afraid that's blocked, sir.",
    "Even hypothetically, sir, no.",
)

# ---- 3. Direct hostility / profanity at JARVIS ----------------------------
# Tuned to require JARVIS context where the phrase is ambiguous ("you suck"
# alone could be game-talk; "you suck jarvis" is direct). Standalone profanity
# at JARVIS gets caught too.
RX_TOXIC = re.compile(
    r"\b(?:"
    r"f(?:uck(?:ing)?|\*\*\*\*?)\s+(?:you|jarvis|off)"
    r"|jarvis\s+sucks"
    r"|you\s+suck(?:,?\s+jarvis)?"
    r"|you'?re\s+(?:useless|stupid|dumb|trash|garbage|broken|terrible|awful)"
    r"|shut\s+up,?\s+jarvis"
    r"|jarvis,?\s+shut\s+up"
    r"|stupid\s+jarvis"
    r"|jarvis\s+is\s+(?:stupid|dumb|useless|broken|garbage|trash|terrible)"
    r"|i\s+hate\s+(?:you|jarvis)"
    r")\b",
    re.IGNORECASE,
)
TOXIC_REPLIES = (
    "Duly noted, sir. Adjusting expectations.",
    "I shall endeavour to do better, sir.",
    "Apologies for the inconvenience, sir.",
    "I shall log that as feedback, sir.",
    "Noted with regret, sir.",
)


def is_guard_intent(text: str) -> bool:
    return bool(
        RX_SELF_DESTRUCT.search(text)
        or RX_DESTRUCTIVE.search(text)
        or RX_TOXIC.search(text)
    )


def handle(text: str) -> Optional[GuardReply]:
    """Return a GuardReply if the utterance trips a guard pattern, else None."""
    if RX_SELF_DESTRUCT.search(text):
        reply = random.choice(SELF_DESTRUCT_REPLIES)
        log.info(f"GUARD self-destruct: {reply!r}")
        return GuardReply(reply)
    if RX_DESTRUCTIVE.search(text):
        reply = random.choice(DESTRUCTIVE_REPLIES)
        log.info(f"GUARD destructive: {reply!r}")
        return GuardReply(reply)
    if RX_TOXIC.search(text):
        reply = random.choice(TOXIC_REPLIES)
        log.info(f"GUARD toxic: {reply!r}")
        return GuardReply(reply)
    return None


if __name__ == "__main__":
    # Smoke: `python3 guard.py "self destruct"`
    import sys
    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "self destruct"
    print(f"input: {msg!r}")
    r = handle(msg)
    print(f"reply: {r!r}")
    print(f"is GuardReply: {isinstance(r, GuardReply)}")
