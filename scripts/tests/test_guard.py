"""Tests for .claude/hooks/guard.py, run as the hook runs: JSON on stdin, exit code + output.

Run: python3 -m unittest discover -s scripts/tests
Some strings are split ("docker" + ".sock") so this file itself passes the guard.
"""
import json
import os
import subprocess
import sys
import unittest

GUARD = os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks", "guard.py")
SOCK = "docker" + ".sock"
KEY = "ANTHROPIC" + "_API_KEY"


def run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    p = subprocess.run([sys.executable, GUARD], input=raw, capture_output=True, text=True, timeout=10)
    return p.returncode, p.stdout, p.stderr


def bash(cmd):
    return run({"tool_name": "Bash", "tool_input": {"command": cmd}})


def write(path, content=""):
    return run({"tool_name": "Write", "tool_input": {"file_path": path, "content": content}})


class GuardCase(unittest.TestCase):
    def assertBlocked(self, result, needle=""):
        code, out, err = result
        self.assertEqual(code, 2, f"expected block, got {code}: {out}{err}")
        self.assertIn("Blocked by homelab guard", err)
        self.assertIn(needle, err)

    def assertAllowed(self, result):
        code, out, err = result
        self.assertEqual(code, 0, f"expected allow, got {code}: {err}")
        self.assertEqual(out.strip(), "", f"expected no decision, got ask: {out}")

    def assertAsks(self, result):
        code, out, err = result
        self.assertEqual(code, 0, err)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "ask")
        self.assertIn(":ro", decision["permissionDecisionReason"])


