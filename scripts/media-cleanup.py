#!/usr/bin/env python3
"""Plan, then (user-run) apply, deletions in the Radarr/Sonarr root folders.

  scripts/media-cleanup.py plan duplicates      # hardlink duplicates + leftover/empty folders
  scripts/media-cleanup.py plan paths PATH...   # explicit files/folders (e.g. test downloads)
  scripts/media-cleanup.py apply MANIFEST       # the USER runs this; Claude's guard blocks deletes

`plan` is read-only: it writes a manifest (TSV) to /srv/homelab/cleanup/ and prints it. `apply`
re-checks every row right before deleting and skips anything that changed:
  dup    <path> <library path>  delete only if both still exist, are the same inode on the same device
  file   <path> <size>          delete only if the size is unchanged
  junk   <path> <size>          non-video leftover (.nfo/.txt/._*/images/samples) inside a listed dir
  dir    <path>                 remove only if, after the rows above, nothing unlisted is left in it
Library folders (movie/series paths known to the apps) are never listed as dirs, except empty
subfolders inside them (e.g. "Season 1" left behind by a rename). Log: <manifest>.log
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

CLEANUP = Path("/srv/homelab/cleanup")
# Never junk: subtitles (.srt/.sub/.idx/.ass/.vtt) or anything else not listed here; their folders are kept.
JUNK_EXT = {".nfo", ".txt", ".jpg", ".jpeg", ".png", ".url", ".exe", ".dat", ".sfv"}


def arr():
    spec = importlib.util.spec_from_file_location("arr_import", Path(__file__).with_name("arr-import.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def is_video(p: Path) -> bool:
    return p.suffix.lower() in {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".mov", ".wmv"} and not p.name.startswith("._")


def is_junk(p: Path) -> bool:
    return p.name.startswith("._") or p.suffix.lower() in JUNK_EXT or p.name == ".DS_Store" or \
        (is_video(p) and "sample" in str(p).lower())


def write(rows: list[tuple], kind: str) -> Path:
    CLEANUP.mkdir(parents=True, exist_ok=True)
    out = CLEANUP / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.tsv"
    out.write_text("".join("\t".join(map(str, r)) + "\n" for r in rows))
    return out


def plan_duplicates() -> None:
    ai = arr()
    roots, mapped = [], []
    for name in ("radarr", "sonarr"):
        kind, port, _ = ai.APPS[name]
        api = ai.Api(name, port)
        roots.append(Path(api.call("GET", "rootfolder")[0]["path"]))
        mapped += [Path(x["path"]) for x in api.call("GET", "movie" if kind == "radarr" else "series")]
    lib_inodes = {}
    for m in mapped:
        for f in (m.rglob("*") if m.exists() else []):
            if f.is_file() and is_video(f):
                st = f.stat()
                lib_inodes[(st.st_dev, st.st_ino)] = f
    mapped_set = set(mapped)

    rows, kept = [], []
    for root in roots:
        for entry in sorted(root.iterdir()):
            if entry in mapped_set:
                # empty subfolders left inside library folders (only ._/.DS_Store at most)
                for d in sorted((p for p in entry.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                    if all(is_junk(x) and not is_video(x) for x in d.rglob("*") if x.is_file()) and \
                            not any(x.is_dir() for x in d.iterdir()):
                        rows += [("junk", x, x.stat().st_size) for x in d.iterdir() if x.is_file()]
                        rows.append(("dir", d))
                continue
            files = [entry] if entry.is_file() else sorted(p for p in entry.rglob("*") if p.is_file())
            ok = True
            for f in files:
                st = f.stat()
                lib = lib_inodes.get((st.st_dev, st.st_ino)) if is_video(f) and "sample" not in str(f).lower() else None
                if lib:
                    rows.append(("dup", f, lib))
                elif is_junk(f) and entry.is_dir():
                    rows.append(("junk", f, st.st_size))
                elif entry.is_file() and f.name.startswith("._"):
                    continue  # loose macOS stubs in the root: out of scope
                else:
                    ok = False
                    kept.append(f)
            if entry.is_dir():
                if ok:  # subfolders deepest first (Sample/, Screens/, S01/), then the folder itself
                    rows += [("dir", d) for d in sorted((d for d in entry.rglob("*") if d.is_dir()),
                                                        key=lambda d: -len(d.parts))]
                    rows.append(("dir", entry))
                else:  # keep the folder; drop its junk rows, delete only verified dups
                    rows = [r for r in rows if not (r[0] == "junk" and Path(r[1]).is_relative_to(entry))]
    out = write(rows, "duplicates")
    dups = [r for r in rows if r[0] == "dup"]
    dirs = [r for r in rows if r[0] == "dir"]
    junk = [r for r in rows if r[0] == "junk"]
    print(f"manifest: {out}")
    print(f"  {len(dups)} hardlink duplicates (same inode as the library copy; frees ~0 bytes)")
    print(f"  {len(junk)} leftover non-video files ({sum(int(r[2]) for r in junk) / 1e6:.0f} MB: nfo/txt/._/images/samples)")
    print(f"  {len(dirs)} folders removed once empty")
    by_dir = {}
    for r in rows:
        if r[0] in ("dup", "junk"):
            p = Path(r[1])
            top = next((root / p.relative_to(root).parts[0] for root in roots if p.is_relative_to(root)), p.parent)
            by_dir.setdefault(top, [0, 0])[0 if r[0] == "dup" else 1] += 1
    for d, (nd, nj) in sorted(by_dir.items()):
        tag = "folder" if d.is_dir() else "loose "
        print(f"   {tag} {d.relative_to(d.parents[0]) if d.is_file() else d}  ({nd} dup, {nj} junk)")
    for r in dirs:
        if not any(Path(r[1]) == d for d in by_dir):
            print(f"   empty  {r[1]}")
    print(f"KEPT (not hardlinks of a library file, so not deleted): {len(kept)}")
    for f in kept:
        print(f"   {f}  ({f.stat().st_size / 1e9:.2f} GB, {f.stat().st_nlink} link)")


def plan_paths(paths: list[str]) -> None:
    rows = []
    for p in map(Path, paths):
        if p.is_dir():
            rows += [("file", f, f.stat().st_size) for f in sorted(p.rglob("*")) if f.is_file()]
            rows += [("dir", d) for d in sorted((d for d in p.rglob("*") if d.is_dir()), key=lambda d: -len(d.parts))]
            rows.append(("dir", p))
        elif p.is_file():
            rows.append(("file", p, p.stat().st_size))
        else:
            sys.exit(f"not found: {p}")
    out = write(rows, "paths")
    files = [r for r in rows if r[0] == "file"]
    print(f"manifest: {out}")
    print(f"  {len(files)} files, {sum(int(r[2]) for r in files) / 1e9:.2f} GB, "
          f"{len([r for r in rows if r[0] == 'dir'])} folders")
    for r in rows:
        if r[0] == "file":
            st = Path(r[1]).stat()
            print(f"   file {int(r[2]) / 1e9:6.2f} GB  links={st.st_nlink}  {r[1]}")
        else:
            print(f"   dir                     {r[1]}")


def apply(manifest: str) -> None:
    rows = [l.rstrip("\n").split("\t") for l in Path(manifest).read_text().splitlines() if l.strip()]
    log = open(f"{manifest}.log", "a")
    done = skipped = 0

    def note(msg):
        print(msg)
        log.write(f"{time.strftime('%F %T')} {msg}\n")

    for r in rows:
        kind, path = r[0], Path(r[1])
        try:
            if kind == "dup":
                a, b = path.stat(), Path(r[2]).stat()
                if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                    note(f"SKIP not the same inode anymore: {path}")
                    skipped += 1
                    continue
            elif kind in ("file", "junk"):
                if path.stat().st_size != int(r[2]):
                    note(f"SKIP size changed: {path}")
                    skipped += 1
                    continue
            elif kind == "dir":
                left = list(path.iterdir()) if path.exists() else []
                if left:
                    note(f"SKIP folder not empty ({len(left)} left): {path}")
                    skipped += 1
                else:
                    path.rmdir()
                    note(f"removed dir {path}")
                    done += 1
                continue
            path.unlink()
            note(f"deleted {kind} {path}")
            done += 1
        except FileNotFoundError:
            note(f"SKIP already gone: {path}")
            skipped += 1
    note(f"done: {done} removed, {skipped} skipped")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:2] == ["plan", "duplicates"]:
        plan_duplicates()
    elif a[:2] == ["plan", "paths"] and len(a) > 2:
        plan_paths(a[2:])
    elif a[:1] == ["apply"] and len(a) == 2:
        apply(a[1])
    else:
        sys.exit(__doc__)
