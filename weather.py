"""
Weather lookup via Open-Meteo (no API key, free for non-commercial).
Geocoding endpoint resolves city -> lat/lon, forecast endpoint returns current conditions.
"""

import logging
import re
import urllib.parse
import urllib.request
import json

log = logging.getLogger("jarvis.weather")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 5.0
DEFAULT_CITY = "Ames"        # Fallback when user doesn't specify
DEFAULT_UNIT = "fahrenheit"  # F by default, user can override per-utterance

# WMO weather codes -> plain English
# https://open-meteo.com/en/docs (search "weather_code")
WMO = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy with rime",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "raining", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snowing", 75: "heavy snow",
    77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _http_get_json(url: str, params: dict) -> dict | None:
    """GET with query params, return parsed JSON or None on failure."""
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    try:
        with urllib.request.urlopen(full, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        log.warning(f"HTTP GET failed: {full} -> {e}")
        return None


def geocode(city: str) -> tuple[float, float, str, str] | None:
    """Resolve city name -> (lat, lon, display_name, country)."""
    data = _http_get_json(GEOCODE_URL, {"name": city, "count": 1})
    if not data or not data.get("results"):
        return None
    r = data["results"][0]
    return (r["latitude"], r["longitude"], r["name"], r.get("country", ""))


def get_current(lat: float, lon: float, unit: str = "fahrenheit") -> dict | None:
    """Fetch current conditions for coords. Returns dict with temp, code, etc."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
        "temperature_unit": unit,
        "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
        "timezone": "auto",
    }
    data = _http_get_json(FORECAST_URL, params)
    if not data or "current" not in data:
        return None
    return data["current"]


def describe(weather_code: int) -> str:
    return WMO.get(weather_code, "an unusual sky")


# ---- Intent router ----

# Patterns that signal a weather query
WEATHER_TRIGGERS = ("weather", "temperature", "forecast", "raining",
                    "snowing", "how hot", "how cold", "how warm")

# Extract city from "weather in <city>" or "weather for <city>" or "in <city>"
RX_CITY = re.compile(
    r"\b(?:weather|temperature|forecast)\s+(?:in|for|at)\s+([a-zA-Z][a-zA-Z\s,.-]*?)(?:\s+in\s+(?:celsius|fahrenheit|c|f))?[.?!]?$",
    re.IGNORECASE,
)
# Fallback: just "in <city>" anywhere
RX_IN_CITY = re.compile(r"\bin\s+([a-zA-Z][a-zA-Z\s,.-]+?)(?:\s+in\s+(?:celsius|fahrenheit|c|f))?[.?!]?$", re.IGNORECASE)

# Unit override
RX_CELSIUS = re.compile(r"\bin\s+(celsius|c)\b", re.IGNORECASE)
RX_FAHRENHEIT = re.compile(r"\bin\s+(fahrenheit|f)\b", re.IGNORECASE)


def is_weather_intent(text: str) -> bool:
    t = text.lower()
    return any(trig in t for trig in WEATHER_TRIGGERS)


def extract_city(text: str) -> str:
    """Try to pull a city name out of the utterance. Fall back to DEFAULT_CITY."""
    m = RX_CITY.search(text)
    if m:
        city = m.group(1).strip().rstrip(",.")
        # Clean up trailing words like "today", "now"
        city = re.sub(r"\b(today|now|right now|currently)\b", "", city, flags=re.IGNORECASE).strip()
        if city:
            return city
    # Don't use RX_IN_CITY broadly — too many false matches ("turn off in a moment")
    return DEFAULT_CITY


def extract_unit(text: str) -> str:
    if RX_CELSIUS.search(text):
        return "celsius"
    if RX_FAHRENHEIT.search(text):
        return "fahrenheit"
    return DEFAULT_UNIT


def handle(text: str) -> str | None:
    """
    Try to handle a weather command. Returns a reply string if handled,
    None if not a weather query (caller falls through to LLM).
    """
    if not is_weather_intent(text):
        return None

    city = extract_city(text)
    unit = extract_unit(text)
    log.info(f"weather intent: city={city!r} unit={unit}")

    geo = geocode(city)
    if not geo:
        return f"I couldn't find {city}, sir."

    lat, lon, display_name, country = geo
    current = get_current(lat, lon, unit)
    if not current:
        return "The weather service is unavailable, sir."

    temp = round(current["temperature_2m"])
    desc = describe(current["weather_code"])
    unit_word = "Fahrenheit" if unit == "fahrenheit" else "Celsius"

    return f"Currently {temp} {unit_word} and {desc} in {display_name}, sir."


if __name__ == "__main__":
    # CLI smoke test: python3 weather.py "what's the weather in Tokyo"
    import sys
    logging.basicConfig(level=logging.DEBUG)
    msg = " ".join(sys.argv[1:]) or "what's the weather"
    print(f"input: {msg!r}")
    print(f"reply: {handle(msg)!r}")
