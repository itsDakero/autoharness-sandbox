#!/usr/bin/env python3
"""Rename files to the naming format in each arr app. Movie/series folders are never moved.
API keys come from each app's config.xml and are never printed.

  scripts/arr-rename.py [app ...] [--examples N]   # preview (read-only)
  scripts/arr-rename.py [app ...] --apply          # rename files (Sonarr also sorts into Season NN/)
"""
import time
import importlib.util
import re
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("arr_import", Path(__file__).with_name("arr-import.py"))
arr_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arr_import)


def preview(name: str, examples: int) -> None:
    kind, port, _ = arr_import.APPS[name]
    api = arr_import.Api(name, port)
    items = api.call("GET", "movie" if kind == "radarr" else "series")
    renames, folders = [], []
    for it in items:
        key = "movieId" if kind == "radarr" else "seriesId"
        for r in api.call("GET", "rename", **{key: it["id"]}) or []:
            renames.append((it["title"], r["existingPath"], r["newPath"]))
        have = Path(it["path"]).name
        idtag = f"[tmdbid-{it['tmdbId']}]" if kind == "radarr" else f"[tvdbid-{it['tvdbId']}]"
        if not have.endswith(idtag):  # the apps don't expose the target folder name; the id tag is the tell
            folders.append((have, idtag))
    files = sum(1 for _ in items if kind == "radarr" and _.get("hasFile")) if kind == "radarr" else \
        sum((s.get("statistics") or {}).get("episodeFileCount", 0) for s in items)
    print(f"== {name}: {len(renames)} of {files} files would be renamed; "
          f"{len(folders)} of {len(items)} folders differ from the folder format (Rename doesn't move folders)")
    for title, old, new in renames[:examples]:
        print(f"   {old}\n     -> {new}")
    for have, want in folders[:min(examples, 3)]:
        print(f"   folder: {have}  (no {want})")


def apply(name: str) -> None:
    kind, port, _ = arr_import.APPS[name]
    api = arr_import.Api(name, port)
    if kind == "radarr":
        ids = [m["id"] for m in api.call("GET", "movie") if m.get("hasFile")]
        cmd = api.call("POST", "command", {"name": "RenameMovie", "movieIds": ids})
    else:
        ids = [s["id"] for s in api.call("GET", "series")]
        cmd = api.call("POST", "command", {"name": "RenameSeries", "seriesIds": ids})
    for _ in range(120):
        state = api.call("GET", f"command/{cmd['id']}")
        if state["status"] not in ("queued", "started"):
            break
        time.sleep(2)
    print(f"== {name}: {cmd['name']} for {len(ids)} items: {state['status']} {state.get('message') or ''}")


if __name__ == "__main__":
    args = sys.argv[1:]
    n = int(args[args.index("--examples") + 1]) if "--examples" in args else 4
    apps = [a for a in args if a in arr_import.APPS] or list(arr_import.APPS)
    for a in apps:
        apply(a) if "--apply" in args else None
        preview(a, n)
