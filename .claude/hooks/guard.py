#!/usr/bin/env python3
"""PreToolUse guard for the homelab rules in CLAUDE.md.

Reads the hook JSON on stdin. Exit 2 (reason on stderr) blocks the call;
printing a permissionDecision "ask" asks the user; exit 0 lets it through.
Any internal error also exits 2 (fail closed). settings.json sets
`onFailure: block` for failures Python can't catch (missing interpreter, timeout).
"""
import json
import re
import shlex
import sys
from pathlib import PurePath

SOCKET_PROXY_COMPOSE = "core/docker-socket-proxy/compose.yaml"

# A file named .env (bare or at the end of a path); not .env.example, not process.env.X
ENV_IN_CMD = re.compile(r"(?<![\w.$-])(?:\S*/)?\.env(?![\w.-])")
ENV_FILE_ARG = re.compile(r"--(?:env-file|exclude)(?:=|\s+)\S+")  # pass .env / skip it; no read
COMPOSE_CMD = re.compile(r"\b(docker\s+compose|docker-compose|dc\.sh)\b")
SAFE_CONFIG_FLAGS = re.compile(r"(?:^|\s)(-q|--quiet|--images|--services|--volumes|--networks|--profiles)\b")
DOCKER_INSPECT = re.compile(r"\bdocker\s+(?:\w+\s+)?inspect\b")
LEAKY_FORMAT = re.compile(r"Env|\{\{\s*(json\s+)?\.\s*\}\}|\.Config\s*\}\}")
DOCKER_EXEC = re.compile(r"\bdocker\s+(?:container\s+)?exec\b|\b(?:docker\s+compose|dc\.sh)\b.*\bexec\b")
ENV_DUMP = re.compile(r"\b(printenv|env)\b|\bexport\s+-p\b")
# Quoted commit/tag messages are text, not commands
MESSAGE_ARG = re.compile(r"""(?:-m|--message)(?:=|\s+)(?:"(?:[^"\\]|\\.)*"|'[^']*')""")
RECURSIVE_GREP = re.compile(r"(?<!git )\b[ef]?grep\b[^|;&]*\s-[a-zA-Z]*[rR]")
MEDIA = re.compile(r"/mnt/media|\$\{?MEDIA_PATH\}?")
MEDIA_WRITE = re.compile(r"""(?<![-\w])(rm|mv|cp|tee|touch|chmod|chown|rsync|mkdir|rmdir|ln|truncate|dd|unlink)\b|\bsed\s+(-\S*\s+)*-i|>>?\s*["']?(/mnt/media|\$\{?MEDIA_PATH)""")
MEDIA_MOUNT = re.compile(r"""(?:/mnt/media|\$\{?MEDIA_PATH\}?)[^\s:"']*:[^\s"']+""")
SOCKET_USE = re.compile(r"\bdocker\s+(run|create)\b|\s(-v|--volume|--mount|--unix-socket)\b|\b(socat|nc|ncat)\b")
IMAGE_LINE = re.compile(r"""^\s*image:\s*["']?([^\s"'#]+)""", re.M)
DOCKER_RUN = re.compile(r"\bdocker\s+(?:container\s+)?(run|create|pull)\b")
# docker run/create flags that take a separate value
VALUE_FLAGS = {
    "-e", "--env", "-v", "--volume", "-p", "--publish", "--name", "--network", "--net", "-w", "--workdir",
    "-u", "--user", "--entrypoint", "--env-file", "-l", "--label", "--mount", "--restart", "--platform",
    "-h", "--hostname", "--add-host", "--cap-add", "--cap-drop", "--device", "--dns", "--security-opt",
    "--tmpfs", "--ulimit", "--log-driver", "--log-opt", "-m", "--memory", "--cpus", "--pull",
    "--health-cmd", "--gpus", "--ipc", "--pid", "--group-add", "--expose", "--stop-signal",
}


def block(msg: str) -> None:
    print(f"Blocked by homelab guard: {msg}", file=sys.stderr)
    sys.exit(2)


def ask(msg: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": msg,
    }}))
    sys.exit(0)


def is_env_file(path: str) -> bool:
    name = PurePath(path).name
    return name == ".env" or (name.endswith(".env") and name != ".env.example")


def bad_image(ref: str) -> bool:
    """True for :latest or an untagged reference (digests are fine)."""
    if "@" in ref or "${" in ref:
        return False
    last = ref.rsplit("/", 1)[-1]
    return ":" not in last or last.endswith(":latest")


def run_image(cmd: str) -> str | None:
    """Best-effort: the image argument of a docker run/create/pull."""
    m = DOCKER_RUN.search(cmd)
    if not m:
        return None
    try:
        tokens = shlex.split(cmd[m.end():])
    except ValueError:
        return None
    skip = False
    for tok in tokens:
        if skip:
            skip = False
        elif tok in ("&&", "||", ";", "|"):
            return None
        elif tok.startswith("-"):
            skip = tok in VALUE_FLAGS
        else:
            return tok
    return None


