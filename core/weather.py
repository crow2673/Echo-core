#!/usr/bin/env python3
"""
core/weather.py
Fetches current weather for Little Rock, AR.
Used by daily_briefing.py for morning context.
"""
import json
import urllib.request
from datetime import datetime

# Little Rock, AR coordinates
LAT = 34.7465
LON = -92.2896

def get_weather():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,weathercode,windspeed_10m,precipitation&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=America%2FChicago"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Echo/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        current = data.get("current", {})
        temp = current.get("temperature_2m", "?")
        wind = current.get("windspeed_10m", "?")
        precip = current.get("precipitation", 0)
        code = current.get("weathercode", 0)

        # WMO weather codes simplified
        if code == 0:
            condition = "clear"
        elif code in [1, 2, 3]:
            condition = "partly cloudy"
        elif code in [45, 48]:
            condition = "foggy"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            condition = "rainy"
        elif code in [71, 73, 75, 77, 85, 86]:
            condition = "snowing"
        elif code in [95, 96, 99]:
            condition = "thunderstorms"
        else:
            condition = "overcast"

        shop_day = precip == 0 and code < 45
        summary = f"{temp}°F, {condition}, wind {wind}mph"
        if precip > 0:
            summary += f", {precip}mm precip"

        return {
            "summary": summary,
            "temp": temp,
            "condition": condition,
            "wind": wind,
            "precipitation": precip,
            "shop_day": shop_day,
            "advice": "Good shop day." if shop_day else "Stay inside day."
        }
    except Exception as e:
        return {"summary": f"weather unavailable ({e})", "shop_day": None, "advice": ""}

if __name__ == "__main__":
    w = get_weather()
    print(w["summary"])
    print(w["advice"])
