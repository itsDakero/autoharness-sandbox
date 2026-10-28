"""Idea box: the admin page writes ideas/<slug>.md into the repo; the build loop (/build-ideas) picks them up.

The repo's ideas/ folder is writable (IDEAS_DIR). Notes are created, never overwritten or deleted: moving notes
to ideas/done/ or ideas/parked/ is scripts/idea.sh's job.

Proposed tab (M6): notes an LLM wrote on its own (the scout, the assistant) wait in ideas/proposed/ until Dan
approves one (moved to ideas/, where the loop picks it up) or dismisses it (moved to ideas/dismissed/, which the
scout reads so it doesn't propose it again). Both moves stay inside IDEAS_DIR, so the dashboard does them itself.

Deploy tab, "Build in a terminal": plans in ideas/terminal/ that write under .claude/, which the background
builder can't do (Claude Code prompts for every write there). Dan builds them with /build-ideas <slug>.

Parked and Deploy tabs: answering, requeueing and deploying need git and docker, which the dashboard doesn't have.
It writes a request into ACTIONS_DIR/requests/ instead; scripts/idea-actions.py (cron as dan, every minute) runs
it, writes results/<id>.json, and keeps status.json (the reviewed builds) up to date.
"""
import logging
import os
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

IDEAS_DIR = Path(os.environ.get("IDEAS_DIR", "/ideas"))
ACTIONS_DIR = Path(os.environ.get("ACTIONS_DIR", "/actions"))
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TITLE_MAX = 100
DETAILS_MAX = 4000
SLUG_MAX = 50
ANSWER_MAX = 8000
REASON_MAX = 300
NOTE_MAX = 40000
RUNNER_STALE = 180   # status.json older than this: the cron runner isn't running
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SECTION = re.compile(r"^## +(.+?)\s*$", re.M)

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NOT_SLUG = re.compile(r"[^a-z0-9]+")
TITLE_LINE = re.compile(r"^#\s+(?:Idea:\s*)?(.+)$", re.M)
REJECTED = re.compile(r"^## +Rejected +(\S+)\s*$(.*)", re.M | re.S)
REASON_LINE = re.compile(r"^Reason: *(.+)$", re.M)
# Score header of a proposed (or scored) note, between the title and the first "## "
HEADER_LINE = re.compile(r"^(Value|Effort|Risk|Score|Source):[ \t]*(.*?)\s*$", re.M)
DEPENDS_LINE = re.compile(r"^Depends on:[ \t]*(\S*)", re.M | re.I)
DEP_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*")
FIRST_INT = re.compile(r"\d+")
LATER_FILE = ".later.json"   # ideas/proposed/: slug -> when Dan pressed Later


log = logging.getLogger("uvicorn.error")


class IdeaError(ValueError):
    pass


def slugify(title: str) -> str:
    slug = NOT_SLUG.sub("-", title.lower()).strip("-")
    return slug[:SLUG_MAX].rstrip("-") or "idea"


def clean(text: str) -> str:
    """Unix newlines, no control characters, no trailing spaces."""
    text = CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def add(title: str, details: str, value: int | None = None, effort: int | None = None,
        research: bool = False) -> dict:
    """value/effort (1-5, optional) go in a score header like the scout's; the score needs both.
    research: "Research: yes" in the header, so the planner checks feasibility and size and parks it first."""
    title = " ".join(clean(title).split())  # one line
    details = clean(details)
    if not title:
        raise IdeaError("A title is required.")
    if len(title) > TITLE_MAX or len(details) > DETAILS_MAX:
        raise IdeaError(f"Keep the title under {TITLE_MAX} and the details under {DETAILS_MAX} characters.")
    if any(v is not None and v not in range(1, 6) for v in (value, effort)):
        raise IdeaError("Value and effort go from 1 to 5.")
    if title.startswith("#"):
        title = title.lstrip("# ") or "Idea"
    base = slugify(title)
    today = datetime.now().strftime("%Y-%m-%d")
    header = "".join(f"{k}: {v}\n" for k, v in (("Value", value), ("Effort", effort)) if v is not None)
    if value is not None and effort is not None:
        header += f"Score: {score(value, effort)}\n"
    if research:
        header += "Research: yes\n"
    if header:
        header += f"Source: dashboard {today}\n\n"
    body = f"{details}\n\n" if details else ""
    note = f"# {title}\n\n{header}{body}_Added from the dashboard, {today}._\n"
    for n in range(1, 100):
        name = f"{base}.md" if n == 1 else f"{base}-{n}.md"
        if _taken(name):
            continue  # filing this one under done/, parked/ or rejected/ later would collide
        try:
            # "x": never overwrite an existing note
            with open(IDEAS_DIR / name, "x", encoding="utf-8") as f:
                f.write(note)
        except FileExistsError:
            continue
        return {"ok": True, "file": name, "title": title}
    raise IdeaError("Too many ideas with that title.")


