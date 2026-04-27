#!/usr/bin/env python3
"""
core/weather.py
Fetches current weather for Little Rock, AR (closest major city to Mena).
Used by daily_briefing.py for morning context.
"""
import json
import urllib.request
from pathlib import Path

LAT = 34.7465
LON = -92.2896


def get_weather() -> dict:
    """Returns dict with summary and advice keys."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={LAT}&longitude={LON}"
            f"&current=temperature_2m,weathercode,windspeed_10m,precipitation"
            f"&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=America%2FChicago"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        current = data.get("current", {})
        temp = current.get("temperature_2m", "?")
        wind = current.get("windspeed_10m", 0)
        precip = current.get("precipitation", 0)
        code = current.get("weathercode", 0)

        conditions = {
            range(0, 1): "clear", range(1, 4): "mostly clear", range(45, 48): "foggy",
            range(51, 68): "rainy", range(71, 78): "snowy", range(80, 83): "showers",
            range(95, 100): "thunderstorms",
        }
        condition = "cloudy"
        for r_obj, desc in conditions.items():
            if code in r_obj:
                condition = desc
                break

        summary = f"{temp}°F, {condition}, wind {wind}mph"
        advice = ""
        if precip > 0:
            advice = "Bring a jacket — precipitation expected."
        elif temp > 90:
            advice = "Hot today — stay hydrated."
        elif temp < 35:
            advice = "Cold today — dress warm."

        return {"summary": summary, "advice": advice, "temp": temp, "condition": condition}
    except Exception as e:
        return {"summary": "weather unavailable", "advice": "", "error": str(e)}


if __name__ == "__main__":
    w = get_weather()
    print(w["summary"])
    if w["advice"]:
        print(w["advice"])
