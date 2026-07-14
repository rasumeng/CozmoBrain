"""Weather integration. Zero-config via wttr.in, optional OpenWeatherMap key."""

import urllib.request
import urllib.parse
import json
import re

from .base import tool_fn, IntegrationCache


_cache = IntegrationCache(default_ttl=600)


def _fetch_wttr(location: str) -> str:
    """Fetch weather from wttr.in (free, no key)."""
    safe = urllib.parse.quote(location)
    url = f"https://wttr.in/{safe}?format=%C+%t+%w+%h&lang=en"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8").strip()
    return text or "[no data]"


def _fetch_wttr_forecast(location: str) -> str:
    """Fetch short forecast from wttr.in."""
    safe = urllib.parse.quote(location)
    url = f"https://wttr.in/{safe}?format=3&lang=en"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8").strip()
    return text or "[no data]"


def _fetch_owm(location: str, api_key: str) -> str:
    """Fetch weather from OpenWeatherMap."""
    safe = urllib.parse.quote(location)
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={safe}&appid={api_key}&units=metric"
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})
    return (
        f"{weather.get('description', '')}, "
        f"{main.get('temp', '?')}°C, "
        f"feels like {main.get('feels_like', '?')}°C, "
        f"humidity {main.get('humidity', '?')}%, "
        f"wind {wind.get('speed', '?')} m/s"
    )


def _get_weather(location: str) -> str:
    """Get current weather for a location."""
    cached = _cache.get(f"weather:{location}")
    if cached:
        return cached

    try:
        result = _fetch_wttr(location)
        _cache.set(f"weather:{location}", result, ttl=600)
        return result
    except Exception as e:
        return f"[error] weather for {location}: {e}"


def _get_forecast(location: str) -> str:
    """Get short weather forecast for a location."""
    cached = _cache.get(f"forecast:{location}")
    if cached:
        return cached

    try:
        result = _fetch_wttr_forecast(location)
        _cache.set(f"forecast:{location}", result, ttl=600)
        return result
    except Exception as e:
        return f"[error] forecast for {location}: {e}"


get_weather = tool_fn(
    "get_weather",
    "Get current weather conditions for a city or location. Returns temperature, conditions, wind, humidity.",
    _get_weather,
)

get_forecast = tool_fn(
    "get_forecast",
    "Get short weather forecast for a city or location.",
    _get_forecast,
)


def get_tools(config: dict) -> list:
    tools = [get_weather, get_forecast]

    owm_key = config.get("weather", {}).get("api_key", "")
    if owm_key:
        def _owm_weather(location: str) -> str:
            return _fetch_owm(location, owm_key)

        owm_weather = tool_fn(
            "get_weather_detailed",
            "Get detailed weather from OpenWeatherMap (more precise data). Requires configured API key.",
            _owm_weather,
        )
        tools.append(owm_weather)

    return tools
