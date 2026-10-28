#!/usr/bin/env python3
"""Organise loose files and release/season-pack folders in the Radarr/Sonarr root folders into their
movie/series folders, via the apps' own Manual Import (move + rename to the naming format).

  scripts/arr-organise.py            # dry run: what would be added, moved, skipped (read-only)
  scripts/arr-organise.py --apply    # add missing titles (no search), then Manual Import (move)
  --skip "Title"                     # repeatable: leave this title's files alone (not added, not moved)

Rules:
- A file that is a hardlink of a file already in the target movie/series folder is skipped (same data).
- Titles not in the app yet are added first (monitored like the Library Import, no search), with a
  new folder in the naming format.
- The app's decision stands: rejected files (e.g. not an upgrade) stay where they are. An upgrade
  replaces the existing file, which the app deletes; the dry run lists those as REPLACE.
- Leftover folders (only .nfo/.txt/samples) are not deleted.
API keys come from each app's config.xml and are never printed.
"""
import importlib.util
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("arr_import", Path(__file__).with_name("arr-import.py"))
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)

APPS = ["radarr", "sonarr"]  # the remote pair has nothing loose
SKIP = {sys.argv[i + 1].lower() for i, a in enumerate(sys.argv[:-1]) if a == "--skip"}


def videos(p: Path) -> list[Path]:
    if p.is_file():
        return [p] if p.suffix.lower() in ai.VIDEO and not p.name.startswith("._") else []
    return sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in ai.VIDEO
                  and not f.name.startswith("._") and "sample" not in str(f.relative_to(p)).lower())


def inodes(path: str) -> set[int]:
    out = set()
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                out.add(os.stat(os.path.join(dirpath, f)).st_ino)
            except OSError:
                pass
    return out


def sources(api, kind):
    root = api.call("GET", "rootfolder")[0]
    detail = api.call("GET", f"rootfolder/{root['id']}")
    rootp = Path(root["path"])
    srcs = [rootp / u["name"] for u in detail.get("unmappedFolders") or []]
    srcs += [p for p in rootp.iterdir() if p.is_file()]
    return root, [s for s in srcs if videos(s)]


def owner(item, kind):
    return item.get("movie") if kind == "radarr" else item.get("series")


def plan(name: str):
    kind, port, profile_name = ai.APPS[name]
    api = ai.Api(name, port)
    root, srcs = sources(api, kind)
    lib = api.call("GET", "movie" if kind == "radarr" else "series")
    by_id = {x["id"]: x for x in lib}
    known_inodes = {x["id"]: inodes(x["path"]) for x in lib if Path(x["path"]).exists()}
    idkey = "tmdbId" if kind == "radarr" else "tvdbId"
    known_ext = {x[idkey]: x for x in lib}

    adds, imports, skips = {}, [], []
    for src in srcs:
        for f in videos(src):
            items = api.call("GET", "manualimport", folder=str(f), filterExistingFiles="false") or []
            item = items[0] if items else None
            target = owner(item, kind) if item else None
            if target and target["title"].lower() in SKIP:
                skips.append((f, f"--skip {target['title']}", target))
                continue
            if not target:  # unknown title: work out what to add
                title, year, _ = ai.guess(api, kind, f.name if src.is_file() else src.name)
                hit, sure = ai.lookup(api, kind, title, year)
                if not (hit and sure):
                    skips.append((f, "no confident match", None))
                    continue
                if hit["title"].lower() in SKIP:
                    skips.append((f, f"--skip {hit['title']}", None))
                    continue
                if hit[idkey] in known_ext:
                    target = known_ext[hit[idkey]]
                else:
                    adds.setdefault(hit[idkey], hit)
                    imports.append((f, hit, None, "ADD+IMPORT"))
                    continue
            tid = target["id"]
            if os.stat(f).st_ino in known_inodes.get(tid, set()):
                skips.append((f, "hardlink of a file already in the library folder", target))
                continue
            rej = [r["reason"] for r in item.get("rejections", [])] if item else []
            if rej:
                skips.append((f, "; ".join(rej), target))
                continue
            has = by_id.get(tid, {}).get("hasFile") if kind == "radarr" else any(
                e.get("hasFile") for e in item.get("episodes", []))
            imports.append((f, by_id.get(tid, target), item, "REPLACE" if has else "IMPORT"))
    return api, kind, root, profile_name, adds, imports, skips