def _taken(name: str) -> bool:
    """Filing a note called <name> under done/, parked/ or rejected/ later would collide."""
    return any((IDEAS_DIR / sub / name).exists() for sub in ("done", "parked", "rejected", "terminal", "waiting"))


def score(value: int, effort: int) -> int:
    return value * (6 - effort)


def _title(path: Path) -> str:
    try:
        m = TITLE_LINE.search(path.read_text(encoding="utf-8", errors="replace")[:2000])
    except OSError:
        return path.stem
    return m.group(1).strip() if m else path.stem


def _depends_on(text: str) -> str:
    """The slug in the header's "Depends on: <slug> free text" line (header = before the first "## "), or ""."""
    header = SECTION.split(text, maxsplit=1)[0]
    m = DEPENDS_LINE.search(header)
    if not m:
        return ""
    m = DEP_SLUG.match(m.group(1).rstrip(",.)"))
    return m.group(0) if m else ""


def _dep_of(path: Path) -> str:
    try:
        return _depends_on(path.read_text(encoding="utf-8", errors="replace")[:NOTE_MAX])
    except OSError:
        return ""


def _deployed(dep: str) -> bool:
    # The /ideas mount is the main checkout, so done/ there is what is on main
    return (IDEAS_DIR / "done" / f"{dep}.md").exists()


def waiting() -> list[dict]:
    """Notes in ideas/waiting/ (chained ideas): they join the queue once the idea they depend on is deployed."""
    items = []
    for p in (IDEAS_DIR / "waiting").glob("*.md"):
        try:
            dep = _dep_of(p)
            title = _title(p)
            if not dep:
                state = "no-dep"
            elif _deployed(dep):
                state = "ready"
            elif (IDEAS_DIR / "rejected" / f"{dep}.md").exists():
                state = "rejected"
            elif any((IDEAS_DIR / sub / f"{dep}.md").exists() for sub in ("", "waiting", "terminal", "parked")):
                state = "waiting"
            else:
                state = "unknown"  # an unmerged build has no note in these folders either; the dep slug is then a typo
        except OSError:
            dep, title, state = "", p.stem, "no-dep"
        items.append({"file": p.name, "title": title, "on": dep, "state": state})
    items.sort(key=lambda i: i["title"].lower())
    return items


def queue() -> dict:
    """Open ideas, oldest first by file time (the build loop uses the git add date, so the order can differ
    for older notes), how many are done, and the parked ones."""
    if not IDEAS_DIR.is_dir():
        return {"ok": False}
    items = []
    for p in IDEAS_DIR.glob("*.md"):
        st = p.stat()
        dep = _dep_of(p)
        items.append({"file": p.name, "title": _title(p), "added": st.st_mtime,
                      "on": dep if dep and not _deployed(dep) else ""})
    items.sort(key=lambda i: i["added"])
    for i in items:
        i["added"] = datetime.fromtimestamp(i["added"]).astimezone().isoformat(timespec="seconds")
    done = sum(1 for _ in (IDEAS_DIR / "done").glob("*.md")) if (IDEAS_DIR / "done").is_dir() else 0
    # Parked by the build loop (scripts/idea.sh park): waiting for Dan's answers in the note
    parked = sorted(({"file": p.name, "title": _title(p)} for p in (IDEAS_DIR / "parked").glob("*.md")),
                    key=lambda i: i["title"].lower())
    proposed = sum(1 for p in (IDEAS_DIR / "proposed").glob("*.md") if SLUG.match(p.stem))
    return {"ok": True, "ideas": items, "done": done, "parked": parked, "rejected": rejected(), "proposed": proposed,
            "waiting": waiting()}


