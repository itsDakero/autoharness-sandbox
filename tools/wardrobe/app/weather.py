"""Open-Meteo forecast (free, no key). Network failures return None; parse/season_for are pure."""
import json
import math
import urllib.parse
import urllib.request

URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10
MAX_BYTES = 200_000


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _first(daily, name):
    v = daily.get(name)
    return _num(v[0]) if isinstance(v, list) and v else None


def parse(data):
    """-> {"tmax", "tmin", "rain"} (tmin/rain may be None) or None when tmax is missing."""
    if not isinstance(data, dict) or not isinstance(data.get("daily"), dict):
        return None
    d = data["daily"]
    tmax = _first(d, "temperature_2m_max")
    if tmax is None or not -90 <= tmax <= 70:
        return None
    rain = _first(d, "precipitation_probability_max")
    if rain is not None and not 0 <= rain <= 100:
        rain = None
    return {"tmax": tmax, "tmin": _first(d, "temperature_2m_min"), "rain": rain}


def season_for(month, tmax=None):
    """With a forecast: >=20 summer, <=11 winter, between spring (Mar-Jun) or autumn.
    Without: the month (DJF winter, MAM spring, JJA summer, SON autumn)."""
    if tmax is not None:
        if tmax >= 20:
            return "summer"
        if tmax <= 11:
            return "winter"
        return "spring" if 3 <= month <= 6 else "autumn"
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def fetch(lat, lon):
    """Today's forecast or None (no location, down, slow, odd JSON). Never raises."""
    if lat is None or lon is None:
        return None
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
    try:
        with urllib.request.urlopen(f"{URL}?{q}", timeout=TIMEOUT) as r:
            return parse(json.loads(r.read(MAX_BYTES)))
    except Exception:  # noqa: BLE001
        return None


def describe(w):
    if not w:
        return "No forecast; using the month"
    s = f"{w['tmax']:.0f}°C"
    if w.get("tmin") is not None:
        s += f" (low {w['tmin']:.0f}°C)"
    if w.get("rain") is not None:
        s += f", {w['rain']:.0f}% rain"
    return s


def brief(w):
    s = f"{w['tmax']:.0f}°C"
    if w.get("rain") is not None:
        s += f", {w['rain']:.0f}% rain"
    return s
