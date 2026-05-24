"""
Persistent memory for Jarvis.

Two stores:
  - History: a rolling deque of the last N (user, jarvis) turns, persisted
    to disk as JSON so it survives restarts. Fed into the LLM prompt so
    Jarvis can follow up on what was just said.
  - Facts:   a SQLite table of things the user explicitly asked Jarvis to
    remember ("remember that I'm allergic to peanuts"). Surfaced into the
    LLM prompt as a short "Known about the user:" block.

Intent matchers:
  - "remember that X" / "make a note that X"  -> store fact
  - "what do you know/remember about me"      -> list facts
  - "forget X" / "forget about X"             -> delete matching fact(s)
"""

import json
import logging
import re
import sqlite3
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Optional

log = logging.getLogger("jarvis.memory")

# ---- Config ----
DATA_DIR = Path.home() / "jarvis" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_PATH = DATA_DIR / "history.json"
DB_PATH = DATA_DIR / "jarvis.db"

# Last N (user, jarvis) exchanges that get prepended into the prompt.
# Six turns = three back-and-forth pairs. Plenty of context, very cheap in tokens.
HISTORY_MAX_PAIRS = 6

_history_lock = Lock()
_history: deque = deque(maxlen=HISTORY_MAX_PAIRS)


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS facts (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               content TEXT NOT NULL UNIQUE,
               created_at REAL NOT NULL
           )"""
    )
    conn.commit()
    conn.close()


def _load_history():
    global _history
    if not HISTORY_PATH.exists():
        return
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        _history = deque(
            ((u, j) for u, j in data[-HISTORY_MAX_PAIRS:]),
            maxlen=HISTORY_MAX_PAIRS,
        )
        log.info(f"loaded {len(_history)} history turns from disk")
    except Exception:
        log.exception("could not load history; starting empty")


def _save_history():
    try:
        with open(HISTORY_PATH, "w") as f:
            json.dump(list(_history), f)
    except Exception:
        log.exception("could not save history")


_init_db()
_load_history()


# ---- History API ----

def add_turn(user_text: str, jarvis_text: str) -> None:
    """Record one (user said, jarvis replied) exchange."""
    with _history_lock:
        _history.append([user_text, jarvis_text])
        _save_history()


def get_history() -> list[tuple[str, str]]:
    with _history_lock:
        return list(_history)


def clear_history() -> None:
    with _history_lock:
        _history.clear()
        _save_history()


# ---- Facts API ----

def get_facts() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT content FROM facts ORDER BY created_at").fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def add_fact(content: str) -> bool:
    content = content.strip()
    if not content:
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO facts (content, created_at) VALUES (?, ?)",
            (content, time.time()),
        )
        conn.commit()
        return conn.total_changes > before
    finally:
        conn.close()


def forget_fact(query: str) -> int:
    """Delete any fact whose content contains `query` (case-insensitive substring).
    Returns number of rows deleted."""
    q = f"%{query.strip().lower()}%"
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("DELETE FROM facts WHERE LOWER(content) LIKE ?", (q,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---- Prompt context ----

def get_prompt_context() -> tuple[str, list[tuple[str, str]]]:
    """Return (facts_block, history_pairs) ready to splice into the LLM prompt.

    facts_block is an empty string when there are no facts. Otherwise it is
    a single short paragraph terminated by a blank line.
    """
    facts = get_facts()
    if facts:
        facts_block = "Known about the user: " + "; ".join(facts) + ".\n\n"
    else:
        facts_block = ""
    return facts_block, get_history()


# ---- Intent ----

# Prefix form: "Remember that X" / "Make a note that X" / "Note down that X"
RX_REMEMBER = re.compile(
    r"\b(?:remember\s+(?:that\s+)?"
    r"|make\s+a\s+note\s+(?:that\s+|of\s+)?"
    r"|note\s+(?:that\s+|down\s+(?:that\s+)?)?)"
    r"(?P<content>.+)",
    re.IGNORECASE,
)

# Postfix form: "[fact]. Remember that." / "I like coffee, remember that."
# / "[fact]. Note that." / "[fact]. Make a note of that."
# Captures the content BEFORE the trailing tag. Checked before RX_REMEMBER
# so it wins when both could match.
#
# The leading negative lookahead skips interrogative phrasings — without it,
# "Can you remember that?" would capture "Can you" as a fact.
RX_REMEMBER_POSTFIX = re.compile(
    r"^(?!(?:can|could|would|will|should|do|did|are|were|have|has|may|might)\s+you\b)"
    r"(?P<content>.+?)"
    r"\s+(?:remember|note|make\s+a\s+note\s+of)\s+(?:that|this)\s*$",
    re.IGNORECASE,
)

# Single-word / pronoun captures that are useless as a stored fact.
# When the regex captures one of these, we ask the user to repeat instead
# of polluting the database with "that".
_USELESS_CONTENT = {
    "that", "this", "it", "those", "these", "them", "stuff", "things",
    "the thing", "the things",
}

# Recall phrasings:
#   "what do you know / remember about me"
#   "do you know / remember anything about me"
#   "do you know about me"
#   "what have I told you"
#   "tell me what you know / remember"
#   "what's on file" / "what's in your memory" / "anything on file"
RX_RECALL = re.compile(
    r"\b(?:what\s+do\s+you\s+(?:know|remember)(?:\s+about\s+me)?"
    r"|do\s+you\s+(?:know|remember)(?:\s+anything)?(?:\s+about\s+me)?"
    r"|tell\s+me\s+what\s+you\s+(?:know|remember)"
    r"|what\s+have\s+i\s+told\s+you"
    r"|(?:what(?:'s|\s+is))?\s*(?:on\s+file|in\s+(?:your\s+)?memory|stored)"
    r"|anything\s+(?:on\s+file|stored|in\s+memory))\b",
    re.IGNORECASE,
)

# "forget that X" / "forget about X" / "forget the X" / "forget X"
# The optional middle group eats any leading article so the captured query is
# the actual content word ("birthday", "peanuts", ...) and substring-matches
# stored facts like "the user's birthday is in March".
RX_FORGET = re.compile(
    r"\bforget(?:\s+about)?\s+"
    r"(?:that\s+|the\s+thing\s+about\s+|the\s+|a\s+|about\s+)?"
    r"(?P<query>.+)",
    re.IGNORECASE,
)


# (prefix, replacement) for first-person -> third-person rewrite. Checked in
# order, first match wins. Longer / more specific prefixes appear first so
# "I don't like X" wins over "I X" if a future verb starts with "don't".
_FIRST_PERSON_REWRITES = [
    ("i don't like ",  "the user doesn't like "),
    ("i do not like ", "the user does not like "),
    ("i'm ",           "the user is "),
    ("i've ",          "the user has "),
    ("i am ",          "the user is "),
    ("i have ",        "the user has "),
    ("i like ",        "the user likes "),
    ("i love ",        "the user loves "),
    ("i hate ",        "the user hates "),
    ("i prefer ",      "the user prefers "),
    ("i want ",        "the user wants "),
    ("i need ",        "the user needs "),
    ("i take ",        "the user takes "),
    ("i drink ",       "the user drinks "),
    ("i eat ",         "the user eats "),
    ("i work ",        "the user works "),
    ("i live ",        "the user lives "),
    ("i go ",          "the user goes "),
    ("my ",            "the user's "),
]


def _normalize_for_storage(text: str) -> str:
    """Rewrite first-person facts to third-person so the stored entry reads
    naturally when surfaced back into the prompt.

      'I am allergic to peanuts'   -> 'the user is allergic to peanuts'
      'I prefer Earl Grey'         -> 'the user prefers Earl Grey'
      'My birthday is in March'    -> "the user's birthday is in March"

    Best-effort; leaves unrecognised phrasing untouched.
    """
    t = text.strip()
    low = t.lower()
    for prefix, replacement in _FIRST_PERSON_REWRITES:
        if low.startswith(prefix):
            return replacement + t[len(prefix):]
    return t


def _strip_intent_punct(text: str) -> str:
    """Replace mid-utterance punctuation with spaces so regexes that key on
    whitespace separators ('remember\\s+...') aren't broken by Whisper's
    habit of inserting commas after introductory imperatives
    (e.g. 'Remember, Mohammed.' -> 'Remember Mohammed')."""
    text = re.sub(r"[,.;:?!]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Catches "Can you / Could you / Did you / Would you / etc." at the start of
# the utterance. We need this so that "Could you remember that for me?" does
# NOT get parsed as remember("for me") — the auxiliary phrasing means the user
# is asking Jarvis to act on something earlier in the conversation, not stating
# a new fact.
INTERROGATIVE_AUX_RX = re.compile(
    r"^(?:can|could|would|will|should|do|did|are|were|have|has|may|might)\s+you\s+",
    re.IGNORECASE,
)


def is_memory_intent(text: str) -> bool:
    text = _strip_intent_punct(text)
    return bool(
        RX_REMEMBER_POSTFIX.search(text)
        or RX_REMEMBER.search(text)
        or RX_RECALL.search(text)
        or RX_FORGET.search(text)
    )


def _store_content(raw_content: str) -> str:
    """Shared path for both remember-prefix and remember-postfix matches.
    Returns the reply string."""
    content = raw_content.strip().rstrip(".!?,;:")
    if not content or content.lower() in _USELESS_CONTENT:
        # Don't store "that" / "this" / "it" — they don't carry meaning on their own.
        return "Remember what, sir?"
    normalized = _normalize_for_storage(content)
    added = add_fact(normalized)
    return "Noted, sir." if added else "I had that already, sir."


def handle(text: str) -> Optional[str]:
    """Try to handle a memory intent. Returns reply string if handled, else None."""
    text = _strip_intent_punct(text)

    # Recall is checked first — its patterns ("do you know about me",
    # "tell me what you remember") are interrogative, so they have to win
    # before the auxiliary-question filter below short-circuits them.
    m = RX_RECALL.search(text)
    if m:
        facts = get_facts()
        if not facts:
            return "Nothing on file yet, sir."
        if len(facts) == 1:
            return f"You told me {facts[0]}, sir."
        # Keep it as one sentence per the JARVIS persona.
        return "You've told me: " + "; ".join(facts) + ", sir."

    # If the utterance starts with an auxiliary-question ("Could you...",
    # "Did you...", "Can you...") AND it contains a remember/note keyword,
    # the user is asking Jarvis to act on something earlier, not stating a
    # new fact. Without this guard, "Could you remember that for me?" gets
    # parsed as remember("for me").
    if INTERROGATIVE_AUX_RX.match(text) and re.search(
        r"\b(?:remember|note)\b", text, re.IGNORECASE
    ):
        return "Remember what, sir?"

    m = RX_FORGET.search(text)
    if m:
        query = m.group("query").strip().rstrip(".!?,;:")
        n = forget_fact(query)
        if n == 0:
            return "I don't have anything matching, sir."
        return "Forgotten, sir." if n == 1 else f"Forgotten {n} entries, sir."

    # Postfix form FIRST so "I like coffee, remember that" captures
    # "I like coffee" instead of falling into RX_REMEMBER (which would
    # capture just "that" and then be rejected by _USELESS_CONTENT).
    m = RX_REMEMBER_POSTFIX.search(text)
    if m:
        return _store_content(m.group("content"))

    m = RX_REMEMBER.search(text)
    if m:
        return _store_content(m.group("content"))

    return None


if __name__ == "__main__":
    # Manual smoke test: `python3 memory.py "remember that I like Earl Grey"`
    import sys

    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "what do you know about me"
    print(f"input: {msg!r}")
    print(f"reply: {handle(msg)!r}")
    print(f"facts: {get_facts()}")
