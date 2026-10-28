#!/usr/bin/env python3
"""Benchmark candidate models on the Mac mini's Ollama (speed, memory, tool calls).

Usage: scripts/model-bench.py http://<TS_IP>:11434 [--models a,b] [--ctx 65536] [--no-write]
       scripts/model-bench.py --memory http://<TS_IP>:11434 [--third <model>] [--no-write]

--memory: stacks models (base, +second, +third) and records resident GB per model, macOS memory
pressure and swap (over SSH) into the memory-budget table in docs/mac-mini.md.

Run by hand from the homelab. Pulls nothing; only generates and unloads (keep_alive 0).
Writes the Markdown table between the model-bench markers in docs/mac-mini.md.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

START = "<!-- model-bench:start -->"
END = "<!-- model-bench:end -->"
MEM_START = "<!-- memory-budget:start -->"
MEM_END = "<!-- memory-budget:end -->"
DEFAULT_MODELS = "gemma4:12b-it-qat,qwen3.5:9b-q4_K_M,qwen3.5:9b,granite4.1:8b"
SYSTEM = "You are the homelab assistant. Answer by calling exactly one of the tools."


def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
TOOLS = [
    fn("service_status", "Status of a homelab service", {"name": S}, ["name"]),
    fn("list_ideas", "List ideas in a state", {"state": {
        "type": "string", "enum": ["queued", "parked", "done", "proposed", "rejected"]}}, ["state"]),
    fn("disk_health", "SMART health of disks", {"disk": S}, []),
    fn("backup_status", "When the last backup ran", {}, []),
    fn("propose_idea", "Propose a new idea", {"title": S, "body": S}, ["title", "body"]),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}
REQUIRED = {t["function"]["name"]: t["function"]["parameters"]["required"] for t in TOOLS}

PROMPTS = [
    {"prompt": "What's the status of jellyfin?", "tool": "service_status", "args": {"name": "jellyfin"}},
    {"prompt": "List the parked ideas.", "tool": "list_ideas", "args": {"state": "parked"}},
    {"prompt": "Is qbittorrent running?", "tool": "service_status", "args": {"name": "qbittorrent"}},
    {"prompt": "Any problems with the disks?", "tool": "disk_health", "args": {}},
    {"prompt": "When did the last backup run?", "tool": "backup_status", "args": {}},
    {"prompt": "What's waiting in the idea queue?", "tool": "list_ideas", "args": {"state": "queued"}},
    {"prompt": "Suggest an idea: a weekly report of Jellyfin's most-watched shows.",
     "tool": "propose_idea", "args": {"title": None, "body": None}},
    {"prompt": "Check sonarr for me.", "tool": "service_status", "args": {"name": "sonarr"}},
    {"prompt": "Which ideas are done already?", "tool": "list_ideas", "args": {"state": "done"}},
    {"prompt": "Is sda healthy?", "tool": "disk_health", "args": {"disk": "sda"}},
]


class Bench:
    def __init__(self, url, ctx, timeout):
        self.url, self.ctx, self.timeout = url, ctx, timeout

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def chat(self, model, messages, predict, tools=None):
        body = {"model": model, "messages": messages, "stream": False,
                "options": {"num_ctx": self.ctx, "num_predict": predict}}
        if tools:
            body["tools"] = tools
        return self.call("/api/chat", body)

    def unload(self, model):
        try:
            self.call("/api/generate", {"model": model, "keep_alive": 0})
        except (urllib.error.URLError, OSError, ValueError):
            pass


def filler(tokens):
    words = int(tokens * 0.75)
    lines, n, i = [], 0, 0
    while n < words:
        i += 1
        line = f"{i:05d} homelab container svc-{i % 17} checked ok latency {i % 97} ms disk {i % 5} fine"
        lines.append(line)
        n += len(line.split())
    return "\n".join(lines)


def parse_args(call):
    if isinstance(call, dict):
        return call
    if isinstance(call, str):
        try:
            v = json.loads(call)
        except ValueError:
            return None
        return v if isinstance(v, dict) else None
    return None


def score(item, msg):
    calls = msg.get("tool_calls") or []
    valid = bool(calls)
    parsed = []
    for c in calls:
        f = c.get("function", {})
        a = parse_args(f.get("arguments"))
        if f.get("name") not in TOOL_NAMES or a is None:
            valid = False
        parsed.append((f.get("name"), a))
    if not valid:
        return False, False
    name, args = parsed[0]
    if name != item["tool"]:
        return True, False
    for req in REQUIRED[name]:
        if req not in args:
            return True, False
    for k, want in item["args"].items():
        got = args.get(k)
        if want is None:
            if not (isinstance(got, str) and got.strip()):
                return True, False
        elif str(got).strip().lower() != want.lower():
            return True, False
    return True, True


def bench_model(b, m, info, prompts, prefill_tokens, verbose):
    row = {"model": m, "format": f"{info.get('format', '?')} {info.get('quantization_level') or info.get('runner', '')}".strip()}
    try:
        r = b.chat(m, [{"role": "user", "content": "Write about 200 words on why a home server needs backups."}], 256)
        row["load"] = f"{r.get('load_duration', 0) / 1e9:.1f}"
        row["decode"] = f"{r['eval_count'] / r['eval_duration'] * 1e9:.1f}"
        r = b.chat(m, [{"role": "user", "content": filler(prefill_tokens) + "\n\nSummarise the log above in 3 bullet points."}], 128)
        row["prefill"] = f"{r['prompt_eval_count'] / r['prompt_eval_duration'] * 1e9:.1f}"
        row["ptoks"] = r["prompt_eval_count"]
        row["resident"] = row["gpu"] = row["ctx"] = "?"
        for e in b.call("/api/ps").get("models", []):
            if e.get("name") == m or e.get("model") == m:
                size = e.get("size") or 0
                row["resident"] = f"{size / 1e9:.1f}"
                row["gpu"] = f"{(e.get('size_vram') or 0) / size * 100:.0f}" if size else "?"
                row["ctx"] = str(e.get("context_length", "?"))
        valid = right = 0
        t0 = time.time()
        for it in prompts:
            r = b.chat(m, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": it["prompt"]}], 256, TOOLS)
            v, ok = score(it, r.get("message", {}))
            valid += v
            right += ok
            if verbose:
                print(f"  [{m}] {it['prompt']!r}: valid={v} right={ok}", file=sys.stderr)
        n = len(prompts)
        row["valid"], row["right"] = f"{valid}/{n}", f"{right}/{n}"
        row["spt"] = f"{(time.time() - t0) / n:.1f}"
    except (urllib.error.URLError, OSError, ValueError, KeyError, ZeroDivisionError) as e:
        row["error"] = f"error: {str(e)[:60]}".replace("|", "/")
    finally:
        b.unload(m)
    return row


def parse_free_pct(text):
    m = re.search(r"free percentage:\s*(\d+)%", text or "")
    return m.group(1) if m else "?"


def parse_pressure(text):
    t = (text or "").strip()
    for line in reversed(t.splitlines()):
        if line.strip() in ("1", "2", "4"):
            return {"1": "normal", "2": "warn", "4": "critical"}[line.strip()]
    return "?"


def parse_swap_gb(text):
    m = re.search(r"used = ([\d.]+)M", text or "")
    return f"{float(m.group(1)) / 1024:.2f}" if m else "?"


def mac_stats(host):
    """Free %, pressure, swap GB from the Mac over key-only SSH; '?' each on any failure."""
    cmd = "memory_pressure -Q; sysctl -n kern.memorystatus_vm_pressure_level; sysctl vm.swapusage"
    out = ""
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, cmd],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"ssh {host} failed (exit {r.returncode}): {r.stderr.strip()[:100]}", file=sys.stderr)
        else:
            out = r.stdout
    except (subprocess.SubprocessError, OSError) as e:
        print(f"ssh {host} failed: {str(e)[:100]}", file=sys.stderr)
    return parse_pressure(out), parse_free_pct(out), parse_swap_gb(out)


def memory_scenario(b, name, models, host):
    row = {"name": name, "models": ", ".join(models), "res": "", "total": "?", "gpu": "?",
           "ctx": "?", "evicted": "?", "pressure": "?", "free": "?", "swap": "?"}
    try:
        for e in b.call("/api/ps").get("models", []):
            b.unload(e.get("name") or e.get("model"))
        failed = []
        for m in models:
            try:
                b.call("/api/chat", {"model": m, "messages": [{"role": "user", "content": "Say hi."}],
                                     "stream": False, "keep_alive": "10m",
                                     "options": {"num_ctx": b.ctx, "num_predict": 1}})
            except (urllib.error.URLError, OSError, ValueError) as e:
                msg = str(e)
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        msg = f"HTTP {e.code} {e.read().decode()[:80]}"
                    except (OSError, ValueError):
                        msg = f"HTTP {e.code}"
                failed.append(m)
                print(f"load of {m} failed: {msg}", file=sys.stderr)
        live = b.call("/api/ps").get("models", [])
        by = {(e.get("name") or e.get("model")): e for e in live}
        parts, total, gpus, ctxs = [], 0, [], []
        for m in models:
            e = by.get(m)
            if not e:
                continue
            size = e.get("size") or 0
            total += size
            parts.append(f"{m}={size / 1e9:.1f}")
            if size:
                gpus.append((e.get("size_vram") or 0) / size * 100)
            ctxs.append(str(e.get("context_length", "?")))
        row["res"] = ", ".join(parts) or "none"
        row["total"] = f"{total / 1e9:.1f}"
        row["gpu"] = f"{min(gpus):.0f}" if gpus else "?"
        row["ctx"] = ctxs[0] if ctxs else "?"
        missing = [m for m in models if m not in by]
        row["evicted"] = ", ".join(missing) if missing else "none"
        if failed:
            row["evicted"] += " (load failed: " + ", ".join(failed) + ")" if missing else ""
        row["pressure"], row["free"], row["swap"] = mac_stats(host)
    except (urllib.error.URLError, OSError, ValueError) as e:
        row["evicted"] = f"error: {str(e)[:60]}".replace("|", "/")
    return row


def run_memory(a, b, version, have):
    scenarios = [("(a)", [a.base]), ("(b)", [a.base, a.second])]
    if a.third:
        scenarios.append(("(c)", [a.base, a.second, a.third]))
    rows, loaded_any = [], set()
    try:
        for name, models in scenarios:
            miss = [m for m in models if m not in have]
            if miss:
                for m in miss:
                    print(f"{m} not pulled: ssh {a.ssh_host} ollama pull {m}", file=sys.stderr)
                rows.append({"name": name, "note": "not pulled: " + ", ".join(
                    f"ssh {a.ssh_host} ollama pull {m}" for m in miss), "models": ", ".join(models)})
                continue
            print(f"Memory scenario {name}: {', '.join(models)} ...", file=sys.stderr)
            loaded_any.update(models)
            rows.append(memory_scenario(b, name, models, a.ssh_host))
            for m in models:
                b.unload(m)
        if not a.third:
            rows.append({"name": "(c)", "note": "skipped: no --third given", "models": ""})
    finally:
        for m in loaded_any:
            b.unload(m)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    out = [f"Memory run {now} UTC, Ollama {version}, num_ctx {a.ctx}.", "",
           "| Scenario | Models | Resident GB each | Total GB | GPU % | ctx | Evicted | Pressure | Free % | Swap used GB |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "note" in r:
            out.append(f"| {r['name']} | {r['models']} | {r['note']} |" + " |" * 7)
        else:
            out.append("| " + " | ".join([r["name"], r["models"], r["res"], r["total"], r["gpu"], r["ctx"],
                                          r["evicted"], r["pressure"], r["free"], r["swap"]]) + " |")
    return "\n".join(out)


def write_table(doc, start, end, table):
    text = doc.read_text()
    i, j = text.find(start), text.find(end)
    if i < 0 or j < i:
        print(f"markers {start} / {end} missing in {doc}; table not written", file=sys.stderr)
        return 1
    doc.write_text(text[:i + len(start)] + "\n" + table + "\n" + text[j:])
    print(f"Wrote table to {doc}", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Benchmark models on the Mac mini's Ollama.")
    ap.add_argument("url", help="Ollama URL, e.g. http://100.74.81.122:11434")
    ap.add_argument("--models", default=None, help=f"comma list (default {DEFAULT_MODELS})")
    ap.add_argument("--memory", action="store_true", help="memory budget mode (stacked loads + Mac stats)")
    ap.add_argument("--base", default="qwen3.5:9b", help="--memory: Hermes's model")
    ap.add_argument("--second", default="gemma4:12b-it-qat", help="--memory: wardrobe's model")
    ap.add_argument("--third", default=None, help="--memory: Ollama model standing in for a Whisper-sized load")
    ap.add_argument("--ssh-host", default="mac-mini", help="--memory: SSH host for memory_pressure/swap")
    ap.add_argument("--ctx", type=int, default=65536)
    ap.add_argument("--prompts", help="JSON list of {prompt, tool, args} replacing the built-in ten")
    ap.add_argument("--prefill-tokens", type=int, default=16000)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--doc", default=str(Path(__file__).resolve().parent.parent / "docs" / "mac-mini.md"))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.memory and a.models is not None:
        ap.error("--memory and --models cannot be combined")
    if a.models is None:
        a.models = DEFAULT_MODELS
    url = a.url.rstrip("/")
    prompts = json.loads(Path(a.prompts).read_text()) if a.prompts else PROMPTS
    b = Bench(url, a.ctx, a.timeout)
    try:
        version = b.call("/api/version").get("version", "?")
        tags = b.call("/api/tags")
        loaded = b.call("/api/ps")
    except (urllib.error.URLError, OSError):
        print(f"Ollama at {url} not reachable (is the Mac up? try: ssh mac-mini true)", file=sys.stderr)
        return 2
    have = {m["name"]: m.get("details", {}) for m in tags.get("models", [])}
    if a.memory:
        table = run_memory(a, b, version, have)
        print(table)
        if a.no_write:
            return 0
        return write_table(Path(a.doc), MEM_START, MEM_END, table)
    for e in loaded.get("models", []):
        b.unload(e.get("name") or e.get("model"))
    rows = []
    for m in [x.strip() for x in a.models.split(",") if x.strip()]:
        if m not in have:
            print(f"{m} not pulled: ssh mac-mini ollama pull {m}", file=sys.stderr)
            rows.append({"model": m, "error": "not pulled"})
            continue
        print(f"Benchmarking {m} ...", file=sys.stderr)
        rows.append(bench_model(b, m, have[m], prompts, a.prefill_tokens, a.verbose))
    ptoks = next((r["ptoks"] for r in rows if "ptoks" in r), "?")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    out = [f"Run {now} UTC, Ollama {version}, num_ctx {a.ctx}, prefill prompt {ptoks} tokens.", "",
           "| Model | Format | Load s | Prefill tok/s | Decode tok/s | Resident GB | GPU % | ctx | Valid tool calls | Right tool+args | s/tool call |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            out.append(f"| {r['model']} | {r.get('format', '')} | {r['error']} |" + " |" * 8)
            continue
        out.append("| " + " | ".join([r["model"], r["format"], r["load"], r["prefill"], r["decode"], r["resident"],
                                      r["gpu"], r["ctx"], r["valid"], r["right"], r["spt"]]) + " |")
    table = "\n".join(out)
    print(table)
    if a.no_write:
        return 0
    doc = Path(a.doc)
    text = doc.read_text()
    i, j = text.find(START), text.find(END)
    if i < 0 or j < i:
        print(f"markers {START} / {END} missing in {doc}; table not written", file=sys.stderr)
        return 1
    doc.write_text(text[:i + len(START)] + "\n" + table + "\n" + text[j:])
    print(f"Wrote table to {doc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
