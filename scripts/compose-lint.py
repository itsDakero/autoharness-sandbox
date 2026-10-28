#!/usr/bin/env python3
"""Lint every <category>/<service>/compose.yaml against the homelab rules in CLAUDE.md.

Usage: scripts/compose-lint.py [--root DIR] [FILE ...]
       scripts/compose-lint.py -h|--help

With no FILE, lints every <category>/<service>/compose.yaml under the repo root (dot dirs such as
.worktrees/ are skipped). Port uniqueness is always checked across the whole repo plus any FILE given.
--root DIR   repo root (default: the parent of scripts/); CLAUDE.md and docs/m1-core.md are read from it.

Rules (one line per finding: `<file>[:<line>]: <rule>: <detail>`):
  image-pinned     image has an explicit tag or digest, never :latest; build-only services need image: too
  logging-cap      logging driver json-file with max-size 10m and max-file 3 (templates/compose.yaml)
  healthcheck      a healthcheck (not disabled), unless the service builds from a local Dockerfile with its
                   own HEALTHCHECK, or docs/m1-core.md "## Healthchecks" lists it as healthy from its
                   image ("left alone: ...") or as skipped ("Skipped: ...")
  web-labels       a service with homelab.port carries Traefik (enable, router rule/entrypoints named after
                   the service, loadbalancer port or router .service), dashboard (homelab.name/group/icon/audience/description)
                   and Uptime Kuma (kuma.<id>.<type>.name) labels; network_mode: host skips Traefik
  port-unique      homelab.port is used by one service only across the repo
  port-table       homelab.port has a row in the CLAUDE.md Ports table naming the service
  docker-sock      no docker.sock mount outside core/docker-socket-proxy
  media-ro         /mnt/media (or ${MEDIA_PATH}) mounts are :ro unless the line, or the comment lines
                   directly above it, say "approved"
  parse            the file is valid YAML with a services: mapping

Exit codes: 0 no findings, 1 findings, 2 usage error (bad flag, missing file or root).

Ideas borrowed, not code: DCLint (github.com/zavoloklom/docker-compose-linter): named rules, one finding
per line with file and line, non-zero exit on findings, explicit image tags, duplicate exported ports.
compose-lint (github.com/tmatens/compose-lint): security-minded checks such as the Docker socket mount,
rule ids in every finding. Stdlib + PyYAML only; reads files, changes nothing.
"""
import os
import re
import sys

import yaml

SOCK = "docker" + ".sock"
SOCK_OK = "core/docker-socket-proxy/compose.yaml"
MEDIA_SOURCES = ("/mnt/media", "${MEDIA_PATH}", "$MEDIA_PATH")
DASHBOARD_LABELS = ("homelab.name", "homelab.group", "homelab.icon", "homelab.audience",
                    "homelab.description")
AUDIENCES = ("admin", "family")


def usage(msg):
    print(f"compose-lint: {msg}\nUsage: scripts/compose-lint.py [--root DIR] [FILE ...] (--help)",
          file=sys.stderr)
    sys.exit(2)


def find_compose_files(root):
    out = []
    for cat in sorted(os.listdir(root)):
        cdir = os.path.join(root, cat)
        if cat.startswith(".") or not os.path.isdir(cdir):
            continue
        for svc in sorted(os.listdir(cdir)):
            path = os.path.join(cdir, svc, "compose.yaml")
            if not svc.startswith(".") and os.path.isfile(path):
                out.append(path)
    return out


