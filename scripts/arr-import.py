#!/usr/bin/env python3
"""Library Import for Radarr/Sonarr (+ remote pair), in place: existing folders become the movie/series
path; nothing is moved or renamed. API keys come from each app's config.xml and are never printed.

  scripts/arr-import.py            # dry run: match every unmapped folder, report
  scripts/arr-import.py --apply    # import the confident, unambiguous matches (no searches)

A folder is imported only if the app's lookup gives a title (and year, if the folder has one) match, and
no other folder maps to the same movie/series, except that a clean "Title (Year)" folder wins over
release-named copies of the same title (those stay where they are, unmanaged). Everything else is reported for a manual decision:
duplicates (two folders, one title), release/episode folders, loose files, no confident match.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

APPS = {  # name: (kind, port, quality profile)
    "radarr": ("radarr", 7878, "Up to 2160p"),
    "sonarr": ("sonarr", 8989, "Up to 2160p"),
    "radarr-remote": ("radarr", 7879, "HD-720p"),
    "sonarr-remote": ("sonarr", 8990, "HD-720p"),
}
VIDEO = {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".mov", ".wmv"}
JUNK_PREFIX = re.compile(r"^\s*www\.\S+\s*-\s*", re.I)
YEAR_SUFFIX = re.compile(r"\s*\(\d{4}\)$")
CLEAN_FOLDER = re.compile(r"^[^\[\]{}]+ \(\d{4}\)$")  # "Title (Year)": preferred over release-named folders


def norm(s: str) -> str:
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


class Api:
    def __init__(self, name: str, port: int):
        self.name, self.base = name, f"http://localhost:{port}/api/v3"
        self._key = re.search(r"<ApiKey>([^<]+)</ApiKey>", Path(f"/srv/homelab/{name}/config.xml").read_text())[1]

    def call(self, method: str, path: str, body=None, **params):
        url = f"{self.base}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"X-Api-Key": self._key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            sys.exit(f"{self.name}: {method} {path} -> HTTP {e.code}: {e.read().decode()[:400]}")


def guess(api: Api, kind: str, folder: str) -> tuple[str, int | None, bool]:
    """(title, year, is_release) from the app's own parser, falling back to 'Title (Year)'."""
    clean = JUNK_PREFIX.sub("", folder)
    parsed = api.call("GET", "parse", title=clean) or {}
    if kind == "radarr":
        info = parsed.get("parsedMovieInfo") or {}
        titles = info.get("movieTitles") or []
        if titles:
            return titles[0], info.get("year") or None, False
    else:
        info = parsed.get("parsedEpisodeInfo") or {}
        if info.get("seriesTitle") and (info.get("episodeNumbers") or info.get("fullSeason")
                                         or info.get("seasonNumber")):
            return info["seriesTitle"], (info.get("seriesTitleInfo") or {}).get("year") or None, True
    m = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", clean)
    if m:
        return m[1], int(m[2]), False
    m = re.match(r"^(.*?)[\s.]+(?:-\s*)?Season\s*\d+$", clean, re.I)
    if m and kind == "sonarr":
        return m[1], None, True
    return clean, None, False


def lookup(api: Api, kind: str, title: str, year: int | None):
    term = f"{title} {year}" if year and kind == "radarr" else title
    results = api.call("GET", "movie/lookup" if kind == "radarr" else "series/lookup", term=term) or []
    def same_title(r) -> bool:
        names = {norm(r["title"]), norm(YEAR_SUFFIX.sub("", r["title"]))}
        names |= {norm(a.get("title", "")) for a in r.get("alternateTitles") or []}
        return norm(title) in names

    candidates = [r for r in results[:10] if same_title(r)]
    # Year given: a matching year wins; a result with no year only if nothing matches the year.
    for r in candidates:
        if not year or (r.get("year") and abs(r["year"] - year) <= 1):
            return r, True
    for r in candidates:
        if not r.get("year"):
            return r, True
    return (results[0] if results else None), False


