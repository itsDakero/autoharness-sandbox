# Forensic parsers

Python scripts, run by hand on the host. No containers, ports or dashboard labels.

## Layout
- `forensics/<parser>/` – one directory per parser, lowercase-kebab. The entry script is `<parser>.py`,
  plus `requirements.txt` if it needs third-party packages and `tests/` for tests.
- Test data and evidence live outside the repo in `/srv/homelab/forensics/testdata/` (and later `cases/`),
  never in git. `.gitignore` also blocks common image/dump extensions under `forensics/` as a safety net.
- `/srv/homelab/forensics/` is excluded from restic (`scripts/backup-excludes.txt`). The B2 off-site copy
  copies every nightly snapshot, so excluding it from the local backup is what keeps it off-site.

## Python
- One shared venv, `forensics/.venv` (gitignored):
  `python3 -m venv forensics/.venv && forensics/.venv/bin/pip install -r forensics/<parser>/requirements.txt`
- Pin versions in `requirements.txt` (`package==x.y.z`).
- Parsers take input/output paths as arguments; nothing is hard-coded to a case.

## Parsers
| Parser | Parses | Output |
|---|---|---|
| `discord-cache-parser` | Discord HTTP cache (OkHttp, Chromium simple/blockfile): messages, attachments, avatars | `report.json`, `index.html`, `attachments/`, `avatars/` |
