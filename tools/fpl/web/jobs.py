"""Cron jobs: python -m web.jobs <solve|deadline|teams|players>.
stdout = the Discord text only (scripts/fpl-web-job.sh posts it); everything else is one line on stderr.
Exit 0 for "nothing to do" (no data, no team id, already running), 1 for a failure."""
import datetime as dt
import sys
import time

from collector import store

from . import data, projections as pj, solve, squad

URL = "http://192.168.0.210:8092/"
STALE = dt.timedelta(hours=12)
WAIT_SECS = 600


def log(msg):
    print(f"fpl-web: {msg}", file=sys.stderr)


def moves_text(step, fts):
    outs, ins = step.get("out", []), step.get("in", [])
    if not outs and not ins:
        return f"roll, {fts if fts is not None else '?'} FTs"
    if len(outs) == len(ins):
        return ", ".join(f"{o} -> {i}" for o, i in zip(outs, ins))
    return f"OUT {', '.join(outs) or '-'}; IN {', '.join(ins) or '-'}"


def deadline_line(gw, deadline_local, step, fts, source, failure=None):
    head = f"FPL GW{gw} (deadline {deadline_local.strftime('%a %H:%M')})"
    if failure:
        return f"{head}: solver failed ({failure}), no plan; {URL}"
    cap = step.get("captain") or "?"
    vice = step.get("vice") or "?"
    return (f"{head}: {moves_text(step, fts)}; captain {cap} (vice {vice}); chip {step.get('chip') or 'none'}; "
            f"source {source}; {URL}")


def plan_is_fresh(latest, next_gw, now):
    lr = latest.get("last_run") or {}
    if not lr.get("ok") or not latest.get("plan"):
        return False
    try:
        at = dt.datetime.fromisoformat(latest["plan_at"])
    except (KeyError, ValueError):
        return False
    return now - at <= STALE and latest.get("plan_next_gw") == next_gw


def job_solve():
    try:
        rec = solve.locked_solve()
    except solve.NoData as e:
        log(str(e))
        return 0
    except solve.SolveError as e:
        log(f"solve FAILED: {e}")
        return 1
    if rec is None:
        log("solve already running")
        return 0
    log("solve ok")
    return 0


def job_deadline():
    inp = data.load_inputs()
    if inp is None:
        log("no data")
        return 0
    if squad.team_id() is None:
        log("no FPL_TEAM_ID")
        return 0
    now = data.utcnow()
    ev = next((e for e in inp["events"] if e["id"] == inp["next_gw"]), None)
    if ev is None:
        log("no data")
        return 0
    gw = int(ev["id"])
    deadline = data.parse_deadline(ev)
    state = data.read_state()
    if not pj.deadline_due(deadline, now, state.get("sent_gw"), gw):
        return 0
    latest = solve.read_latest()
    failure = None
    if not plan_is_fresh(latest, gw, now):
        try:
            rec = solve.locked_solve()
            if rec is None:  # a button / cron solve is running: wait for it, then use its result
                end = time.time() + WAIT_SECS
                while solve.running_since() and time.time() < end:
                    time.sleep(10)
            latest = solve.read_latest()
        except solve.NoData as e:
            log(str(e))
            return 0
        except solve.SolveError as e:
            failure = str(e)
            latest = solve.read_latest()
        if not failure and not plan_is_fresh(latest, gw, now):
            failure = (latest.get("last_run") or {}).get("error") or "no fresh plan"
    step = (latest.get("plan") or {}).get(str(gw))
    if not failure and step is None:
        failure = f"plan has no GW{gw}"
    line = deadline_line(gw, deadline.astimezone(), step or {}, latest.get("plan_fts"),
                         latest.get("plan_source", "?"), failure)
    print(line)
    sent = [g for g in (state.get("sent_gw") or []) if isinstance(g, int)] + [gw]
    data.update_state(sent_gw=sent[-10:])
    return 0


def job_teams():
    from model import teams
    res = teams.run()
    if res["unmapped"]:
        log("teams: unmapped odds names (fell back to ratings): " + ", ".join(res["unmapped"]))
    if res["status"] != "ok":
        log(f"teams: {res['msg']}")
    return 0


def job_players():
    from model import players
    res = players.run()
    if res["status"] != "ok":
        log(f"players: {res['status']}: {res['msg']}")
    elif res["unmapped_vaastav"]:
        log(f"players: {res['unmapped_vaastav']} vaastav name(s) not matched to a current player (no last-season log)")
    return 0


def main(argv):
    store.ensure_dirs()
    job = argv[1] if len(argv) > 1 else ""
    try:
        if job == "solve":
            return job_solve()
        if job == "deadline":
            return job_deadline()
        if job == "teams":
            return job_teams()
        if job == "players":
            return job_players()
    except Exception as e:  # last resort: one stderr line, no traceback
        log(f"{job} FAILED: {type(e).__name__}: {str(e)[:150]}")
        return 1
    print("usage: python -m web.jobs <solve|deadline|teams|players>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