def label(kind, f, target, item):
    t = f"{target['title']} ({target.get('year')})"
    if kind == "sonarr" and item:
        eps = ",".join(f"E{e['episodeNumber']:02d}" for e in item.get("episodes", []))
        t += f" S{item.get('seasonNumber', 0):02d}{eps}"
    return t


def report(name):
    api, kind, root, _, adds, imports, skips = plan(name)
    counts = defaultdict(int)
    for *_, how in imports:
        counts[how] += 1
    print(f"== {name}: {len(imports)} files to move in ({counts['IMPORT']} new, {counts['ADD+IMPORT']} for "
          f"{len(adds)} titles to add, {counts['REPLACE']} replacing an existing file), {len(skips)} skipped")
    for hit in adds.values():
        print(f"   ADD {hit['title']} ({hit.get('year')})  -> new folder in {root['path']}")
    for f, target, item, how in sorted(imports, key=lambda x: (x[3], str(x[0]))):
        print(f"   {how:<10} {f.relative_to(root['path'])}\n              -> {label(kind, f, target, item)}")
    reasons = defaultdict(list)
    for f, why, target in skips:
        reasons[why].append(f)
    for why, fs in reasons.items():
        print(f"   SKIP x{len(fs)}: {why}")
        for f in fs[:3]:
            print(f"        e.g. {f.relative_to(root['path'])}")
    return api, kind, root, adds, imports


def apply(name):
    api, kind, root, profile_name, adds, imports, skips = plan(name)
    profile = next(p["id"] for p in api.call("GET", "qualityprofile") if p["name"] == profile_name)
    for hit in adds.values():
        body = {**hit, "qualityProfileId": profile, "rootFolderPath": root["path"], "monitored": True}
        if kind == "radarr":
            body.update(minimumAvailability="released", addOptions={"searchForMovie": False, "monitor": "movieOnly"})
        else:
            body.update(seasonFolder=True, addOptions={"monitor": "all", "searchForMissingEpisodes": False,
                                                       "searchForCutoffUnmetEpisodes": False})
        api.call("POST", "movie" if kind == "radarr" else "series", body)
        print(f"   added {hit['title']} ({hit.get('year')})")
    if adds:  # re-plan so the new titles resolve to ids/episodes
        time.sleep(10)
        api, kind, root, _, _, imports, _ = plan(name)
    files = []
    for f, target, item, how in imports:
        if not item or not owner(item, kind):
            print(f"   not resolved after add, left in place: {f.name}")
            continue
        entry = {"path": str(f), "quality": item["quality"], "languages": item.get("languages") or [],
                 "releaseGroup": item.get("releaseGroup") or ""}
        if kind == "radarr":
            entry["movieId"] = item["movie"]["id"]
        else:
            entry.update(seriesId=item["series"]["id"], episodeIds=[e["id"] for e in item["episodes"]])
        files.append(entry)
    if not files:
        print(f"== {name}: nothing to import")
        return
    cmd = api.call("POST", "command", {"name": "ManualImport", "importMode": "move", "files": files})
    for _ in range(300):
        st = api.call("GET", f"command/{cmd['id']}")
        if st["status"] not in ("queued", "started"):
            break
        time.sleep(2)
    print(f"== {name}: ManualImport (move) of {len(files)} files: {st['status']} {st.get('message') or ''}")


if __name__ == "__main__":
    for n in [a for a in sys.argv[1:] if a in APPS and "--skip" not in sys.argv[sys.argv.index(a) - 1:sys.argv.index(a)]] or APPS:
        apply(n) if "--apply" in sys.argv else report(n)