def run(name: str, apply: bool) -> None:
    kind, port, profile_name = APPS[name]
    api = Api(name, port)
    root = api.call("GET", "rootfolder")[0]
    detail = api.call("GET", f"rootfolder/{root['id']}")
    folders = sorted(u["name"] for u in detail.get("unmappedFolders") or [])
    loose = [p.name for p in Path(root["path"]).iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO and not p.name.startswith("._")]
    profile = next(p["id"] for p in api.call("GET", "qualityprofile") if p["name"] == profile_name)
    idkey = "tmdbId" if kind == "radarr" else "tvdbId"

    matched, releases, unsure = defaultdict(list), [], []
    for f in folders:
        title, year, is_release = guess(api, kind, f)
        hit, sure = lookup(api, kind, title, year)
        if is_release:
            releases.append((f, hit and f"{hit['title']} ({hit.get('year')})"))
        elif hit and sure:
            matched[hit[idkey]].append((f, hit))
        else:
            unsure.append((f, hit and f"{hit['title']} ({hit.get('year')})"))
    importable, dupes, leftovers = {}, {}, []
    for k, v in matched.items():
        clean = [x for x in v if CLEAN_FOLDER.match(x[0])]
        if len(v) == 1:
            importable[k] = v[0]
        elif len(clean) == 1:  # one "Title (Year)" folder + release-named leftovers (old seeding copies)
            importable[k] = clean[0]
            leftovers += [x[0] for x in v if x is not clean[0]]
        else:
            dupes[k] = v

    print(f"== {name}: {len(folders)} unmapped folders, {len(loose)} loose video files in {root['path']}")
    print(f"   importable: {len(importable)}  left alone: {len(leftovers)} release-named duplicates, "
          f"{sum(len(v) for v in dupes.values())} unresolved duplicates, {len(releases)} release/episode folders, "
          f"{len(unsure)} no confident match")
    for f, hit in sorted(importable.values(), key=lambda x: x[0]):
        print(f"   IMPORT {f}  -> {hit['title']} ({hit.get('year')}) {idkey}={hit[idkey]}")
    for f in leftovers:
        print(f"   LEFTOVER {f}")
    for k, v in dupes.items():
        print(f"   DUPLICATE {v[0][1]['title']} ({v[0][1].get('year')}): " + " | ".join(f for f, _ in v))
    for f, h in releases:
        print(f"   RELEASE FOLDER {f}  -> {h}")
    for f, h in unsure:
        print(f"   UNSURE {f}  -> best guess {h}")
    for f in sorted(loose):
        print(f"   LOOSE FILE {f}")
    if not apply or not importable:
        return

    items = []
    for f, hit in importable.values():
        item = {**hit, "path": f"{root['path'].rstrip('/')}/{f}", "qualityProfileId": profile,
                "monitored": True, "rootFolderPath": root["path"]}
        if kind == "radarr":
            item.update(minimumAvailability="released",
                        addOptions={"searchForMovie": False, "monitor": "movieOnly"})
        else:
            item.update(seasonFolder=True, addOptions={
                "monitor": "all", "searchForMissingEpisodes": False, "searchForCutoffUnmetEpisodes": False})
        items.append(item)
    api.call("POST", "movie/import" if kind == "radarr" else "series/import", items)
    print(f"   imported {len(items)} in place (no search). Waiting for disk scan...")
    for _ in range(60):
        time.sleep(5)
        if not any(c["status"] in ("queued", "started") for c in api.call("GET", "command")):
            break
    if kind == "radarr":
        movies = api.call("GET", "movie")
        print(f"   radarr now has {len(movies)} movies, {sum(1 for m in movies if m.get('hasFile'))} with a file")
    else:
        series = api.call("GET", "series")
        files = sum((s.get("statistics") or {}).get("episodeFileCount", 0) for s in series)
        print(f"   sonarr now has {len(series)} series, {files} episode files")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    for n in [a for a in sys.argv[1:] if not a.startswith("--")] or APPS:
        run(n, apply)
