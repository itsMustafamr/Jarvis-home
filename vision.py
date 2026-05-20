"""YOLO11n vision wrapper for Jarvis.

Loads model once at import (~3s cold). Subsequent calls ~45ms on Orin Nano Super.
"""
from collections import Counter
from pathlib import Path
from typing import Union
import io

from PIL import Image
from ultralytics import YOLO

_MODEL_PATH = Path.home() / "jarvis-vision-test" / "yolo11n.pt"
_CONF_THRESHOLD = 0.4
_DEVICE = 0

print(f"[vision] Loading YOLO11n from {_MODEL_PATH}...")
_model = YOLO(str(_MODEL_PATH))
_warmup = Image.new("RGB", (640, 480))
_model(_warmup, device=_DEVICE, verbose=False)
print("[vision] Model ready.")


def _pluralize(name: str, count: int) -> str:
    if count == 1:
        return f"a {name}" if name[0].lower() not in "aeiou" else f"an {name}"
    irregular = {
        "person": "people", "mouse": "mice", "knife": "knives",
        "sandwich": "sandwiches", "bench": "benches", "bus": "buses",
        "scissors": "scissors", "skis": "skis",
    }
    plural = irregular.get(name, name + "s")
    return f"{count} {plural}"


def describe(image: Union[bytes, str, Path]) -> str:
    if isinstance(image, bytes):
        img = Image.open(io.BytesIO(image))
    else:
        img = str(image)

    results = _model(img, device=_DEVICE, verbose=False, conf=_CONF_THRESHOLD)
    boxes = results[0].boxes
    names = results[0].names

    if boxes is None or len(boxes) == 0:
        return "I don't see anything I recognize."

    class_ids = boxes.cls.int().tolist()
    counts = Counter(names[cid] for cid in class_ids)
    items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    phrases = [_pluralize(name, count) for name, count in items]

    if len(phrases) == 1:
        return f"I see {phrases[0]}."
    if len(phrases) == 2:
        return f"I see {phrases[0]} and {phrases[1]}."
    return f"I see {', '.join(phrases[:-1])}, and {phrases[-1]}."


if __name__ == "__main__":
    import sys
    test_image = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "jarvis-vision-test" / "bus.jpg")
    print(f"Testing on: {test_image}")
    print(describe(test_image))
