"""FPL public API + vaastav archive. Every function raises RuntimeError with a one-line reason."""
import time

import requests

UA = {"User-Agent": "homelab-fpl-collector/0.1 (personal use)"}
BASE = "https://fantasy.premierleague.com/api"


def get(url, as_json=True):
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"request failed: {type(e).__name__} for {url.split('?')[0]}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from {url.split('?')[0]}")
    if not as_json:
        return r.content
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f"not JSON (HTML or empty body) from {url.split('?')[0]}")


def bootstrap():
    d = get(f"{BASE}/bootstrap-static/")
    if not isinstance(d, dict) or not all(isinstance(d.get(k), list) for k in ("elements", "events", "teams")):
        raise RuntimeError("bootstrap-static has an unexpected shape")
    return d


def fixtures():
    d = get(f"{BASE}/fixtures/")
    if not isinstance(d, list):
        raise RuntimeError("fixtures has an unexpected shape")
    return d


def live(gw):
    d = get(f"{BASE}/event/{gw}/live/")
    if not isinstance(d, dict) or not isinstance(d.get("elements"), list):
        raise RuntimeError(f"live gw {gw} has an unexpected shape")
    return d


def element_summary(pid):
    d = get(f"{BASE}/element-summary/{pid}/")
    if not isinstance(d, dict):
        raise RuntimeError(f"element-summary {pid} has an unexpected shape")
    return d


def all_summaries(ids, delay=0.5):
    out = {}
    for i in ids:
        out[i] = element_summary(i)
        time.sleep(delay)
    return out


def vaastav_merged_gw(season):
    url = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
    body = get(url, as_json=False)
    if not body:
        raise RuntimeError("vaastav merged_gw.csv is empty")
    return body
