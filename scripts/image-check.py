#!/usr/bin/env python3
"""Cron (Mondays 09:10, user dan): weekly digest of newer image tags for the pinned compose images.

Read-only: no container, no Docker socket. Reads the pinned `image:` lines of the tracked *compose.yaml
files (not templates/, not locally built homelab/*), asks Docker Hub / GHCR for newer tags (same queries
and rules as .claude/skills/update-stack/SKILL.md step 1) and posts ONE digest to Discord
(scripts/discord.sh). A pending release whose GitHub release notes mention security / CVE / GHSA also goes
to ntfy (high priority), once per image:tag. Applying upgrades stays with /update-stack.

Flavour rule: skeleton = the tag with every digit run replaced by N; a candidate must have the same
skeleton as the current tag (keeps `v`, `-rootless`, `-lsN`; drops latest, 12, rc, beta, develop-*).
HOLDS (below) pin a line on purpose (Omada 6.2.x, AutoKuma 2.x): listed as "held", not pending.
GitHub allows 60 unauthenticated requests/hour: ETag cache in ~/.cache/homelab/image-check.json
(a 304 is free); on a rate limit the run stops GitHub lookups and says so.

Logs to syslog (journalctl -t image-check).

  scripts/image-check.py                      # Discord digest + ntfy (what cron runs)
  scripts/image-check.py --print              # print the digest only: no Discord, no ntfy, "alerted" kept
  scripts/image-check.py [--print] omada ...  # only these services
  scripts/image-check.py --propose            # also write one Risk 1 note per strict-semver patch bump
                                              # to ideas/proposed/ (cron); with --print: show, write nothing

--propose: a ref gets a note only when current and newest tag both fully match vN.N.N[-suffix] (semver: no
leading zeros, so zero-padded dates like 2024.01.15 never match) with the same
prefix/suffix, same major.minor and a higher patch; no compose file under core/; not gluetun (PROPOSE_SKIP);
not in HOLDS; no inline `#` comment on its image line; not proposed before (ideas/, proposed, done, parked,
rejected, terminal, dismissed incl. -N) and no bump-<service>-* note still pending. Only the strictly
matched tags go into a note. Dan still has to Approve it on the Proposed tab; auto-deploy takes it from there.
"""
import json
import os
import re
import subprocess
import sys
import syslog
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache" / "homelab" / "image-check.json"
NTFY = "http://localhost:8081"
TIMEOUT = 15
DISCORD_MAX = 1900

# service: (regex the candidate tag must match, reason)
HOLDS = {
    "omada": (r"^6\.2\.", "stay on 6.2.x (docs/m3-omada.md)"),
    "autokuma": (r"^2\.", "major must match Uptime Kuma 2.x"),
}
# image repo -> GitHub repo (release notes for the security check)
GITHUB = {
    "adguard/adguardhome": "AdguardTeam/AdGuardHome",
    "tecnativa/docker-socket-proxy": "Tecnativa/docker-socket-proxy",
    "dockurr/samba": "dockur/samba",
    "binwiederhier/ntfy": "binwiederhier/ntfy",
    "traefik": "traefik/traefik",
    "louislam/uptime-kuma": "louislam/uptime-kuma",
    "bigboot/autokuma": "BigBoot/AutoKuma",
    "linuxserver/prowlarr": "Prowlarr/Prowlarr",
    "linuxserver/radarr": "Radarr/Radarr",
    "linuxserver/sonarr": "Sonarr/Sonarr",
    "qmcgaw/gluetun": "qdm12/gluetun",
    "seerr-team/seerr": "seerr-team/seerr",
    "dgtlmoon/changedetection.io": "dgtlmoon/changedetection.io",
    "amir20/dozzle": "amir20/dozzle",
    "analogj/scrutiny": "AnalogJ/scrutiny",
    "nousresearch/hermes-agent": "NousResearch/hermes-agent",
}
# services never proposed (besides core/ and HOLDS)
PROPOSE_SKIP = {"gluetun"}
SEMVER = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[a-z][a-z0-9-]*)?$")  # no leading zeros
IDEAS = REPO / "ideas"
IDEA_DIRS = ("proposed", "done", "parked", "rejected", "terminal")
SECURITY = re.compile(r"(?i)security|CVE-\d|GHSA-")
TTY = sys.stdout.isatty()


