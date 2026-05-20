"""Vision intent classifier for Jarvis.

Conservative imperative/question patterns. Returns True only when the user is
clearly asking the assistant to look at something. Avoids false-positives like
"I see what you mean" or "looks good to me".
"""
import re

# Match a few clear patterns. All anchored to recognized imperative or question forms.
# Order matters only for readability; any match returns True.
_PATTERNS = [
    # "what do/can you see", "what are you seeing"
    r"\bwhat\s+(do|can|are)\s+you\s+see(ing)?\b",
    # "what's (in front of you|around you|around me|in the room|in this image|in this picture)"
    r"\bwhat'?s\s+(in front of|around|in)\b",
    # "describe (what you see|the scene|this|the room|what's in front)"
    r"\bdescribe\s+(what|the|this|it)\b",
    # "look at (this|that|the camera)" or imperative "look around"
    r"\blook\s+(at|around)\b",
    # "what am I looking at", "what is this"
    r"\bwhat\s+am\s+i\s+looking\s+at\b",
    r"\bwhat\s+is\s+(this|that)\b",
    # "tell me what you see"
    r"\btell\s+me\s+what\s+you\s+see\b",
    # "can you see (this|me|that|anything)"
    r"\bcan\s+you\s+see\b",
    # "use your eyes", "use the camera"
    r"\buse\s+(your\s+eyes|the\s+camera)\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def is_vision_intent(text: str) -> bool:
    """Return True if the utterance is asking Jarvis to look at something."""
    if not text:
        return False
    return any(p.search(text) for p in _COMPILED)


if __name__ == "__main__":
    # Quick smoke test
    positives = [
        "what do you see",
        "what can you see in front of you",
        "what's around me",
        "describe what you see",
        "describe the scene",
        "look at this",
        "look around",
        "what am I looking at",
        "what is this",
        "tell me what you see",
        "can you see anything",
        "use your eyes",
    ]
    negatives = [
        "I see what you mean",
        "looks good",
        "I can see the appeal",
        "turn on the lights",
        "what's the weather",
        "tell me a joke",
        "look up the news",  # we don't want this firing
        "describe yourself",  # nope
    ]
    print("POSITIVES (should all be True):")
    for t in positives:
        print(f"  {is_vision_intent(t)!s:5}  {t}")
    print("NEGATIVES (should all be False):")
    for t in negatives:
        print(f"  {is_vision_intent(t)!s:5}  {t}")