def rejected() -> list[dict]:
    """Builds Dan rejected on the Deploy tab (scripts/deploy-idea.sh reject), newest first."""
    items = []
    for p in (IDEAS_DIR / "rejected").glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:NOTE_MAX]
        except OSError:
            continue
        m = REJECTED.search(text)
        reason = m and REASON_LINE.search(m.group(2))
        items.append({"file": p.name, "title": _title(p), "date": m.group(1) if m else "",
                      "reason": reason.group(1).strip() if reason else ""})
    items.sort(key=lambda i: (i["date"], i["title"].lower()), reverse=True)
    return items


# ---- Proposed tab ----

def header(text: str) -> dict:
    """The score header (Value/Effort/Risk/Score/Source lines before the first "## "). The score is worked out
    from value and effort when both are there, so a note's own Score line can't push it up the list."""
    m = SECTION.search(text)
    fields = {k.lower(): v for k, v in HEADER_LINE.findall(text[:m.start()] if m else text)}
    out: dict = {"source": fields.get("source", "")}
    for k in ("value", "effort", "risk", "score"):
        n = FIRST_INT.match(fields.get(k, ""))
        out[k] = int(n.group()) if n else None
    if out["value"] in range(1, 6) and out["effort"] in range(1, 6):
        out["score"] = score(out["value"], out["effort"])
    return out


def _later() -> dict[str, float]:
    try:
        data = json.loads((IDEAS_DIR / "proposed" / LATER_FILE).read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, (int, float))} if isinstance(data, dict) else {}


def proposed() -> dict:
    """Proposals, best score first; the ones Dan put off (Later) go to the back, oldest Later first."""
    later, items = _later(), []
    for p in (IDEAS_DIR / "proposed").glob("*.md"):
        if not SLUG.match(p.stem):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:NOTE_MAX]
            mtime = p.stat().st_mtime
        except OSError:
            continue
        sections = {h.lower(): b for h, b in _sections(text) if h}
        items.append({"slug": p.stem, "title": _title(p), "note": text, **header(text),
                      "problem": sections.get("problem", ""), "proposal": sections.get("proposal", ""),
                      "later": later.get(p.stem), "mtime": mtime})
    items.sort(key=lambda i: (i["later"] is not None, i["later"] or 0, -(i["score"] or 0), i["mtime"]))
    dismissed = sum(1 for _ in (IDEAS_DIR / "dismissed").glob("*.md"))
    return {"ok": True, "items": items, "dismissed": dismissed, "runner": "ok", "actions": []}


def decide(action: str, slug: str, reason: str) -> dict:
    """Approve (into the build queue), dismiss (into ideas/dismissed/, with the reason) or put off one proposal."""
    if action not in ("approve", "dismiss", "later") or not SLUG.match(slug):
        raise IdeaError("Unknown action.")
    src = IDEAS_DIR / "proposed" / f"{slug}.md"
    try:
        text = src.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise IdeaError("That proposal isn't here any more.")
    title, today = _title(src), datetime.now().strftime("%Y-%m-%d")
    if action == "later":
        later = {k: v for k, v in _later().items() if (IDEAS_DIR / "proposed" / f"{k}.md").exists()}
        later[slug] = time.time()
        tmp = IDEAS_DIR / "proposed" / f".{LATER_FILE}.tmp"
        tmp.write_text(json.dumps(later))
        os.rename(tmp, IDEAS_DIR / "proposed" / LATER_FILE)
        return {"ok": True, "title": title}
    if action == "approve":
        name = f"{slug}.md"
        if _taken(name):
            raise IdeaError(f"An idea called {slug} was built, parked or rejected before: rename the note first.")
        dest = IDEAS_DIR / name
        text = text.rstrip("\n") + f"\n\n_Approved on the dashboard, {today}._\n"
    else:
        reason = " ".join(clean(reason).split())  # one line in the note
        if len(reason) > REASON_MAX:
            raise IdeaError(f"Keep the reason under {REASON_MAX} characters.")
        text = text.rstrip("\n") + f"\n\n## Dismissed {today}\n\n" + (f"Reason: {reason}\n" if reason else "No reason given.\n")
        (IDEAS_DIR / "dismissed").mkdir(exist_ok=True)
        dest = None
    for n in range(1, 100):
        if action == "dismiss":  # the same slug can be proposed and dismissed again later
            dest = IDEAS_DIR / "dismissed" / (f"{slug}.md" if n == 1 else f"{slug}-{n}.md")
        try:
            with open(dest, "x", encoding="utf-8") as f:  # never overwrite
                f.write(text)
            break
        except FileExistsError:
            if action == "approve":
                raise IdeaError(f"ideas/{slug}.md already exists: approve it after that one is built.")
    else:
        raise IdeaError("Too many dismissed notes with that name.")
    try:
        src.unlink()
    except FileNotFoundError:  # a second click got here first; its copy stays, this one goes
        dest.unlink()
        raise IdeaError("That proposal isn't here any more.")
    return {"ok": True, "title": title, "file": str(dest.relative_to(IDEAS_DIR))}