class RateLimited(Exception):
    pass


def log(msg: str) -> None:
    syslog.syslog(msg)
    if TTY:
        print(msg)


def env() -> dict:
    out = {}
    try:
        for line in (REPO / ".env").read_text().splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if m:
                out[m[1]] = m[2].strip().strip("'\"")
    except OSError:
        pass
    return out


def http_json(url: str, headers=None):
    """GET -> (status, parsed JSON, response headers). Raises on network/HTTP/JSON errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "homelab-image-check", **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read().decode()), r.headers


def reason(e: Exception) -> str:
    if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError):
        return str(e)
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, json.JSONDecodeError):
        return "not JSON"
    if isinstance(e, TimeoutError) or "timed out" in str(e):
        return "timeout"
    return type(e).__name__


# ---------- images ----------
def read_images():
    """{image ref: {"svcs": [services], "files": [repo-relative compose files], "commented": bool}}
    from the tracked compose files; commented = an `image:` line of the ref has an inline # comment."""
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "*compose.yaml"],
                           capture_output=True, text=True, check=True).stdout.split()
    images: dict = {}
    for f in files:
        if f.startswith("templates/"):
            continue
        svc = None
        for line in (REPO / f).read_text().splitlines():
            m = re.match(r"^  ([a-z0-9-]+):\s*$", line)
            if m:
                svc = m[1]
                continue
            m = re.match(r"^\s*image:\s*(\S+)", line)
            if m and svc:
                ref = m[1].split("#")[0].strip().strip("'\"")
                if ref.startswith("homelab/"):
                    continue
                e = images.setdefault(ref, {"svcs": [], "files": [], "commented": False})
                if svc not in e["svcs"]:
                    e["svcs"].append(svc)
                if f not in e["files"]:
                    e["files"].append(f)
                if "#" in line.split("image:", 1)[1]:
                    e["commented"] = True
    return {r: {**e, "svcs": sorted(e["svcs"]), "files": sorted(e["files"])} for r, e in images.items()}


def split_ref(ref: str):
    """-> (name, tag); drops a trailing @sha256 digest and a docker.io/ (+ library/) prefix."""
    name, _, tag = ref.split("@", 1)[0].rpartition(":")
    if name.startswith("docker.io/"):
        name = name[len("docker.io/"):]
        if name.startswith("library/"):
            name = name[len("library/"):]
    return name, tag


def skeleton(tag: str) -> str:
    return re.sub(r"\d+", "N", tag)


