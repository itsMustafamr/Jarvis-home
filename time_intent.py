"""
Date / time / timer / reminder intent matchers, plus the small parsers that
turn natural-language durations and clock times into seconds and datetimes.

handle() returns:
  - a reply string if the utterance was a date/time/timer/reminder intent
  - None otherwise (caller falls through to LLM)
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Optional

from scheduler import get_scheduler

log = logging.getLogger("jarvis.time_intent")


# ----------------------------------------------------------------------
# Patterns
# ----------------------------------------------------------------------

RX_WHAT_TIME = re.compile(
    r"\bwhat(?:'s|\s+is)?\s+(?:the\s+)?time\b",
    re.IGNORECASE,
)
RX_WHAT_DATE = re.compile(
    r"\b(?:what(?:'s|\s+is)?\s+(?:the\s+|today's\s+)?date"
    r"|what\s+day\s+(?:is\s+it|is\s+today))\b",
    re.IGNORECASE,
)

# "set a timer for 5 minutes" / "timer 30 seconds" / "start a timer for two hours"
RX_TIMER_NUM_AFTER = re.compile(
    r"\b(?:(?:set|start|make|create|give\s+me|please)\s+(?:a\s+|me\s+a\s+)?)?"
    r"timer\s+(?:for\s+)?"
    r"(?P<value>\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|fifteen|twenty|thirty|forty[-\s]?five|sixty)"
    r"[-\s]?(?P<unit>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
    re.IGNORECASE,
)

# "start a 10 minute timer" / "5-minute timer" / "ten second timer"
RX_TIMER_NUM_BEFORE = re.compile(
    r"\b(?:(?:set|start|make|create|give\s+me|please)\s+(?:a\s+|me\s+a\s+)?)?"
    r"(?P<value>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|fifteen|twenty|thirty|forty[-\s]?five|sixty)"
    r"[-\s]?(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)\s+timer\b",
    re.IGNORECASE,
)

# "remind me to take pills in 15 minutes"
RX_REMIND_IN = re.compile(
    r"\bremind\s+me\s+(?:to\s+)?(?P<what>.+?)\s+in\s+"
    r"(?P<value>\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|fifteen|twenty|thirty|forty[-\s]?five|sixty)"
    r"[-\s]?(?P<unit>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
    re.IGNORECASE,
)

# "remind me to call mum at 8 pm", "remind me to leave at 17:30"
RX_REMIND_AT = re.compile(
    r"\bremind\s+me\s+(?:to\s+)?(?P<what>.+?)\s+at\s+"
    r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
    re.IGNORECASE,
)


WORDS_TO_NUM = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60,
    "forty-five": 45, "fortyfive": 45, "forty five": 45,
}

UNIT_TO_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
}


# ----------------------------------------------------------------------
# Parsers
# ----------------------------------------------------------------------

def _parse_value(value: str) -> float:
    v = value.strip().lower()
    if v in WORDS_TO_NUM:
        return float(WORDS_TO_NUM[v])
    try:
        return float(v)
    except ValueError:
        return 0.0


def _seconds_from(value_str: str, unit_str: str) -> float:
    v = _parse_value(value_str)
    u = unit_str.strip().lower()
    return v * UNIT_TO_SECONDS.get(u, 0)


def _human_duration(seconds: float) -> str:
    """Noun form: '5 minutes', '1 hour', '2 minutes and 30 seconds'.
    Used in confirmation replies ('Timer set for 5 minutes, sir.')."""
    seconds = int(round(seconds))
    if seconds >= 3600 and seconds % 3600 == 0:
        h = seconds // 3600
        return f"{h} hour" if h == 1 else f"{h} hours"
    if seconds >= 60 and seconds % 60 == 0:
        m = seconds // 60
        return f"{m} minute" if m == 1 else f"{m} minutes"
    if seconds >= 60:
        m, s = divmod(seconds, 60)
        return f"{m} minute{'s' if m != 1 else ''} and {s} second{'s' if s != 1 else ''}"
    return f"{seconds} second" if seconds == 1 else f"{seconds} seconds"


def _human_duration_adj(seconds: float) -> str:
    """Adjective form: '5-minute', '1-hour', '90-second'.
    Used inside noun phrases ('your 5-minute timer is up')."""
    seconds = int(round(seconds))
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}-hour"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60}-minute"
    return f"{seconds}-second"


def _parse_clock_time(s: str) -> Optional[dt.time]:
    """Parse '8pm', '8:30am', '14:30', '8' into a datetime.time. None on failure."""
    s = s.strip().lower().replace(" ", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)?$", s)
    if not m:
        return None
    h = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    period = m.group(3)
    if period == "pm" and h < 12:
        h += 12
    elif period == "am" and h == 12:
        h = 0
    if h > 23 or minute > 59:
        return None
    return dt.time(h, minute)


def _fmt_clock(t: dt.datetime) -> str:
    """Spoken-friendly time string. Avoids platform-specific strftime directives."""
    hour = t.hour
    minute = t.minute
    period = "am"
    if hour == 0:
        h12 = 12
    elif hour < 12:
        h12 = hour
    elif hour == 12:
        h12 = 12
        period = "pm"
    else:
        h12 = hour - 12
        period = "pm"
    if minute == 0:
        return f"{h12} {period}"
    return f"{h12}:{minute:02d} {period}"


# ----------------------------------------------------------------------
# Intent handler
# ----------------------------------------------------------------------

def is_time_intent(text: str) -> bool:
    return bool(
        RX_WHAT_TIME.search(text)
        or RX_WHAT_DATE.search(text)
        or RX_TIMER_NUM_AFTER.search(text)
        or RX_TIMER_NUM_BEFORE.search(text)
        or RX_REMIND_IN.search(text)
        or RX_REMIND_AT.search(text)
    )


def handle(text: str) -> Optional[str]:
    # 1. Plain "what time is it" / "what's the date"
    if RX_WHAT_TIME.search(text):
        now = dt.datetime.now()
        return f"It's {_fmt_clock(now)}, sir."

    if RX_WHAT_DATE.search(text):
        now = dt.datetime.now()
        # "Friday the 22nd of May"
        day = now.day
        suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"It's {now.strftime('%A')} the {day}{suffix} of {now.strftime('%B')}, sir."

    # 2. Reminders ("remind me to X in/at Y") — checked BEFORE timers so the
    #    word "minute" inside the reminder body doesn't trip the timer regex.
    m = RX_REMIND_IN.search(text)
    if m:
        seconds = _seconds_from(m.group("value"), m.group("unit"))
        what = m.group("what").strip().rstrip(".!?,;:")
        if seconds <= 0:
            return "I'll need a valid duration, sir."
        if seconds > 86400:
            return "I can manage a reminder up to twenty-four hours out, sir."
        sched = get_scheduler()
        sched.schedule_in(seconds, f"Sir, you asked to be reminded to {what}.")
        return f"I'll remind you in {_human_duration(seconds)}, sir."

    m = RX_REMIND_AT.search(text)
    if m:
        target_t = _parse_clock_time(m.group("time"))
        if target_t is None:
            return "I didn't catch the time, sir."
        what = m.group("what").strip().rstrip(".!?,;:")
        now = dt.datetime.now()
        target = now.replace(
            hour=target_t.hour, minute=target_t.minute, second=0, microsecond=0
        )
        if target <= now:
            target = target + dt.timedelta(days=1)
        sched = get_scheduler()
        sched.schedule_at(target.timestamp(), f"Sir, you asked to be reminded to {what}.")
        return f"I'll remind you at {_fmt_clock(target)}, sir."

    # 3. Timers — try both word orderings.
    m = RX_TIMER_NUM_AFTER.search(text) or RX_TIMER_NUM_BEFORE.search(text)
    if m:
        seconds = _seconds_from(m.group("value"), m.group("unit"))
        if seconds <= 0:
            return "I'll need a valid duration, sir."
        if seconds > 86400:
            return "I can manage a timer up to twenty-four hours, sir."
        sched = get_scheduler()
        sched.schedule_in(seconds, f"Sir, your {_human_duration_adj(seconds)} timer is up.")
        return f"Timer set for {_human_duration(seconds)}, sir."

    return None


if __name__ == "__main__":
    # python3 time_intent.py "set a timer for 10 seconds"
    import sys

    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "what time is it"
    print(f"input: {msg!r}")
    print(f"reply: {handle(msg)!r}")
