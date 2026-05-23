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

# "remember that I'm allergic to peanuts", "make a note that the wifi password is X",
# "note that I take pills at 8am", "note down that ..."
RX_REMEMBER = re.compile(
    r"\b(?:remember\s+(?:that\s+)?"
    r"|make\s+a\s+note\s+(?:that\s+|of\s+)?"
    r"|note\s+(?:that\s+|down\s+(?:that\s+)?)?)"
    r"(?P<content>.+)",
    re.IGNORECASE,
)

# "what do you know about me", "what do you remember", "tell me what you know"
RX_RECALL = re.compile(
    r"\b(?:what\s+do\s+you\s+(?:know|remember)(?:\s+about\s+me)?"
    r"|tell\s+me\s+what\s+you\s+(?:know|remember)"
    r"|what\s+have\s+i\s+told\s+you)\b",
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


def _normalize_for_storage(text: str) -> str:
    """Rewrite first-person facts to third-person so the stored entry reads naturally
    when surfaced back into the prompt.

      'I am allergic to peanuts'   -> 'the user is allergic to peanuts'
      'My birthday is in March'    -> "the user's birthday is in March"

    Best-effort; leaves unrecognised phrasing untouched.
    """
    t = text.strip()
    low = t.lower()
    if low.startswith("i am "):
        return "the user is " + t[5:]
    if low.startswith("i'm "):
        return "the user is " + t[4:]
    if low.startswith("i have "):
        return "the user has " + t[7:]
    if low.startswith("i've "):
        return "the user has " + t[5:]
    if low.startswith("i like "):
        return "the user likes " + t[7:]
    if low.startswith("i love "):
        return "the user loves " + t[7:]
    if low.startswith("i don't like "):
        return "the user doesn't like " + t[13:]
    if low.startswith("i hate "):
        return "the user hates " + t[7:]
    if low.startswith("my "):
        return "the user's " + t[3:]
    return t


def _strip_intent_punct(text: str) -> str:
    """Replace mid-utterance punctuation with spaces so regexes that key on
    whitespace separators ('remember\\s+...') aren't broken by Whisper's
    habit of inserting commas after introductory imperatives
    (e.g. 'Remember, Mohammed.' -> 'Remember Mohammed')."""
    text = re.sub(r"[,.;:?!]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_memory_intent(text: str) -> bool:
    text = _strip_intent_punct(text)
    return bool(
        RX_REMEMBER.search(text) or RX_RECALL.search(text) or RX_FORGET.search(text)
    )


def handle(text: str) -> Optional[str]:
    """Try to handle a memory intent. Returns reply string if handled, else None."""
    text = _strip_intent_punct(text)
    m = RX_FORGET.search(text)
    if m:
        query = m.group("query").strip().rstrip(".!?,;:")
        n = forget_fact(query)
        if n == 0:
            return "I don't have anything matching, sir."
        return "Forgotten, sir." if n == 1 else f"Forgotten {n} entries, sir."

    m = RX_RECALL.search(text)
    if m:
        facts = get_facts()
        if not facts:
            return "Nothing on file yet, sir."
        if len(facts) == 1:
            return f"You told me {facts[0]}, sir."
        # Keep it as one sentence per the JARVIS persona.
        return "You've told me: " + "; ".join(facts) + ", sir."

    m = RX_REMEMBER.search(text)
    if m:
        content = m.group("content").strip().rstrip(".!?,;:")
        if not content:
            return "Remember what, sir?"
        normalized = _normalize_for_storage(content)
        added = add_fact(normalized)
        return "Noted, sir." if added else "I had that already, sir."

    return None


if __name__ == "__main__":
    # Manual smoke test: `python3 memory.py "remember that I like Earl Grey"`
    import sys

    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "what do you know about me"
    print(f"input: {msg!r}")
    print(f"reply: {handle(msg)!r}")
    print(f"facts: {get_facts()}")
