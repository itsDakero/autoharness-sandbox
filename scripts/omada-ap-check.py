#!/usr/bin/env python3
"""Cron (hourly at :50, user dan): Discord alert when an Omada access point is not connected to the controller.

Adopted APs hold a TCP link to the controller on 29814 (docs/m3-omada.md, "How the APs find the controller"). Omada
runs in host network mode, so `ss` on the host sees those links: no root, no API login, no container. The check
counts distinct peer IPs established on :29814 against EXPECTED_APS. A short count is re-checked once after
RECHECK_S seconds (an AP reconnecting after a controller restart is not a problem).
  - fewer APs than expected: one Discord message, repeated daily while it lasts or at once when the count changes;
    exit 1 after it (cron-run.sh --ok 0,1, no double alert from Kuma); Discord post failed: exit 2 (Kuma alerts)
  - all APs back after an alert: one Discord "recovered" line
  - controller not listening on 29814: logged, exit 0 (the omada Kuma monitor alerts on that)
Not urgent (Wi-Fi keeps working on the APs' last config; only controller features wait), so Discord, not ntfy.
State: JSON {"alerted": <epoch>, "count": <n>} in /srv/homelab/omada-ap-check/state; no file = no open alert.

  scripts/omada-ap-check.py            # what cron runs
  scripts/omada-ap-check.py --dry-run  # print the count, post nothing, state untouched
Logs: journalctl -t omada-ap-check. Test overrides (shell env, not .env): OMADA_AP_CHECK_STATE,
OMADA_AP_CHECK_EXPECTED, OMADA_AP_CHECK_RECHECK_S.
"""
import json
import os
import subprocess
import sys
import syslog
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 29814  # AP manage port (v5+ firmware)
EXPECTED_APS = int(os.environ.get("OMADA_AP_CHECK_EXPECTED", "3"))  # the 3 APs in docs/m3-omada.md
RECHECK_S = int(os.environ.get("OMADA_AP_CHECK_RECHECK_S", "90"))
REPEAT_S = 24 * 3600 - 600  # hourly runs drift a little; a daily repeat must not slip to 25 h
STATE = Path(os.environ.get("OMADA_AP_CHECK_STATE", "/srv/homelab/omada-ap-check/state"))


def log(msg: str) -> None:
    syslog.openlog("omada-ap-check")
    syslog.syslog(msg)
    print(msg)


def ss(*args: str) -> list[str]:
    r = subprocess.run(["ss", "-Hn", *args], capture_output=True, text=True, timeout=30, check=True)
    return [line for line in r.stdout.splitlines() if line.strip()]


def listening() -> bool:
    return bool(ss("-tl", f"sport = :{PORT}"))


def connected_aps() -> set[str]:
    """Distinct peer IPs with an established link to :PORT. Columns: Recv-Q Send-Q Local Peer."""
    peers = set()
    for line in ss("-t", "state", "established", f"( sport = :{PORT} )"):
        cols = line.split()
        if len(cols) >= 4:
            ip = cols[3].rsplit(":", 1)[0].strip("[]")
            peers.add(ip.removeprefix("::ffff:"))
    return peers


def read_state() -> dict:
    try:
        s = json.loads(STATE.read_text())
        return s if isinstance(s, dict) and isinstance(s.get("alerted"), int) else {}
    except (OSError, ValueError):
        return {}  # missing or corrupt: treat as no open alert


def write_state(s: dict | None) -> None:
    if s is None:
        STATE.unlink(missing_ok=True)
        return
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s) + "\n")
    tmp.replace(STATE)


def discord(msg: str) -> int:
    return subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], capture_output=True, text=True).returncode


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ["--dry-run"]):
        print("usage: omada-ap-check.py [--dry-run]", file=sys.stderr)
        return 2
    dry = bool(args)
    try:
        if not listening():
            log(f"controller not listening on {PORT}: skipped (omada Kuma monitor covers it)")
            return 0
        aps = connected_aps()
        if len(aps) < EXPECTED_APS and RECHECK_S > 0 and not dry:
            log(f"{len(aps)}/{EXPECTED_APS} APs connected, re-checking in {RECHECK_S}s")
            time.sleep(RECHECK_S)
            aps = connected_aps()
    except (OSError, subprocess.SubprocessError) as e:
        log(f"ss failed: {e}")
        return 2
    n = len(aps)
    seen = ", ".join(sorted(aps)) or "none"
    state = read_state()

    if n >= EXPECTED_APS:
        log(f"ok: {n}/{EXPECTED_APS} APs connected ({seen})")
        if state and not dry:
            rc = discord(f"Omada APs recovered: {n}/{EXPECTED_APS} connected again ({seen}).")
            log(f"recovery sent, discord rc={rc}")
            if rc == 0:
                write_state(None)
        return 0

    log(f"{n}/{EXPECTED_APS} APs connected ({seen})")
    if dry:
        return 0
    now = int(time.time())
    if state and 0 <= now - state["alerted"] < REPEAT_S and state.get("count") == n:
        log(f"suppressed: alerted {(now - state['alerted']) // 3600}h ago")
        return 0
    msg = (f"Omada AP check: only {n}/{EXPECTED_APS} access points connected to the controller ({seen}).\n"
           "Wi-Fi keeps working on the last config; controller features wait.\n"
           "Check: Omada UI (https://homelab:8043/) device list, `ss -tn | grep ':29814'`, UFW 29810-29817 "
           "from the LAN (docs/m3-omada.md)")
    rc = discord(msg)
    log(f"{EXPECTED_APS - n} AP(s) missing, discord rc={rc}")
    if rc != 0:
        return 2  # alert not delivered: let Kuma alert instead
    write_state({"alerted": now, "count": n})
    return 1


if __name__ == "__main__":
    sys.exit(main())