class Bash(GuardCase):
    def test_blocked(self):
        cases = {
            "sudo apt install jq": "sudo",
            "cat .env": ".env",
            "source /home/dan/homelab/.env": ".env",
            "cp .env /tmp/x": ".env",
            "cat /proc/1/environ": "environ",
            "grep -r password .": "recursive grep",
            "grep -rn TOKEN scripts/": "recursive grep",
            "docker compose config": "compose config",
            "scripts/dc.sh core/traefik config": "compose config",
            "docker inspect traefik": "docker inspect",
            "docker container inspect traefik": "docker inspect",
            "docker inspect --format '{{.Config.Env}}' traefik": "--format",
            "docker inspect --format '{{json .}}' traefik": "--format",
            "docker exec traefik env": "environment",
            "docker exec radarr printenv": "environment",
            "scripts/dc.sh media/radarr exec radarr env": "environment",
            "rm -rf /mnt/media/movies/x": "/mnt/media",
            "touch /mnt/media/x": "/mnt/media",
            "echo hi > /mnt/media/x": "/mnt/media",
            "sed -i s/a/b/ /mnt/media/x.nfo": "/mnt/media",
            f"docker run -v /var/run/{SOCK}:/var/run/{SOCK} alpine:3.20": "socket-proxy",
            f"curl --unix-socket /var/run/{SOCK} http://localhost/containers/json": "socket-proxy",
            f"export {KEY}=x": "ANTHROPIC",
            "docker run --rm nginx:latest": "pinned",
            "docker run --rm -e A=1 --name web nginx": "pinned",
            "docker pull ghcr.io/foo/bar": "pinned",
        }
        for cmd, needle in cases.items():
            with self.subTest(cmd=cmd):
                self.assertBlocked(bash(cmd), needle)

    def test_allowed(self):
        cases = [
            "git status",
            "cat .env.example",
            "docker compose --env-file .env -f core/traefik/compose.yaml ps",
            "scripts/dc.sh core/traefik config -q",
            "docker compose config --images",
            "docker inspect --format '{{.State.Health.Status}}' traefik",
            "grep -rn TOKEN --exclude='*.env' scripts/",
            "git grep -n TOKEN",
            "grep -n foo scripts/backup.sh",
            "ls /mnt/media/movies",
            "du -sh /mnt/media",
            "docker exec radarr ls /config",
            "docker run --rm alpine:3.20 echo hi",
            "docker run --rm -e A=1 --name web nginx:1.27.2",
            "docker pull ghcr.io/foo/bar@sha256:abc",
            'git commit -m "guard: block sudo and cat .env"',
            "node -e 'console.log(process.env.HOME)'",
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertAllowed(bash(cmd))

    def test_media_mount_rw_asks(self):
        self.assertAsks(bash("docker run --rm -v /mnt/media:/media alpine:3.20 ls /media"))

    def test_media_mount_ro_allowed(self):
        self.assertAllowed(bash("docker run --rm -v /mnt/media:/media:ro alpine:3.20 ls /media"))


class Files(GuardCase):
    def test_env_paths_blocked(self):
        for tool, key in [("Read", "file_path"), ("Edit", "file_path"), ("Write", "file_path"),
                          ("Grep", "path"), ("Glob", "glob")]:
            for path in ["/home/dan/homelab/.env", ".env", "tools/fpl/prod.env"]:
                with self.subTest(tool=tool, path=path):
                    self.assertBlocked(run({"tool_name": tool, "tool_input": {key: path}}), "secrets")

    def test_env_example_allowed(self):
        self.assertAllowed(run({"tool_name": "Read", "tool_input": {"file_path": "/home/dan/homelab/.env.example"}}))

    def test_media_write_blocked(self):
        self.assertBlocked(write("/mnt/media/movies/x.nfo", "x"), "/mnt/media")

    def test_socket_outside_proxy_blocked(self):
        content = f"services:\n  x:\n    volumes:\n      - /var/run/{SOCK}:/var/run/{SOCK}:ro\n"
        self.assertBlocked(write("/home/dan/homelab/tools/x/compose.yaml", content), "docker-socket-proxy")

    def test_socket_in_proxy_allowed(self):
        content = f"services:\n  docker-socket-proxy:\n    image: tecnativa/docker-socket-proxy:0.3.0\n" \
                  f"    volumes:\n      - /var/run/{SOCK}:/var/run/{SOCK}:ro\n"
        self.assertAllowed(write("/home/dan/homelab/core/docker-socket-proxy/compose.yaml", content))

    def test_socket_in_docs_allowed(self):
        self.assertAllowed(write("/home/dan/homelab/docs/m1-core.md", f"Never mount {SOCK}."))

    def test_api_key_blocked(self):
        self.assertBlocked(write("/home/dan/homelab/scripts/x.py", f"os.environ['{KEY}']"), "ANTHROPIC")

    def test_api_key_in_edit_blocked(self):
        payload = {"tool_name": "Edit", "tool_input": {
            "file_path": "/home/dan/homelab/scripts/x.py", "old_string": "a", "new_string": KEY}}
        self.assertBlocked(run(payload), "ANTHROPIC")

    def test_api_key_in_multiedit_blocked(self):
        payload = {"tool_name": "MultiEdit", "tool_input": {
            "file_path": "/home/dan/homelab/scripts/x.py",
            "edits": [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": KEY}]}}
        self.assertBlocked(run(payload), "ANTHROPIC")

    def test_unpinned_images_blocked(self):
        for ref in ["nginx:latest", "nginx", "ghcr.io/foo/bar", "lscr.io/linuxserver/radarr:latest"]:
            with self.subTest(ref=ref):
                self.assertBlocked(write("/home/dan/homelab/tools/x/compose.yaml",
                                         f"services:\n  x:\n    image: {ref}\n"), "pinned")

    def test_pinned_images_allowed(self):
        for ref in ["nginx:1.27.2", '"ghcr.io/foo/bar:v2.1"', "nginx@sha256:abc", "${IMAGE}",
                    "localhost:5000/foo:1.0"]:
            with self.subTest(ref=ref):
                self.assertAllowed(write("/home/dan/homelab/tools/x/compose.yaml",
                                         f"services:\n  x:\n    image: {ref}\n"))

    def test_latest_outside_yaml_allowed(self):
        self.assertAllowed(write("/home/dan/homelab/scripts/x.py", "image: nginx:latest\n"))

    def test_media_mount_in_compose(self):
        path = "/home/dan/homelab/media/x/compose.yaml"
        self.assertAsks(write(path, "    volumes:\n      - ${MEDIA_PATH}:/media\n"))
        self.assertAllowed(write(path, "    volumes:\n      - ${MEDIA_PATH}:/media:ro\n"))

    def test_plain_file_allowed(self):
        self.assertAllowed(write("/home/dan/homelab/scripts/x.py", "print('hi')\n"))


class FailClosed(GuardCase):
    def test_bad_input_blocked(self):
        for raw in ["not json", "[]", '{"tool_name": "Bash", "tool_input": "x"}']:
            with self.subTest(raw=raw):
                self.assertBlocked(run(raw))

    def test_empty_input_allowed(self):
        self.assertAllowed(run({"tool_name": "Bash", "tool_input": {}}))


if __name__ == "__main__":
    unittest.main()