def ports_table(root):
    """{port: first word of the service column} from the CLAUDE.md Ports table."""
    table, in_ports = {}, False
    try:
        with open(os.path.join(root, "CLAUDE.md"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("## "):
                    in_ports = line.strip() == "## Ports"
                    continue
                m = re.match(r"\|\s*(\d+)\s*\|\s*([^|]*)\|", line) if in_ports else None
                if m:
                    words = m.group(2).split()
                    table[int(m.group(1))] = words[0] if words else ""
    except OSError:
        pass
    return table


def healthcheck_exceptions(root):
    """Services docs/m1-core.md's Healthchecks section names as healthy from the image or skipped."""
    try:
        with open(os.path.join(root, "docs", "m1-core.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set()
    m = re.search(r"^## Healthchecks\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    section = " ".join(m.group(1).split()) if m else ""
    names = set()
    m = re.search(r"left alone:\s*([^.]*)\.", section)
    if m:
        names.update(n.strip() for n in m.group(1).split(","))
    m = re.search(r"Skipped:\s*(.*?)\.(?:\s|$)", re.sub(r"\([^)]*\)", "", section))
    if m:
        # "autokuma (why...); adguard (why...)", reasons dropped: the first word of each clause.
        for clause in m.group(1).split(";"):
            words = clause.split()
            if words:
                names.add(words[0].strip("`,"))
    names.discard("")
    return names


def labels_of(svc):
    raw = svc.get("labels") or {}
    if isinstance(raw, dict):
        # mapping syntax: YAML true/false come back as bools, compose passes them as "true"/"false"
        return {str(k): "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
                for k, v in raw.items()}
    out = {}
    for item in raw:
        k, _, v = str(item).partition("=")
        out[k.strip()] = v.strip()
    return out


def node_lines(doc_node):
    """{service: {"_": line, "at": {field: line}, "volumes": [line per item], "labels": {key: line}}}.

    Lines are 1-based."""
    out = {}
    if not isinstance(doc_node, yaml.MappingNode):
        return out
    for k, v in doc_node.value:
        if k.value != "services" or not isinstance(v, yaml.MappingNode):
            continue
        for sk, sv in v.value:
            info = {"_": sk.start_mark.line + 1, "at": {}, "volumes": [], "labels": {}}
            if isinstance(sv, yaml.MappingNode):
                for fk, fv in sv.value:
                    info["at"][fk.value] = fk.start_mark.line + 1
                    if fk.value == "volumes" and isinstance(fv, yaml.SequenceNode):
                        info["volumes"] = [n.start_mark.line + 1 for n in fv.value]
                    elif fk.value == "labels" and isinstance(fv, yaml.SequenceNode):
                        for n in fv.value:
                            if isinstance(n, yaml.ScalarNode):
                                info["labels"][n.value.partition("=")[0].strip()] = n.start_mark.line + 1
                    elif fk.value == "labels" and isinstance(fv, yaml.MappingNode):
                        for lk, _ in fv.value:
                            info["labels"][lk.value] = lk.start_mark.line + 1
            out[sk.value] = info
    return out


def image_problem(image):
    if not image:
        return None
    ref = str(image)
    if "@sha256:" in ref:
        return None
    last = ref.rsplit("/", 1)[-1]
    if ":" not in last:
        return f"{ref} has no tag (pin an exact version)"
    if last.rsplit(":", 1)[1] == "latest":
        return f"{ref} uses :latest (pin an exact version)"
    return None


def logging_problem(svc):
    log = svc.get("logging")
    if not isinstance(log, dict):
        return "no logging: block (json-file, max-size 10m, max-file 3)"
    opts = log.get("options") if isinstance(log.get("options"), dict) else {}
    bad = []
    if log.get("driver") != "json-file":
        bad.append(f"driver {log.get('driver')!r}")
    if str(opts.get("max-size")) != "10m":
        bad.append(f"max-size {opts.get('max-size')!r}")
    if str(opts.get("max-file")) != "3":
        bad.append(f"max-file {opts.get('max-file')!r}")
    return f"want json-file 10m x 3, got {', '.join(bad)}" if bad else None


def mounts(svc):
    """(index, source, target, read_only) per volume entry, short or long syntax."""
    for i, v in enumerate(svc.get("volumes") or []):
        if isinstance(v, dict):
            yield i, str(v.get("source", "")), str(v.get("target", "")), bool(v.get("read_only"))
        else:
            parts = str(v).split(":")
            src = parts[0] if len(parts) > 1 else ""
            tgt = parts[1] if len(parts) > 1 else parts[0]
            mode = parts[2] if len(parts) > 2 else ""
            yield i, src, tgt, "ro" in mode.split(",")


def is_media(path):
    return any(path == s or path.startswith(s + "/") for s in MEDIA_SOURCES)


def approved(lines, lineno):
    """True if line `lineno` (1-based) or the comment block directly above it says "approved"."""
    if not lineno or lineno > len(lines):
        return False
    line = lines[lineno - 1]
    if "#" in line and "approved" in line.split("#", 1)[1].lower():
        return True
    i = lineno - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        if "approved" in lines[i].lower():
            return True
        i -= 1
    return False


def dockerfile_healthcheck(compose_path, svc):
    """True if the service builds from a local Dockerfile with its own HEALTHCHECK (not NONE)."""
    build = svc.get("build")
    if not build:
        return False
    ctx, dockerfile = (build, "Dockerfile") if isinstance(build, str) else (
        build.get("context", "."), build.get("dockerfile", "Dockerfile"))
    path = os.path.join(os.path.dirname(compose_path), str(ctx), str(dockerfile))
    try:
        with open(path, encoding="utf-8") as f:
            return any(re.match(r"\s*HEALTHCHECK\s+(?!NONE\b)", line, re.I) for line in f)
    except OSError:
        return False


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    data = yaml.safe_load(text)
    return text, data, node_lines(yaml.compose(text))


def lint_file(path, rel, hc_exempt, table, port_users):
    findings = []

    def add(line, rule, detail):
        findings.append(f"{rel}:{line}: {rule}: {detail}" if line else f"{rel}: {rule}: {detail}")

    try:
        text, data, where = load(path)
    except (OSError, yaml.YAMLError) as e:
        add(None, "parse", str(e).replace("\n", " "))
        return findings
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict):
        add(None, "parse", "no services: mapping")
        return findings
    lines = text.splitlines()

    for name, svc in services.items():
        svc = svc if isinstance(svc, dict) else {}
        w = where.get(name, {"_": None, "at": {}, "volumes": [], "labels": {}})
        at = w["_"]
        field = lambda k: w["at"].get(k, at)  # noqa: E731

        if "image" not in svc:
            add(at, "image-pinned", f"{name}: no image: (build-only images are tagged :latest; "
                "add image: homelab/<name>:<version>)")
        else:
            problem = image_problem(svc["image"])
            if problem:
                add(field("image"), "image-pinned", f"{name}: {problem}")

        problem = logging_problem(svc)
        if problem:
            add(field("logging"), "logging-cap", f"{name}: {problem}")

        hc = svc.get("healthcheck")
        if name not in hc_exempt and not dockerfile_healthcheck(path, svc):
            if not isinstance(hc, dict):
                add(at, "healthcheck", f"{name}: no healthcheck (and not an exception in docs/m1-core.md)")
            elif hc.get("disable"):
                add(field("healthcheck"), "healthcheck", f"{name}: healthcheck disabled")

        labels = labels_of(svc)
        lab_line = lambda k: w["labels"].get(k, field("labels"))  # noqa: E731
        if "homelab.port" in labels:
            missing = [k for k in DASHBOARD_LABELS if not labels.get(k)]
            if labels.get("homelab.audience") and labels["homelab.audience"] not in AUDIENCES:
                add(lab_line("homelab.audience"), "web-labels",
                    f"{name}: homelab.audience={labels['homelab.audience']} (admin or family)")
            if svc.get("network_mode") != "host":
                router = f"traefik.http.routers.{name}"
                for k in ("traefik.enable", f"{router}.rule", f"{router}.entrypoints"):
                    if not labels.get(k):
                        missing.append(k)
                lb = f"traefik.http.services.{name}.loadbalancer.server.port"
                if not labels.get(lb) and not labels.get(f"{router}.service"):
                    missing.append(lb)
                if labels.get("traefik.enable") and labels["traefik.enable"] != "true":
                    add(lab_line("traefik.enable"), "web-labels", f"{name}: traefik.enable is not true")
            if not any(re.fullmatch(r"kuma\.[^.]+\.[^.]+\.name", k) for k in labels):
                missing.append("kuma.<id>.<type>.name (Uptime Kuma)")
            if missing:
                add(field("labels"), "web-labels", f"{name}: missing {', '.join(missing)}")

            port_s = labels["homelab.port"]
            pline = lab_line("homelab.port")
            if not port_s.isdigit():
                add(pline, "port-table", f"{name}: homelab.port={port_s} is not a number")
            else:
                port = int(port_s)
                others = [u for u in port_users.get(port, []) if u != (rel, name)]
                if others:
                    add(pline, "port-unique", f"{name}: homelab.port={port} also used by "
                        + ", ".join(f"{r} ({s})" for r, s in others))
                if port not in table:
                    add(pline, "port-table", f"{name}: homelab.port={port} not in the CLAUDE.md Ports table")
                elif table[port] not in (name, rel.split("/")[-2] if "/" in rel else ""):
                    add(pline, "port-table", f"{name}: homelab.port={port} is listed for "
                        f"{table[port] or '(blank)'} in the CLAUDE.md Ports table")

        for i, src, tgt, ro in mounts(svc):
            vline = w["volumes"][i] if i < len(w["volumes"]) else field("volumes")
            if SOCK in src or SOCK in tgt:
                if rel != SOCK_OK:
                    add(vline, "docker-sock", f"{name}: mounts {src or tgt}; use docker-socket-proxy")
            if (is_media(src) or (not src and is_media(tgt))) and not ro and not approved(lines, vline):
                add(vline, "media-ro", f"{name}: {src or tgt} -> {tgt} is read-write without an "
                    "approval comment (add :ro)")
    return findings


def collect_ports(paths, root):
    users = {}
    for path in paths:
        try:
            _, data, _ = load(path)
        except (OSError, yaml.YAMLError):
            continue
        services = data.get("services") if isinstance(data, dict) else None
        for name, svc in (services or {}).items():
            port = labels_of(svc if isinstance(svc, dict) else {}).get("homelab.port", "")
            if port.isdigit():
                users.setdefault(int(port), []).append((relpath(path, root), name))
    return users


def relpath(path, root):
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    return path if rel.startswith("..") else rel.replace(os.sep, "/")


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = []
    it = iter(argv)
    for a in it:
        if a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        if a == "--root":
            root = next(it, None)
            if root is None:
                usage("--root needs a directory")
        elif a.startswith("--root="):
            root = a.split("=", 1)[1]
        elif a.startswith("-"):
            usage(f"unknown option {a}")
        else:
            files.append(a)
    if not os.path.isdir(root):
        usage(f"no such directory: {root}")
    for f in files:
        if not os.path.isfile(f):
            usage(f"no such file: {f}")

    repo = find_compose_files(root)
    targets = files or repo
    seen = {os.path.abspath(p) for p in repo}
    all_paths = repo + [f for f in files if os.path.abspath(f) not in seen]
    port_users = collect_ports(all_paths, root)
    table = ports_table(root)
    hc_exempt = healthcheck_exceptions(root)

    findings = []
    for path in targets:
        findings += lint_file(path, relpath(path, root), hc_exempt, table, port_users)
    for line in findings:
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