def check_command(cmd: str) -> None:
    cmd = MESSAGE_ARG.sub("-m MSG", cmd)
    if re.search(r"\bsudo\b", cmd):
        block("no sudo. Anything needing root goes in bootstrap.sh (idempotent, logged) for the user to run.")
    if ENV_IN_CMD.search(ENV_FILE_ARG.sub("", cmd)):
        block(".env holds secrets; don't read, copy or source it. Use .env.example for the variable names.")
    if re.search(r"/proc/\S*environ", cmd):
        block("/proc/*/environ prints secrets.")
    if RECURSIVE_GREP.search(cmd) and "--exclude" not in cmd:
        block("recursive grep would read .env. Use the Grep tool (skips gitignored files) or add --exclude='*.env'.")
    if COMPOSE_CMD.search(cmd) and re.search(r"\bconfig\b", cmd) and not SAFE_CONFIG_FLAGS.search(cmd):
        block("`compose config` prints interpolated .env secrets. Use `config -q` (validate) or `config --images`.")
    if DOCKER_INSPECT.search(cmd):
        fmt = re.search(r"(?:--format|-f)(?:=|\s+)(.*)", cmd)
        if not fmt:
            block("`docker inspect` without --format prints container env (secrets). Use --format '{{...}}'.")
        if LEAKY_FORMAT.search(fmt.group(1)):
            block("that --format would print container env (secrets). Pick specific fields.")
    if DOCKER_EXEC.search(cmd) and ENV_DUMP.search(cmd):
        block("dumping a container's environment prints secrets.")
    if MEDIA.search(cmd):
        if MEDIA_WRITE.search(cmd):
            block("never modify /mnt/media. Read-only access only.")
        if any(not m.endswith(":ro") for m in MEDIA_MOUNT.findall(cmd)):
            ask("Mounts the media library without :ro (read-write). CLAUDE.md requires approval.")
    if "docker.sock" in cmd and SOCKET_USE.search(cmd):
        block("Docker API only via docker-socket-proxy (tcp://docker-socket-proxy:2375). Never mount or use docker.sock.")
    if "ANTHROPIC_API_KEY" in cmd:
        block("never create or use ANTHROPIC_API_KEY.")
    if DOCKER_RUN.search(cmd):
        img = run_image(cmd)
        if img and bad_image(img):
            block(f"image `{img}` must be pinned to a version (no :latest, no missing tag).")


def check_file(path: str, content: str) -> None:
    rel = path.split("/homelab/", 1)[-1] if "/homelab/" in path else path
    is_docs = rel.endswith(".md") or rel.startswith(".claude/hooks/")
    if path.startswith("/mnt/media"):
        block("never modify /mnt/media.")
    if not content:
        return
    if not is_docs:
        if "docker.sock" in content and rel != SOCKET_PROXY_COMPOSE:
            block(f"docker.sock is only mounted in {SOCKET_PROXY_COMPOSE}. Use DOCKER_HOST=tcp://docker-socket-proxy:2375.")
        if "ANTHROPIC_API_KEY" in content:
            block("never create or use ANTHROPIC_API_KEY.")
    if rel.endswith((".yaml", ".yml")):
        for ref in IMAGE_LINE.findall(content):
            if bad_image(ref):
                block(f"image `{ref}` must be pinned to a version (no :latest, no missing tag).")
        if any(not m.endswith(":ro") for m in MEDIA_MOUNT.findall(content)):
            ask("Mounts the media library without :ro (read-write). CLAUDE.md requires approval.")


def _main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        block("unexpected hook input")
    inp = data.get("tool_input") or {}
    if not isinstance(inp, dict):
        block("unexpected hook input")
    paths = [inp.get(k) for k in ("file_path", "path", "notebook_path", "glob") if inp.get(k)]
    for p in paths:
        if is_env_file(p):
            block(f"{p} holds secrets; never read or edit it. Variable names are in .env.example.")
    if data.get("tool_name") == "Bash":
        check_command(inp.get("command") or "")
        return
    parts = [inp.get("content"), inp.get("new_string"), inp.get("new_source")]
    parts += [e.get("new_string") for e in inp.get("edits") or [] if isinstance(e, dict)]
    content = "\n".join(p for p in parts if isinstance(p, str))
    for p in paths:
        check_file(p, content)


def main() -> None:
    try:
        _main()
    except Exception as e:  # SystemExit (exit 0/2 above) is not an Exception
        block(f"guard error ({type(e).__name__}: {e}); failing closed.")


if __name__ == "__main__":
    main()
