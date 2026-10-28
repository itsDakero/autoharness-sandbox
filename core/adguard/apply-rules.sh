#!/usr/bin/env bash
# Install the *.lan rewrite as AdGuard custom filtering rules (idempotent).
# Tailnet clients (100.64.0.0/10) get the Tailscale IP, everyone else the LAN IP.
# Usage: core/adguard/apply-rules.sh   (needs ADGUARD_USERNAME/PASSWORD in .env)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; . "$REPO/.env"; set +a
: "${ADGUARD_USERNAME:?set in .env}" "${ADGUARD_PASSWORD:?set in .env}"

export API="http://${LAN_IP}:3000/control"
python3 - <<'PY'
import base64, json, os, urllib.request

api = os.environ["API"]
auth = base64.b64encode(f'{os.environ["ADGUARD_USERNAME"]}:{os.environ["ADGUARD_PASSWORD"]}'.encode()).decode()
domain, lan, ts = os.environ["DOMAIN"], os.environ["LAN_IP"], os.environ["TAILSCALE_IP"]

BEGIN, END = "! homelab:begin (managed by apply-rules.sh)", "! homelab:end"
managed = [
    BEGIN,
    f"||{domain}^$dnsrewrite=NOERROR;A;{ts},client=100.64.0.0/10",
    f"||{domain}^$dnsrewrite=NOERROR;A;{lan},client=~100.64.0.0/10",
    END,
]

def call(path, body=None):
    req = urllib.request.Request(f"{api}/{path}", headers={"Authorization": f"Basic {auth}"})
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else None

current = call("filtering/status").get("user_rules") or []
kept, inside = [], False
for line in current:
    if line == BEGIN:
        inside = True
    elif line == END:
        inside = False
    elif not inside:
        kept.append(line)
rules = kept + managed
if rules == current:
    print("AdGuard rules already up to date")
else:
    call("filtering/set_rules", {"rules": rules})
    print("AdGuard rules updated:")
    print("\n".join(managed))
PY
