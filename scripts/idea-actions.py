#!/usr/bin/env python3
"""Dashboard idea actions: cron as dan, every minute (scripts/install-cron.sh). No root.

The dashboard can't run git or docker, so its Parked and Deploy tabs drop requests into
$APPDATA_PATH/dashboard/actions/requests/. This carries them out, writes results/<id>.json, then writes
status.json (the reviewed builds waiting on idea/<slug> branches) for the Deploy tab.
  answer <slug> text     append "## Answers <date>" to ideas/parked/<slug>.md, commit + push
  requeue <slug> [text]  the same, then move the note back to ideas/, so the loop plans it again
  deploy <slug>          scripts/deploy-idea.sh --yes <slug> (--sensitive-ok after the dashboard's second
                         confirm); builds touching bootstrap.sh, systemd/ or .claude/ are refused there
  reject <slug> reason   scripts/deploy-idea.sh reject <slug> (reason on stdin): drops the build, files the note
                         under ideas/rejected/ with the date and reason, commit + push; also a plan waiting in
                         ideas/terminal/ for a terminal build (the dashboard lists those itself), or a parked
                         note in ideas/parked/ (the Parked tab's Reject; no build to drop)
Request text is only ever written into the note, never run.
Auto-deploy: after the requests, one ready build per run is deployed without a click when its note's header says
Risk 1, it carries the dashboard's "Approved" line, needs no terminal/sensitive confirm/manual step and touches none of
the deploy pipeline files. State: actions/auto-deploy.json; pause: touch actions/auto-deploy.off.
Usage: scripts/idea-actions.py [--status] [--auto-dry-run]
  --status: only rewrite status.json; --auto-dry-run: print what auto-deploy would do, write nothing
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import syslog
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACTIONS = Path(os.environ.get("APPDATA_PATH", "/srv/homelab")) / "dashboard" / "actions"
REQUESTS, RESULTS = ACTIONS / "requests", ACTIONS / "results"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REVIEWED = "Reviewed-by: idea-reviewer"
TITLE_LINE = re.compile(r"^#\s+(?:Idea:\s*)?(.+)$", re.M)
TEXT_MAX = 8000
KEEP_RESULTS = 30
DIFF_MAX = 150_000
NOTE_MAX = 40_000
LOG_MAX = 6000
AUTO_STATE, AUTO_OFF = ACTIONS / "auto-deploy.json", ACTIONS / "auto-deploy.off"
APPROVED = re.compile(r"^_Approved on the dashboard, \d{4}-\d{2}-\d{2}\._$", re.M)
RISK_LINE = re.compile(r"^Risk:[ \t]*(.*?)\s*$", re.M)
RISK_ONE = re.compile(r"^1(?:\s*/\s*5)?(?![\d\-\u2013\u2014.,/])")
SECTION = re.compile(r"^## ", re.M)
# A new env var or a change to the deploy pipeline itself always goes to Dan
AUTO_PROTECTED = re.compile(r"^(\." + "env" + r"\.example|scripts/(deploy-idea\.sh|idea-actions\.py|idea\.sh|install-cron\.sh|cron\.d/.*))$")

os.environ.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
os.environ["GIT_TERMINAL_PROMPT"] = "0"
syslog.openlog("idea-actions")


class Refused(Exception):
    pass


def log(msg: str) -> None:
    syslog.syslog(msg)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        raise Refused(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout


def discord(msg: str) -> None:
    subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], capture_output=True)


def title_of(text: str, fallback: str) -> str:
    m = TITLE_LINE.search(text[:2000])
    return m.group(1).strip() if m else fallback


def write_json(path: Path, data) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


@contextmanager
def git_lock():
    """The lock idea.sh and deploy-idea.sh take: one writer on main at a time."""
    common = Path(git("rev-parse", "--git-common-dir").strip())
    with open((REPO / common) / "homelab-ideas.lock", "w") as f:
        for _ in range(600):
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(1)
        else:
            raise Refused("another idea step (build loop or deploy) held the lock for 10 minutes")
        yield


def on_main() -> None:
    if git("symbolic-ref", "--short", "HEAD", check=False).strip() != "main":
        raise Refused("the repo checkout isn't on main")


def push() -> str:
    """Push main, but only after the secret scan passes on everything not yet pushed."""
    up = subprocess.run(["git", "rev-parse", "--verify", "-q", "@{u}"], cwd=REPO, capture_output=True, text=True)
    base = "@{u}" if up.returncode == 0 else "origin/main"
    scan = subprocess.run([str(REPO / "scripts" / "secret-scan.sh"), str(REPO), f"{base}..HEAD"],
                          cwd=REPO, capture_output=True, text=True)
    if scan.returncode != 0:
        why = "found a possible secret" if scan.returncode == 1 else "couldn't run"
        discord(f"Secret scan {why}; the dashboard's note commit on main was not pushed (see scripts/secret-scan.sh)")
        return " (not pushed: secret scan blocked/couldn't run; committed locally)"
    r = subprocess.run(["git", "push", "-q"], cwd=REPO, capture_output=True, text=True)
    return "" if r.returncode == 0 else " (push failed; committed locally)"


def append_answers(note: Path, text: str) -> None:
    body = note.read_text(encoding="utf-8").rstrip("\n")
    note.write_text(f"{body}\n\n## Answers {datetime.now():%Y-%m-%d}\n\n{text}\n", encoding="utf-8")


def answer(slug: str, text: str, requeue: bool) -> str:
    rel, dest = f"ideas/parked/{slug}.md", f"ideas/{slug}.md"
    note = REPO / rel
    with git_lock():
        on_main()
        if not note.is_file():
            raise Refused(f"{rel} isn't there any more (requeued already?)")
        if requeue and (REPO / dest).exists():
            raise Refused(f"{dest} already exists")
        original = note.read_bytes()
        title = title_of(original.decode(errors="replace"), slug)
        try:
            if text:
                append_answers(note, text)
                git("add", "--", rel)
            if not requeue:
                git("commit", "-q", "-m", f"ideas: answer {slug}", "--", rel)
                return f"Answers saved in {rel}{push()}"
            if git("ls-files", "--", rel).strip():
                git("mv", "--", rel, dest)
                paths = [rel, dest]
            else:
                (REPO / dest).write_bytes(note.read_bytes())
                note.unlink()
                git("add", "--", dest)
                paths = [dest]
            git("commit", "-q", "-m", f"ideas: requeue {slug}", "--", *paths)
        except Exception:
            # Put main back as it was: a half-done move or a staged note would block the next deploy
            git("reset", "-q", "--", rel, check=False)
            if requeue:
                git("rm", "-q", "--cached", "--ignore-unmatch", "--", dest, check=False)
                (REPO / dest).unlink(missing_ok=True)
            note.write_bytes(original)
            raise
        result = f"Requeued as {dest}; the build loop plans it on its next pass{push()}"
    discord(f"Requeued: {title}" + (" (answers in the note)" if text else ""))
    return result


def deploy(slug: str, sensitive_ok: bool) -> tuple[str, str]:
    cmd = [str(REPO / "scripts" / "deploy-idea.sh"), "--yes"]
    if sensitive_ok:
        cmd.append("--sensitive-ok")
    try:
        r = subprocess.run(cmd + [slug], cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        raise Refused("deploy-idea.sh took over 20 minutes and was stopped; check the repo in a terminal")
    out = r.stdout[-LOG_MAX:]
    if r.returncode:
        last = [line for line in out.splitlines() if line.strip()][-1:] or ["failed"]
        raise Refused(last[0].removeprefix("deploy-idea: "), out)
    return f"Deployed {slug}", out


def reject(slug: str, reason: str) -> tuple[str, str]:
    r = subprocess.run([str(REPO / "scripts" / "deploy-idea.sh"), "reject", slug], cwd=REPO, input=reason,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    out = r.stdout[-LOG_MAX:]
    if r.returncode:
        last = [line for line in out.splitlines() if line.strip()][-1:] or ["failed"]
        raise Refused(last[0].removeprefix("deploy-idea: "), out)
    return f"Rejected {slug}", out


def run(req_path: Path) -> str:
    """Run one request; return the slug of a deploy/reject request (whatever its result), else ""."""
    rid = req_path.stem
    result = {"id": rid, "action": "", "slug": "", "state": "running", "message": "", "log": "",
              "started": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        raw = req_path.read_bytes()
        req = json.loads(raw) if len(raw) <= 65536 else {}
    except (OSError, ValueError):
        req = {}
    req_path.unlink(missing_ok=True)
    if not isinstance(req, dict):
        req = {}
    action, slug, text = req.get("action"), req.get("slug"), req.get("text") or ""
    result.update(action=str(action)[:20], slug=str(slug)[:64])
    out_path = RESULTS / f"{rid}.json"
    write_json(out_path, result)
    try:
        if action not in ("answer", "requeue", "deploy", "reject") or not isinstance(slug, str) or not SLUG.match(slug):
            raise Refused("bad request")
        if not isinstance(text, str) or len(text) > TEXT_MAX:
            raise Refused("answer text too long")
        text = text.replace("\r\n", "\n").strip()
        if action == "deploy":
            result["message"], result["log"] = deploy(slug, req.get("sensitive_ok") is True)
        elif action == "reject":
            if not text:
                raise Refused("no reason given")
            result["message"], result["log"] = reject(slug, text)
        else:
            if action == "answer" and not text:
                raise Refused("no answers given")
            result["message"] = answer(slug, text, requeue=action == "requeue")
        result["state"] = "done"
    except Refused as e:
        result["state"], result["message"] = "failed", str(e.args[0])
        if len(e.args) > 1:
            result["log"] = e.args[1]
    except Exception as e:  # keep going with the other requests
        result["state"], result["message"] = "failed", f"{type(e).__name__}: {e}"
    result["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_json(out_path, result)
    log(f"{action} {slug}: {result['state']}: {result['message']}")
    return slug if action in ("deploy", "reject") and isinstance(slug, str) else ""


def build_info(slug: str) -> dict:
    branch = f"idea/{slug}"
    note = git("show", f"{branch}:ideas/done/{slug}.md", check=False)
    files = [f for f in git("diff", "--name-only", f"main...{branch}").splitlines() if f]
    check = subprocess.run([str(REPO / "scripts" / "deploy-idea.sh"), "check", slug], cwd=REPO,
                           capture_output=True, text=True).stdout.splitlines()
    terminal = [line.split(" ", 1)[1] for line in check if line.startswith("terminal ")]
    sensitive = [line.split(" ", 1)[1] for line in check if line.startswith("sensitive ")]
    m = re.search(r"^## Manual steps\s*\n(.*?)(?=^## |\Z)", note, re.M | re.S)
    manual = m.group(1).strip() if m else ""
    if manual.lower().rstrip(".") == "none":
        manual = ""
    diff = git("diff", f"main...{branch}")
    after = ["sudo ./bootstrap.sh"] if any(re.match(r"^(bootstrap\.sh|systemd/)", f) for f in files) else []
    return {
        "slug": slug,
        "title": title_of(note, slug),
        "commits": git("log", "--format=%h %s", f"main..{branch}").splitlines(),
        "diffstat": git("diff", "--stat", f"main...{branch}").rstrip(),
        "files": files,
        "terminal": terminal,
        "sensitive": sensitive,
        "manual": manual,
        "note": note[:NOTE_MAX],
        "diff": diff[:DIFF_MAX],
        "diff_truncated": len(diff) > DIFF_MAX,
        "command": f"cd {REPO} && scripts/deploy-idea.sh {slug}",
        "after": after,
        "built": git("log", "-1", "--format=%cI", branch).strip(),
    }


def write_status() -> None:
    ready, building = [], []
    for ref in git("for-each-ref", "--format=%(refname:short)", "refs/heads/idea/").split():
        slug = ref.removeprefix("idea/")
        if not SLUG.match(slug):
            continue
        if REVIEWED in git("log", f"main..{ref}", "--format=%B", check=False).splitlines():
            try:
                ready.append(build_info(slug))
            except Refused as e:
                log(f"status {slug}: {e}")
        else:
            building.append(slug)
    ready.sort(key=lambda b: b["built"])
    write_json(ACTIONS / "status.json", {"updated": datetime.now().astimezone().isoformat(timespec="seconds"),
                                         "ready": ready, "building": building})


def reviewed_slugs() -> list[str]:
    out = []
    for ref in git("for-each-ref", "--format=%(refname:short)", "refs/heads/idea/").split():
        slug = ref.removeprefix("idea/")
        if SLUG.match(slug) and REVIEWED in git("log", f"main..{ref}", "--format=%B", check=False).splitlines():
            out.append(slug)
    return out


def auto_state() -> dict:
    try:
        data = json.loads(AUTO_STATE.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def auto_skip_reason(info: dict, tip: str, state: dict) -> str:
    """The first auto-deploy rule a ready build fails, or "" when it is eligible."""
    note = info["note"]
    m = SECTION.search(note)
    risk = RISK_LINE.search(note[:m.start()] if m else note)
    if not risk:
        return "no Risk line in the header"
    if not RISK_ONE.match(risk.group(1)):
        return f"Risk is not 1 ({risk.group(1)[:20]})"
    if not APPROVED.search(note):
        return "not approved on the dashboard"
    if info["terminal"] or info["sensitive"]:
        return "needs a terminal or a sensitive-file confirm"
    if info["manual"]:
        return "has manual steps"
    if any(AUTO_PROTECTED.match(f) for f in info["files"]):
        return "touches the env template or the deploy pipeline"
    if state.get(info["slug"], {}).get("sha") == tip:
        return "this commit was already tried"
    return ""


def auto_deploy(dry_run: bool = False, skip: frozenset | set = frozenset()) -> None:
    if AUTO_OFF.exists():
        log("auto-deploy paused (auto-deploy.off)")
        if dry_run:
            print("paused (auto-deploy.off exists)")
        return
    state = auto_state()
    builds = []
    for slug in reviewed_slugs():
        try:
            info = build_info(slug)
            tip = git("rev-parse", f"idea/{slug}").strip()
        except Refused as e:
            log(f"auto-deploy {slug}: {e}")
            continue
        builds.append((info, tip))
    builds.sort(key=lambda b: b[0]["built"])
    if dry_run:
        for info, tip in builds:
            why = auto_skip_reason(info, tip, state)
            print(f"{info['slug']} " + (f"skip: {why}" if why else "eligible"))
        return
    # Forget branches that are gone
    live = set(git("for-each-ref", "--format=%(refname:short)", "refs/heads/idea/").split())
    kept = {k: v for k, v in state.items() if f"idea/{k}" in live}
    if kept != state:
        state = kept
        write_json(AUTO_STATE, state)
    for info, tip in builds:
        if info["slug"] in skip:  # Dan's button deploy/reject this pass: leave it to him, even if it failed
            continue
        if auto_skip_reason(info, tip, state):
            continue
        slug, title = info["slug"], info["title"]
        # Record the commit first: a crash or a failure must not retry every minute
        state[slug] = {"sha": tip, "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "result": "failed", "message": "started; no result recorded"}
        write_json(AUTO_STATE, state)
        discord(f"Auto-deploying (Risk 1): {title}")
        rid = f"auto-{slug}-{int(time.time())}"
        result = {"id": rid, "action": "deploy", "slug": slug, "state": "running", "message": "", "log": "",
                  "started": state[slug]["at"]}
        write_json(RESULTS / f"{rid}.json", result)
        try:
            result["message"], result["log"] = deploy(slug, sensitive_ok=False)
            result["state"] = "done"
        except Refused as e:
            result["state"], result["message"] = "failed", str(e.args[0])
            if len(e.args) > 1:
                result["log"] = e.args[1]
        except Exception as e:
            result["state"], result["message"] = "failed", f"{type(e).__name__}: {e}"
        result["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write_json(RESULTS / f"{rid}.json", result)
        state[slug].update(result="done" if result["state"] == "done" else "failed",
                           message=result["message"][:300], at=result["finished"])
        write_json(AUTO_STATE, state)
        log(f"auto-deploy {slug}: {result['state']}: {result['message']}")
        if result["state"] != "done":
            discord(f"Auto-deploy failed: {title} ({result['message'][:200]}); it's on the Deploy tab")
        return  # one per run


def prune_results() -> None:
    old = sorted(RESULTS.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-KEEP_RESULTS]
    for p in old:
        p.unlink(missing_ok=True)


def main() -> None:
    if "--auto-dry-run" in sys.argv[1:]:
        auto_deploy(dry_run=True)  # writes nothing: no mkdir, no lock, no state
        return
    REQUESTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    with open(ACTIONS / ".runner.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # last minute's run is still going (a deploy can take a few minutes)
        if "--status" not in sys.argv[1:]:
            # Recover results left "running" by a run that died (the runner lock is free now)
            for p in RESULTS.glob("*.json"):
                try:
                    r = json.loads(p.read_text())
                except (OSError, ValueError):
                    continue
                if r.get("state") == "running":
                    r.update(state="failed", message="interrupted; check the repo in a terminal")
                    write_json(p, r)
            handled = set()
            for req in sorted(REQUESTS.glob("*.json")):
                handled.add(run(req))
            handled.discard("")
            try:
                auto_deploy(skip=handled)
            except Exception as e:  # never keep status.json from being written
                log(f"auto-deploy: {type(e).__name__}: {e}")
            prune_results()
        write_status()


if __name__ == "__main__":
    main()
