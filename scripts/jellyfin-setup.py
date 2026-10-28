#!/usr/bin/env python3
"""Jellyfin libraries + NVENC transcoding, idempotent. JELLYFIN_API_KEY from .env, never printed.

  scripts/jellyfin-setup.py           # libraries, hardware transcoding (server name is set in the wizard)
  scripts/jellyfin-setup.py status    # libraries, encoding, Intro Skipper plugin and task triggers (read-only)
  scripts/jellyfin-setup.py plugins   # Intro Skipper: repository, pinned install, no plugin auto-update,
                                      # nightly analysis window (run again after restarting Jellyfin)

Run after the first-run wizard (admin user) and creating an API key (Dashboard > API Keys).
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = "http://localhost:8096"
LIBRARIES = [  # name, collection type, path
    ("Movies", "movies", "/mnt/media/movies"),
    ("TV", "tvshows", "/mnt/media/tv"),
    ("Movies (Remote)", "movies", "/mnt/media/movies-720p"),
    ("TV (Remote)", "tvshows", "/mnt/media/tv-720p"),
]
# GTX 970 (GM204): NVDEC for H.264, MPEG-2, MPEG-4, VC-1 only. No HEVC/VP9/AV1 decode, no 10-bit.
# NVENC: H.264 (and HEVC 8-bit, left off: H.264 output plays everywhere).
ENCODING = {
    "HardwareAccelerationType": "nvenc",
    "EnableHardwareEncoding": True,
    "HardwareDecodingCodecs": ["h264", "mpeg2video", "mpeg4", "vc1"],
    "EnableDecodingColorDepth10Hevc": False,
    "EnableDecodingColorDepth10Vp9": False,
    "EnableDecodingColorDepth10HevcRext": False,
    "EnableDecodingColorDepth12HevcRext": False,
    "EnableEnhancedNvdecDecoder": True,
    "AllowHevcEncoding": False,
    "AllowAv1Encoding": False,
    "EnableTonemapping": True,
}
# Intro Skipper (https://github.com/intro-skipper/intro-skipper), stable 12.0/v12.0.5.0 (2026-10-09).
REPO_NAME = "Intro Skipper"
REPO_URL = "https://intro-skipper.org/manifest.json"
PLUGIN_NAME = "Intro Skipper"
PLUGIN_VERSION = "12.0.5.0"
NIGHT_TICKS = 72000000000  # 02:00 as .NET ticks (2h)
MAX_RUNTIME_TICKS = 144000000000  # 4h
USAGE = "usage: jellyfin-setup.py [status|plugins]"
if sys.argv[1:] not in ([], ["status"], ["plugins"]):
    print(USAGE, file=sys.stderr)
    sys.exit(2)


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


KEY = env().get("JELLYFIN_API_KEY") or sys.exit("JELLYFIN_API_KEY missing in .env")


def call(method: str, path: str, body=None, **params):
    url = f"{URL}{path}" + (f"?{urllib.parse.urlencode(params, doseq=True)}" if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f'MediaBrowser Token="{KEY}"', "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def plugin_info():
    return next((p for p in call("GET", "/Plugins") or [] if p.get("Name") == PLUGIN_NAME), None)


def plugin_tasks() -> list:
    tasks = call("GET", "/ScheduledTasks") or []
    mine = [t for t in tasks if (t.get("Category") or "").lower() == PLUGIN_NAME.lower()]
    return mine or [t for t in tasks if any(w in (t.get("Name") or "").lower() for w in ("intro", "credit"))]


def night_trigger() -> list:
    return [{"Type": "DailyTrigger", "TimeOfDayTicks": NIGHT_TICKS, "MaxRuntimeTicks": MAX_RUNTIME_TICKS}]


def triggers_match(t: dict) -> bool:
    want = night_trigger()
    got = [{k: x.get(k) for k in want[0]} for x in t.get("Triggers") or []]
    return got == want


def plugins() -> None:
    # 1. repository (keep every existing entry)
    repos = call("GET", "/Repositories") or []
    if any(r.get("Url") == REPO_URL for r in repos):
        print(f"repository {REPO_NAME!r}: present")
    else:
        call("POST", "/Repositories", [*repos, {"Name": REPO_NAME, "Url": REPO_URL, "Enabled": True}])
        print(f"repository {REPO_NAME!r}: set ({REPO_URL})")

    # 2. install, pinned; never reinstall or downgrade
    cur = plugin_info()
    if cur and str(cur.get("Version")) == PLUGIN_VERSION:
        print(f"plugin {PLUGIN_NAME!r} {PLUGIN_VERSION}: present ({cur.get('Status')})")
    elif cur:
        print(f"WARNING: plugin {PLUGIN_NAME!r} is {cur.get('Version')}, pinned {PLUGIN_VERSION}; "
              "changing nothing")
    else:
        pkg = next((p for p in call("GET", "/Packages") or [] if p.get("name") == PLUGIN_NAME), None)
        if not pkg:
            sys.exit(f"package {PLUGIN_NAME!r} not found in /Packages (manifest unreachable?); nothing installed")
        versions = [str(v.get("version")) for v in pkg.get("versions") or []]
        if PLUGIN_VERSION not in versions:
            sys.exit(f"{PLUGIN_NAME!r} {PLUGIN_VERSION} not offered (available: {', '.join(versions[:8])}); "
                     "nothing installed")
        call("POST", f"/Packages/Installed/{urllib.parse.quote(PLUGIN_NAME)}",
             assemblyGuid=pkg.get("guid"), version=PLUGIN_VERSION, repositoryUrl=REPO_URL)
        print("plugin: installed, restart needed: scripts/dc.sh media/jellyfin restart")

    # 3. pin: no plugin auto-update
    upd = next((t for t in call("GET", "/ScheduledTasks") or [] if t.get("Key") == "PluginUpdates"), None)
    if not upd:
        print("WARNING: plugin-update task (Key PluginUpdates) not found; auto-update not checked")
    elif upd.get("Triggers"):
        call("POST", f"/ScheduledTasks/{upd['Id']}/Triggers", [])
        print("plugin auto-update: set (triggers cleared)")
    else:
        print("plugin auto-update: present (no triggers)")

    # 4. night window, only once the plugin is loaded
    cur = plugin_info()
    if not cur or cur.get("Status") != "Active":
        print("night window: restart Jellyfin, then run `plugins` again to set the night window")
        return
    tasks = plugin_tasks()
    if not tasks:
        print("WARNING: no Intro Skipper scheduled tasks found; night window not set")
    for t in tasks:
        if triggers_match(t):
            print(f"task {t.get('Name')!r}: present (daily 02:00, max 4h)")
        else:
            call("POST", f"/ScheduledTasks/{t['Id']}/Triggers", night_trigger())
            print(f"task {t.get('Name')!r}: set (daily 02:00, max 4h)")


def status() -> None:
    for f in call("GET", "/Library/VirtualFolders"):
        print(f"library {f['Name']!r} ({f.get('CollectionType')}): {f.get('Locations')}")
    enc = call("GET", "/System/Configuration/encoding")
    for k in ENCODING:
        print(f"encoding {k}: {enc.get(k)}")
    cur = plugin_info()
    print(f"plugin {PLUGIN_NAME!r}: " + (f"{cur.get('Version')} {cur.get('Status')} (pinned {PLUGIN_VERSION})"
                                         if cur else f"not installed (pinned {PLUGIN_VERSION})"))
    for t in plugin_tasks():
        print(f"task {t.get('Name')!r}: triggers {t.get('Triggers')}")


def setup() -> None:
    existing = {f["Name"]: f for f in call("GET", "/Library/VirtualFolders")}
    for name, ctype, path in LIBRARIES:
        if name in existing:
            locs = existing[name].get("Locations") or []
            if path not in locs:
                call("POST", "/Library/VirtualFolders/Paths", {"Name": name, "PathInfo": {"Path": path}})
            print(f"library {name!r}: present ({path})")
            continue
        call("POST", "/Library/VirtualFolders", {"LibraryOptions": {
            "PathInfos": [{"Path": path}],
            "PreferredMetadataLanguage": "en",
            "MetadataCountryCode": "GB",
            "EnableRealtimeMonitor": True,
        }}, name=name, collectionType=ctype, refreshLibrary="false")
        print(f"library {name!r}: created ({ctype}, {path})")

    enc = call("GET", "/System/Configuration/encoding")
    call("POST", "/System/Configuration/encoding", {**enc, **ENCODING})
    after = call("GET", "/System/Configuration/encoding")
    bad = {k: after.get(k) for k, v in ENCODING.items() if after.get(k) != v}
    print("encoding: NVENC on, NVDEC h264/mpeg2/mpeg4/vc1" + (f", MISMATCH {bad}" if bad else ""))

    call("POST", "/Library/Refresh")
    print("library scan started")


if __name__ == "__main__":
    {"status": status, "plugins": plugins}.get(sys.argv[1] if sys.argv[1:] else "", setup)()