async def announce(title: str, file: str) -> None:
    """Discord feed post; best effort (the note is already saved). No pings, whatever the title says."""
    if not DISCORD_WEBHOOK_URL.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        return
    body = {"content": f"Idea queued: {title} (ideas/{file})", "allowed_mentions": {"parse": []}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            (await client.post(DISCORD_WEBHOOK_URL, json=body)).raise_for_status()
    except httpx.HTTPError as e:
        # str(e) can include the URL, which holds the webhook token
        log.warning("Discord post failed: %s", type(e).__name__)


# ---- Parked and Deploy tabs ----

def _sections(text: str) -> list[tuple[str, str]]:
    """[(heading, body)] for each "## " section; the text before the first one is ("", ...)."""
    out, last, head = [], 0, ""
    for m in SECTION.finditer(text):
        out.append((head, text[last:m.start()].strip()))
        head, last = m.group(1), m.end()
    out.append((head, text[last:].strip()))
    return out


def _runner() -> dict:
    """status.json from the cron runner, and whether it is fresh."""
    path = ACTIONS_DIR / "status.json"
    try:
        status = json.loads(path.read_text())
        age = time.time() - path.stat().st_mtime
    except (OSError, ValueError):
        return {"runner": "missing", "status": {}}
    return {"runner": "ok" if age < RUNNER_STALE else "stale", "status": status}


def _actions() -> list[dict]:
    """Recent actions, newest first: requests not picked up yet ("queued"), then the runner's results."""
    out = []
    for p in (ACTIONS_DIR / "requests").glob("*.json"):
        try:
            r = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        out.append({"id": p.stem, "action": r.get("action"), "slug": r.get("slug"), "state": "queued"})
    for p in (ACTIONS_DIR / "results").glob("*.json"):
        try:
            r = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        out.append({k: r.get(k) for k in ("id", "action", "slug", "state", "message", "log", "finished")})
    out.sort(key=lambda a: str(a.get("id")), reverse=True)  # ids start with the request time
    return out[:40]


def parked() -> dict:
    """Parked notes, oldest first, with their Questions and any answers given so far."""
    items = []
    for p in (IDEAS_DIR / "parked").glob("*.md"):
        if not SLUG.match(p.stem):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:NOTE_MAX]
            mtime = p.stat().st_mtime
        except OSError:
            continue
        secs = _sections(text)
        questions = [b for h, b in secs if h.lower() == "questions"]
        research = [b for h, b in secs if h.lower() == "research"]
        answers = [{"heading": h, "text": b} for h, b in secs if h.lower().startswith("answers")]
        parked_on = next((h.split(" ", 1)[1] for h, _ in secs if h.lower().startswith("parked ")), "")
        items.append({"slug": p.stem, "title": _title(p), "note": text, "questions": questions[-1] if questions else "",
                      "research": research[-1] if research else "",
                      "answers": answers, "parked": parked_on, "mtime": mtime})
    items.sort(key=lambda i: i["mtime"])
    r = _runner()
    return {"ok": True, "items": items, "runner": r["runner"],
            "actions": [a for a in _actions() if a["action"] in ("answer", "requeue", "reject")]}


