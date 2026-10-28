#!/usr/bin/env python3
"""Radarr/Sonarr (+ remote 720p pair) and Prowlarr wiring, idempotent. Secrets are never printed.

  scripts/arr-setup.py          # root folders, qBittorrent client, quality profiles + sizes, naming, hardlinks, Prowlarr
  scripts/arr-setup.py sizes    # only the main pair's 2160p size caps (MAIN_SIZES)
  scripts/arr-setup.py auth     # Forms login on all five from ARR_USERNAME / ARR_PASSWORD in .env
  scripts/arr-setup.py discord  # "Discord" connection on all four: imports + upgrades to DISCORD_WEBHOOK_URL

API keys are read from each app's config.xml; qBittorrent login from .env.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QBIT = {"host": "gluetun", "port": 8083}
MAIN_PROFILE = "Up to 2160p"
# name: (kind, host port, container port, root folder, qBittorrent category, quality profile, Prowlarr label)
ARRS = {
    "radarr":        ("radarr", 7878, 7878, "/mnt/media/movies",      "movies",        MAIN_PROFILE, "Radarr"),
    "sonarr":        ("sonarr", 8989, 8989, "/mnt/media/tv",          "tv",            MAIN_PROFILE, "Sonarr"),
    "radarr-remote": ("radarr", 7879, 7878, "/mnt/media/movies-720p", "movies-remote", "HD-720p",    "Radarr (Remote)"),
    "sonarr-remote": ("sonarr", 8990, 8989, "/mnt/media/tv-720p",     "tv-remote",     "HD-720p",    "Sonarr (Remote)"),
}
PROWLARR = ("prowlarr", 9696, 9696)
CATEGORY_FIELD = {"radarr": "movieCategory", "sonarr": "tvCategory"}
# Main profile: these resolutions, minus disc/remux sizes. Cutoff Bluray-2160p.
MAIN_RES = {720, 1080, 2160}
MAIN_EXCLUDE = re.compile(r"Remux|BR-DISK|Raw-HD", re.I)
MAIN_CUTOFF = "Bluray-2160p"
# Main pair: 2160p size cap in MB per minute (140 ≈ 20 GB for a 2h20 film), preferred 100. Min unchanged.
# Quality sizes are per app (not per profile); the remote pair is 720p-only and keeps the defaults.
MAIN_SIZES = {q: (100, 140) for q in ("HDTV-2160p", "WEBDL-2160p", "WEBRip-2160p", "Bluray-2160p")}
# Jellyfin-friendly naming (new imports): ids in folder names, files start with the folder name so
# Jellyfin groups versions. Colon replacement "smart" (Radarr) / 4 (Sonarr), multi-episode S01E01-E02.
_MEDIA = "{[MediaInfo VideoDynamicRangeType]}{[Mediainfo AudioCodec}{ Mediainfo AudioChannels]}{[MediaInfo VideoCodec]}{-Release Group}"
NAMING = {
    "radarr": {
        "renameMovies": True,
        "movieFolderFormat": "{Movie CleanTitle} ({Release Year}) [tmdbid-{TmdbId}]",
        "standardMovieFormat": "{Movie CleanTitle} ({Release Year}) [tmdbid-{TmdbId}] - {edition-{Edition Tags}} {[Quality Full]}" + _MEDIA,
    },
    "sonarr": {
        "renameEpisodes": True,
        "seriesFolderFormat": "{Series TitleYear} [tvdbid-{TvdbId}]",
        "seasonFolderFormat": "Season {season:00}",
        "specialsFolderFormat": "Season 00",
        "multiEpisodeStyle": 5,
        "standardEpisodeFormat": "{Series TitleYear} - S{season:00}E{episode:00} - {Episode CleanTitle} {[Quality Full]}" + _MEDIA,
        "dailyEpisodeFormat": "{Series TitleYear} - {Air-Date} - {Episode CleanTitle} {[Quality Full]}" + _MEDIA,
        "animeEpisodeFormat": "{Series TitleYear} - S{season:00}E{episode:00} - {absolute:000} - {Episode CleanTitle} {[Quality Full]}" + _MEDIA,
    },
}


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


class Api:
    def __init__(self, name: str, port: int, version: str):
        self.name, self.base = name, f"http://localhost:{port}/api/{version}"
        cfg = (Path(env().get("APPDATA_PATH", "/srv/homelab")) / name / "config.xml").read_text()
        self._key = re.search(r"<ApiKey>([^<]+)</ApiKey>", cfg)[1]

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/{path}", data=data, method=method,
                                     headers={"X-Api-Key": self._key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            sys.exit(f"{self.name}: {method} {path} -> HTTP {e.code}: {detail}")

    def upsert(self, path: str, match: dict, body: dict, label: str, test: bool = False) -> dict:
        """Create, or update the first item whose fields equal `match`. test: POST <path>/test first."""
        item = next((i for i in self.call("GET", path) if all(i.get(k) == v for k, v in match.items())), None)
        if item:
            body = {**item, **body, "id": item["id"]}
        if test:
            self.call("POST", f"{path}/test", body)
        out = self.call("PUT", f"{path}/{item['id']}", body) if item else self.call("POST", path, body)
        print(f"  {label}: {'updated' if item else 'created'}")
        return out


def set_fields(fields: list[dict], values: dict) -> list[dict]:
    missing = set(values) - {f["name"] for f in fields}
    if missing:
        sys.exit(f"schema has no fields {missing}")
    return [{**f, "value": values[f["name"]]} if f["name"] in values else f for f in fields]


def main_profile(api: Api) -> dict:
    """'Any' profile reshaped: 720p-2160p allowed (no remux/disc), upgrades until Bluray-2160p."""
    base = next(p for p in api.call("GET", "qualityprofile") if p["name"] == "Any")
    res = {q["quality"]["id"]: q["quality"]["resolution"] for q in api.call("GET", "qualitydefinition")}

    def ok(q: dict) -> bool:
        return res.get(q["id"]) in MAIN_RES and not MAIN_EXCLUDE.search(q["name"])

    items, cutoff = [], None
    for it in base["items"]:
        it = json.loads(json.dumps(it))
        if it.get("items"):  # group, e.g. "WEB 2160p"
            for sub in it["items"]:
                sub["allowed"] = ok(sub["quality"])
            it["allowed"] = any(s["allowed"] for s in it["items"])
        else:
            it["allowed"] = ok(it["quality"])
            if it["quality"]["name"] == MAIN_CUTOFF:
                cutoff = it["quality"]["id"]
        items.append(it)
    if cutoff is None:
        sys.exit(f"{api.name}: no {MAIN_CUTOFF} quality")
    body = {k: v for k, v in base.items() if k != "id"}
    body.update(name=MAIN_PROFILE, upgradeAllowed=True, cutoff=cutoff, items=items)
    return body


def quality_sizes(api: Api) -> None:
    """Preferred/max size (MB/min) for MAIN_SIZES qualities; prints before -> after."""
    for qd in api.call("GET", "qualitydefinition"):
        name = qd["quality"]["name"]
        if name not in MAIN_SIZES:
            continue
        pref, mx = MAIN_SIZES[name]
        before = f"min {qd['minSize']}, preferred {qd.get('preferredSize')}, max {qd.get('maxSize')}"
        if (qd.get("preferredSize"), qd.get("maxSize")) != (pref, mx):
            qd = api.call("PUT", f"qualitydefinition/{qd['id']}", {**qd, "preferredSize": pref, "maxSize": mx})
        print(f"  size {name}: {before} -> min {qd['minSize']}, preferred {qd['preferredSize']}, max {qd['maxSize']} MB/min")


def sizes() -> None:
    for name, (_, port, _, _, _, profile, _) in ARRS.items():
        if profile == MAIN_PROFILE:
            print(name)
            quality_sizes(Api(name, port, "v3"))


def setup() -> None:
    e = env()
    qb_user, qb_pass = e.get("QBITTORRENT_USERNAME"), e.get("QBITTORRENT_PASSWORD")
    if not qb_user or not qb_pass:
        sys.exit("QBITTORRENT_USERNAME / QBITTORRENT_PASSWORD missing in .env")
    keys = {}
    for name, (kind, port, cport, root, cat, profile, _) in ARRS.items():
        api = Api(name, port, "v3")
        keys[name] = api._key
        print(f"{name} ({api.call('GET', 'system/status')['version']})")

        if not any(r["path"].rstrip("/") == root for r in api.call("GET", "rootfolder")):
            api.call("POST", "rootfolder", {"path": root})
            print(f"  root folder {root}: created")
        else:
            print(f"  root folder {root}: present")

        schema = next(s for s in api.call("GET", "downloadclient/schema") if s["implementation"] == "QBittorrent")
        # removeCompletedDownloads: once imported and stopped at ratio 1.0 (qbit-setup.py), delete
        # torrent + files; the library keeps its hardlink.
        client = {**schema, "name": "qBittorrent", "enable": True, "priority": 1,
                  "removeCompletedDownloads": True, "removeFailedDownloads": True,
                  "fields": set_fields(schema["fields"], {
                      "host": QBIT["host"], "port": QBIT["port"], "useSsl": False,
                      "username": qb_user, "password": qb_pass, CATEGORY_FIELD[kind]: cat})}
        client.pop("id", None)
        api.upsert("downloadclient", {"name": "qBittorrent"}, client, f"qBittorrent client (category {cat}, test OK)", test=True)

        if profile == MAIN_PROFILE:
            api.upsert("qualityprofile", {"name": MAIN_PROFILE}, main_profile(api), f"quality profile {MAIN_PROFILE!r}")
            quality_sizes(api)
        elif not any(p["name"] == profile for p in api.call("GET", "qualityprofile")):
            sys.exit(f"{name}: quality profile {profile!r} missing")
        else:
            print(f"  quality profile {profile!r}: built-in")

        naming = api.call("GET", "config/naming")
        api.call("PUT", f"config/naming/{naming['id']}", {**naming, **NAMING[kind]})
        print("  naming: Jellyfin format, rename on (applies to new imports; existing files untouched)")

        mm = api.call("GET", "config/mediamanagement")
        if not mm.get("copyUsingHardlinks"):
            api.call("PUT", f"config/mediamanagement/{mm['id']}", {**mm, "copyUsingHardlinks": True})
        print("  hardlinks: on")

    prowlarr = Api(PROWLARR[0], PROWLARR[1], "v1")
    print(f"prowlarr ({prowlarr.call('GET', 'system/status')['version']})")
    schemas = {s["implementation"]: s for s in prowlarr.call("GET", "applications/schema")}
    for name, (kind, port, cport, _, _, _, label) in ARRS.items():
        schema = schemas[kind.capitalize()]
        app = {**schema, "name": label, "syncLevel": "fullSync",
               "fields": set_fields(schema["fields"], {
                   "prowlarrUrl": f"http://prowlarr:{PROWLARR[2]}",
                   "baseUrl": f"http://{name}:{cport}",
                   "apiKey": keys[name]})}
        app.pop("id", None)
        prowlarr.upsert("applications", {"name": label}, app, f"app {label} -> http://{name}:{cport} (full sync, test OK)", test=True)


def discord() -> None:
    """One Discord connection per app, for imports and upgrades only (the Discord feed; ntfy keeps urgent alerts).
    The apps test a connection on every save (a bad URL fails the save), so every app posts one test message;
    no separate test call, which would post a second."""
    url = env().get("DISCORD_WEBHOOK_URL", "")
    if not url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        sys.exit("DISCORD_WEBHOOK_URL missing or not a Discord webhook in .env")
    for name, (kind, port, *_r, label) in ARRS.items():
        api = Api(name, port, "v3")
        schema = next(s for s in api.call("GET", "notification/schema") if s["implementation"] == "Discord")
        events = {k: False for k, v in schema.items() if re.fullmatch(r"on[A-Z]\w*", k) and isinstance(v, bool)}
        events.update(onDownload=True, onUpgrade=True)
        body = {**schema, **events, "name": "Discord", "includeHealthWarnings": False, "tags": [],
                "fields": set_fields(schema["fields"], {"webHookUrl": url, "username": label})}
        body.pop("id", None)
        api.upsert("notification", {"name": "Discord"}, body, f"{name}: Discord on import + upgrade (test OK)")


def auth() -> None:
    e = env()
    user, pw = e.get("ARR_USERNAME"), e.get("ARR_PASSWORD")
    if not user or not pw:
        sys.exit("ARR_USERNAME / ARR_PASSWORD missing in .env")
    apps = [(n, p, "v3") for n, (_, p, *_r) in ARRS.items()] + [(PROWLARR[0], PROWLARR[1], "v1")]
    for name, port, version in apps:
        api = Api(name, port, version)
        host = api.call("GET", "config/host")
        host.update(authenticationMethod="forms", authenticationRequired="enabled",
                    username=user, password=pw, passwordConfirmation=pw)
        api.call("PUT", f"config/host/{host['id']}", host)
        after = api.call("GET", "config/host")
        print(f"{name}: auth {after['authenticationMethod']}/{after['authenticationRequired']}")


if __name__ == "__main__":
    {"auth": auth, "sizes": sizes, "discord": discord}.get(sys.argv[1] if len(sys.argv) > 1 else "", setup)()