def nums(tag: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def upstream(tag: str) -> str:
    """The app version in a tag: its first dotted number run (v1.2.3, version-1.2.3, 1.2.3-ls12 -> 1.2.3)."""
    m = re.search(r"\d+(?:\.\d+)*", tag)
    return m[0] if m else ""


def kind(cur: tuple, new: tuple) -> str:
    for i, label in enumerate(("major", "minor", "patch")):
        a = cur[i] if i < len(cur) else 0
        b = new[i] if i < len(new) else 0
        if a != b:
            return label
    return "build"


# ---------- patch proposals ----------
def is_patch_bump(cur: str, new: str) -> bool:
    """True only when both tags fully match the strict semver shape, share the v prefix and suffix,
    have the same major.minor and the new patch is higher."""
    a, b = SEMVER.fullmatch(cur), SEMVER.fullmatch(new)
    if not a or not b:
        return False
    if cur.startswith("v") != new.startswith("v") or a[4] != b[4]:
        return False
    return (a[1], a[2]) == (b[1], b[2]) and int(b[3]) > int(a[3])


def bump_slug(svc: str, tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"bump-{svc}-{tag}".lower()).strip("-")[:50].strip("-")


def seen_before(slug: str) -> bool:
    for d in ("", *IDEA_DIRS):
        if (IDEAS / d / f"{slug}.md").exists():
            return True
    dis = IDEAS / "dismissed"
    return (dis / f"{slug}.md").exists() or any(re.fullmatch(re.escape(slug) + r"-\d+\.md", p.name)
                                                for p in dis.glob(f"{slug}*.md"))


def pending_for(svc: str) -> bool:
    prefix = re.sub(r"[^a-z0-9]+", "-", f"bump-{svc}-".lower())
    return any(p.is_file() for d in ("", "proposed") for p in (IDEAS / d).glob(f"{prefix}*.md"))


def registry_url(ref: str) -> str:
    name, _ = split_ref(ref)
    if name.startswith("ghcr.io/"):
        owner, _, pkg = name[len("ghcr.io/"):].partition("/")
        return f"https://github.com/{owner}/{pkg.split('/')[0]}/pkgs/container/{pkg.replace('/', '%2F')}"
    ns, repo = name.split("/", 1) if "/" in name else ("_", name)
    return f"https://hub.docker.com/{'_' if ns == '_' else 'r/' + ns}/{repo}" + ("" if ns == "_" else "/tags")


def proposal_text(ref, svcs, files, cur, new, lname, sec) -> str:
    notes = f"https://github.com/{GITHUB[lname]}/releases" if lname in GITHUB else registry_url(ref)
    sec = [t for t in sec if SEMVER.fullmatch(t)]
    secline = f" Release notes mention security: {', '.join(sec)}." if sec else ""
    major, minor = SEMVER.fullmatch(new)[1], SEMVER.fullmatch(new)[2]
    quoted = ", ".join(f"`{f}`" for f in files)
    return "\n".join([
        f"# Bump {' + '.join(svcs)} to {new} (patch)", "",
        "Value: 2   (patch release: bug and security fixes)",
        "Effort: 1  (one image tag)",
        f"Risk: 1    (patch bump within {major}.{minor}, same tag flavour)",
        "Score: 10",
        f"Source: image-check {date.today().isoformat()}", "",
        "## Problem",
        f"{quoted} pin `{ref}`; `{new}` is out (patch).{secline}", "",
        "## Proposal",
        *[f"- In `{f}`, change only the `image:` tag `{cur}` -> `{new}`; nothing else." for f in files],
        f"- Release notes: {notes}",
        "- Check: " + "; ".join(f"scripts/dc.sh {os.path.dirname(f)} config -q" for f in files) + ". No manual steps.",
        ""])


def write_proposal(slug: str, text: str) -> bool:
    d = IDEAS / "proposed"
    tmp = d / f".{slug}.tmp"
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text)
        os.replace(tmp, d / f"{slug}.md")
    except OSError as e:
        log(f"proposal {slug} not written: {e}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    log(f"proposal written: {slug}")
    return True


# ---------- registries ----------
def hub_tags(name: str, cur_tag: str):
    ns, repo = name.split("/", 1) if "/" in name else ("library", name)
    url = f"https://hub.docker.com/v2/repositories/{ns}/{repo}/tags?page_size=100&ordering=last_updated"
    sk = skeleton(cur_tag)
    tags: list = []
    for _ in range(2):
        _, data, _h = http_json(url)
        tags += [t["name"] for t in data.get("results", [])]
        if any(skeleton(t) == sk for t in tags) or not data.get("next"):
            break
        url = data["next"]
    return tags


def ghcr_tags(path: str):
    _, tok, _h = http_json(f"https://ghcr.io/token?scope=repository:{path}:pull")
    _, data, _h = http_json(f"https://ghcr.io/v2/{path}/tags/list?n=10000",
                            {"Authorization": f"Bearer {tok['token']}"})
    return data.get("tags") or []


def candidates(ref: str):
    name, cur = split_ref(ref)
    if name.startswith("ghcr.io/"):
        name = name[len("ghcr.io/"):]
        tags = ghcr_tags(name)
    else:
        tags = hub_tags(name, cur)
    sk, curn = skeleton(cur), nums(cur)
    same = [t for t in tags if skeleton(t) == sk]
    if not same:
        raise ValueError("no tags of the current flavour")
    return name.lower(), sorted((t for t in set(same) if nums(t) > curn), key=nums)


# ---------- GitHub notes ----------
class GitHub:
    def __init__(self, cache: dict):
        self.cache = cache["github"]
        self.limited = False

    def releases(self, repo: str):
        """Cached/fresh releases [{tag, pre, sec}]; raises RateLimited or another error."""
        ent = self.cache.get(repo)
        ent = ent if isinstance(ent, dict) else {}
        if self.limited:
            if ent.get("releases") is not None:
                return ent["releases"]
            raise RateLimited()
        hdr = {"Accept": "application/vnd.github+json"}
        if ent.get("etag"):
            hdr["If-None-Match"] = ent["etag"]
        try:
            _, data, h = http_json(f"https://api.github.com/repos/{repo}/releases?per_page=30", hdr)
        except urllib.error.HTTPError as e:
            if e.code == 304 and ent.get("releases") is not None:
                return ent["releases"]
            if e.code == 429 or (e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0"):
                self.limited = True
                if ent.get("releases") is not None:
                    return ent["releases"]
                raise RateLimited()
            raise
        rels = [{"tag": r.get("tag_name", ""), "pre": bool(r.get("prerelease")),
                 "sec": bool(SECURITY.search(r.get("body") or ""))} for r in data]
        self.cache[repo] = {"etag": h.get("ETag"), "releases": rels}
        return rels


def security_tags(gh: GitHub, name: str, cur: str, cand: str):
    """-> (security release tags between current and candidate, note); note says why not checked."""
    repo = GITHUB.get(name)
    if not repo:
        return [], "notes not checked"
    lo, hi = nums(upstream(cur)), nums(upstream(cand))
    if lo == hi:
        return [], ""
    try:
        rels = gh.releases(repo)
    except RateLimited:
        return [], "notes not checked (GitHub rate limit)"
    except Exception as e:
        return [], f"notes not checked ({reason(e)})"
    return [r["tag"] for r in rels if not r["pre"] and r["sec"] and lo < nums(r["tag"]) <= hi], ""


# ---------- cache / output ----------
def load_cache() -> dict:
    try:
        c = json.loads(CACHE.read_text())
        if not isinstance(c, dict):
            raise ValueError("bad cache")
    except Exception:
        c = {}
    if not isinstance(c.get("github"), dict):
        c["github"] = {}
    if not isinstance(c.get("alerted"), list):
        c["alerted"] = []
    return c


def save_cache(c: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(c))
        os.replace(tmp, CACHE)
    except OSError as e:
        log(f"cache not written: {e}")


def chunks(text: str):
    cur = ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > DISCORD_MAX:
            yield cur
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        yield cur


def ntfy(topic: str, title: str, body: str) -> bool:
    req = urllib.request.Request(f"{NTFY}/{topic}", data=body.encode(), method="POST",
                                 headers={"Title": title, "Priority": "high", "Tags": "warning"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except Exception:
        log("ntfy post failed")
        return False


def main() -> int:
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    printing = "--print" in args
    propose = "--propose" in args
    only = [a for a in args if not a.startswith("--")]
    images = read_images()
    if only:
        images = {r: e for r, e in images.items() if any(x in e["svcs"] for x in only)}
        if not images:
            print("no such service: " + " ".join(only), file=sys.stderr)
            return 2

    cache = load_cache()
    gh = GitHub(cache)
    pending, held, failed, secure = [], [], [], []
    current = 0
    written = 0
    for ref, info in sorted(images.items(), key=lambda kv: kv[1]["svcs"][0]):
        svcs = info["svcs"]
        label = "+".join(svcs)
        _, cur = split_ref(ref)
        try:
            lname, cands = candidates(ref)
        except Exception as e:
            failed.append(f"couldn't check: {label} {ref} ({reason(e)})")
            log(f"check failed: {ref}: {reason(e)}")
            continue
        hold = next((HOLDS[s] for s in svcs if s in HOLDS), None)
        ok = cands
        if hold:
            ok = [t for t in cands if re.search(hold[0], t)]
            bad = [t for t in cands if not re.search(hold[0], t)]
            if bad:
                held.append(f"held: {label} {bad[-1]} ({hold[1]})")
        if not ok:
            current += 1
            continue
        cand = ok[-1]
        sec, note = security_tags(gh, lname, cur, cand)
        todo = f"/update-stack {svcs[0]}"
        slug = None
        if (propose and not hold and is_patch_bump(cur, cand) and not info["commented"]
                and not any(f.startswith("core/") for f in info["files"])
                and not any(s in PROPOSE_SKIP for s in svcs)
                and not (lname in GITHUB and note)):
            try:
                cand_slug = bump_slug(svcs[0], cand)
                if pending_for(svcs[0]):
                    todo += " [proposal pending]"
                elif not seen_before(cand_slug):
                    slug = cand_slug
            except OSError as e:
                log(f"proposal check failed: {ref}: {e}")
        if slug:
            text = proposal_text(ref, svcs, info["files"], cur, cand, lname, sec)
            if printing:
                print(f"--- would write ideas/proposed/{slug}.md\n{text}")
                written += 1
                todo = f"proposed ({slug})"
            elif write_proposal(slug, text):
                written += 1
                todo = f"proposed ({slug})"
        line = (f"{label}: {cur} -> {cand} ({kind(nums(cur), nums(cand))})"
                f"{' SECURITY' if sec else ''} - {todo}")
        if note:
            line += f" [{note}]"
        pending.append(line)
        if sec:
            secure.append((lname, svcs[0], cur, cand, sec))

    total = len(images)
    today = date.today().isoformat()
    if not pending and not failed:
        head = f"Image check {today}: all {total} images current ({len(held)} held)"
    else:
        head = (f"Image check {today}: {len(pending)} pending, {current} current, "
                f"{len(held)} held, {len(failed)} not checked")
    extra = []
    if propose:
        extra = [f"{written} patch proposals {'would be written' if printing else 'written'}"]
    msg = "\n".join([head, *pending, *held, *failed, *extra])
    log(f"run: {total} images, {len(pending)} pending, {len(held)} held, {len(failed)} failed")
    exit_code = 1 if failed and len(failed) == total else 0

    if printing:
        print(msg)
        for lname, svc, cur, cand, sec in secure:
            if f"{lname}:{cand}" not in cache["alerted"]:
                print(f"(would ntfy: Security update: {svc} {cur} -> {cand}, {', '.join(sec)})")
        save_cache(cache)
        return exit_code

    topic = env().get("NTFY_ALERT_TOPIC")
    for lname, svc, cur, cand, sec in secure:
        key = f"{lname}:{cand}"
        if key in cache["alerted"]:
            continue
        if not topic:
            log("NTFY_ALERT_TOPIC not set: no security notification")
            break
        if ntfy(topic, f"Security update: {svc}",
                f"{cur} -> {cand}\nSecurity notes in: {', '.join(sec)}\n/update-stack {svc}"):
            cache["alerted"].append(key)
    save_cache(cache)
    for part in chunks(msg):
        r = subprocess.run([str(REPO / "scripts" / "discord.sh"), part], capture_output=True)
        if r.returncode:
            log("discord post failed")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