def _hand_builds(skip: set) -> list[dict]:
    """Plans waiting in ideas/terminal/ (scripts/idea.sh terminal): they write under .claude/, so Dan builds them
    in a terminal session with /build-ideas <slug>. Skipped once that build has a branch (it's in skip)."""
    items = []
    for p in (IDEAS_DIR / "terminal").glob("*.md"):
        if not SLUG.match(p.stem) or p.stem in skip:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:NOTE_MAX]
            mtime = p.stat().st_mtime
        except OSError:
            continue
        secs = _sections(text)
        last = lambda name: next((b for h, b in reversed(secs) if h.lower() == name), "")
        manual = last("manual steps")
        if manual.lower().rstrip(".") == "none":
            manual = ""
        files = [line[2:].strip() for line in next((b for h, b in reversed(secs)
                                                     if h.lower().startswith("build in a terminal")), "").splitlines()
                 if line.startswith("- ")]
        items.append({"slug": p.stem, "title": _title(p), "kind": "hand", "plan": last("plan"), "manual": manual,
                      "files": files, "note": text,
                      "built": datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds")})
    items.sort(key=lambda i: i["built"])
    return items


def deploys() -> dict:
    r = _runner()
    st = r["status"]
    ready, building = st.get("ready", []), st.get("building", [])
    hand = _hand_builds({b.get("slug") for b in ready} | set(building))
    return {"ok": True, "ready": ready + hand, "building": building,
            "updated": st.get("updated"), "runner": r["runner"],
            "actions": [a for a in _actions() if a["action"] in ("deploy", "reject")]}


def request(action: str, slug: str, text: str, sensitive_ok: bool) -> dict:
    """Queue one action for scripts/idea-actions.py. Reject works on terminal-only builds too (it only
    files the note and drops the branch) and on a parked note (no build at all)."""
    if action not in ("answer", "requeue", "deploy", "reject") or not SLUG.match(slug):
        raise IdeaError("Unknown action.")
    text = clean(text)
    if len(text) > ANSWER_MAX:
        raise IdeaError(f"Keep the answers under {ANSWER_MAX} characters.")
    if any(a["slug"] == slug and a["state"] in ("queued", "running") for a in _actions()):
        raise IdeaError("Already working on this one.")
    if action in ("answer", "requeue"):
        if not (IDEAS_DIR / "parked" / f"{slug}.md").is_file():
            raise IdeaError("That idea isn't parked any more.")
        if action == "answer" and not text:
            raise IdeaError("Type your answers first.")
    elif action == "reject" and (IDEAS_DIR / "parked" / f"{slug}.md").is_file():
        pass  # a parked note: nothing to build or drop
    else:
        build = next((b for b in deploys()["ready"] if b.get("slug") == slug), None)
        if not build:
            raise IdeaError("That build isn't ready to deploy (any more).")
        if action == "deploy" and build.get("kind") == "hand":
            raise IdeaError("Build this one in a terminal first.")
    if action == "reject":
        text = " ".join(text.split())  # one line in the note
        if not text:
            raise IdeaError("Give a short reason first.")
        if len(text) > REASON_MAX:
            raise IdeaError(f"Keep the reason under {REASON_MAX} characters.")
    elif action == "deploy":
        if build.get("terminal"):
            raise IdeaError("This one has to be deployed from a terminal.")
        if build.get("sensitive") and not sensitive_ok:
            raise IdeaError("Confirm the sensitive files first.")
        text = ""
    if _runner()["runner"] == "missing":
        raise IdeaError("The action runner isn't set up: run scripts/install-cron.sh on the server.")
    rid = f"{time.time_ns()}-{action}-{slug}"
    req = ACTIONS_DIR / "requests"
    tmp = req / f".{rid}.tmp"
    tmp.write_text(json.dumps({"action": action, "slug": slug, "text": text, "sensitive_ok": bool(sensitive_ok)}))
    os.rename(tmp, req / f"{rid}.json")  # whole files only: the runner globs *.json
    return {"ok": True, "id": rid}
