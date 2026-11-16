"""Sestavení obrazovek bez závislosti na vykreslování ve firmwaru."""
from __future__ import annotations
import math
import unicodedata

def format_page(page: dict, state: str | None, attributes: dict | None) -> dict:
    text = page.get("text", "")
    if page.get("entity_id"):
        if state in (None, "unknown", "unavailable"):
            value = "Nedostupné"
        else:
            value = state
            try:
                number = float(state)
                if math.isfinite(number):
                    value = f"{number:.{page.get('decimals', 1)}f}".replace(".", ",")
                else:
                    value = "Nedostupné"
            except (ValueError, TypeError):
                value = {"on": "Zapnuto", "off": "Vypnuto"}.get(state, state)
            if page.get("show_unit", True):
                unit = (attributes or {}).get("unit_of_measurement", "")
                if unit:
                    value += " " + str(unit)
        text = f"{text} {value}".strip()
    text = unicodedata.normalize("NFC", text).replace("℃", "°C").replace("℉", "°F")
    # Protokol má limit v bajtech; nikdy nesmíme rozdělit UTF-8 znak.
    text = text.encode("utf-8")[:384].decode("utf-8", errors="ignore")
    return {"id": page["id"], "text": text,
        "hold_ms": int(page.get("hold_seconds", 5) * 1000),
        "speed": int(page.get("speed", 20)), "scroll_right": page.get("scroll_right", False),
        "enter": page.get("enter", "none"), "exit": page.get("exit", "none"),
        "transition_ms": int(page.get("transition_ms", 600)),
        "blink": page.get("blink", "none"), "blink_ms": int(page.get("blink_ms", 1000)),
        "invert": page.get("invert", False)}
