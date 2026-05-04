from __future__ import annotations

import requests

from config import TIMEZONE, WEATHER_LAT, WEATHER_LON

WMO_CODES = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorms",
}


def _what_to_wear(high_f: float, precip_probability: int | None, conditions: str) -> str:
    if high_f < 55:
        line = "Wear a warm layer."
    elif high_f < 68:
        line = "A light layer should be enough."
    else:
        line = "Short sleeves should be comfortable."
    if precip_probability and precip_probability >= 40:
        line += " Bring an umbrella."
    elif "rain" in conditions or "drizzle" in conditions:
        line += " Keep a rain layer handy."
    return line


def get_weather() -> dict | None:
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": WEATHER_LAT,
                "longitude": WEATHER_LON,
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "timezone": TIMEZONE,
                "forecast_days": 1,
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        current = data["current"]
        daily = data["daily"]
        current_temp = round(float(current["temperature_2m"]))
        high = round(float(daily["temperature_2m_max"][0]))
        low = round(float(daily["temperature_2m_min"][0]))
        precip = daily.get("precipitation_probability_max", [None])[0]
        conditions = WMO_CODES.get(int(current["weather_code"]), "conditions unavailable")
        return {
            "current_temp_f": current_temp,
            "conditions": conditions,
            "high_f": high,
            "low_f": low,
            "precip_probability": precip,
            "what_to_wear": _what_to_wear(high, precip, conditions),
        }
    except Exception:
        return None
