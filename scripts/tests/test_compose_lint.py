"""Tests for scripts/compose-lint.py, run as a CLI against small temp repos.

Run: python3 -m unittest discover -s scripts/tests
Some strings are split ("docker" + ".sock", ":" + "latest") so this file itself passes the guard.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

LINT = os.path.join(os.path.dirname(__file__), "..", "compose-lint.py")
SOCK = "docker" + ".sock"
LATEST = ":" + "latest"

CLAUDE_MD = """\
# Homelab
## Ports
| Port | Service |
|---|---|
| 8123 | myservice |
| 8124 | other (note) |
## Next
| 9999 | not-a-port-row |
"""

M1_CORE = """\
# M1
## Healthchecks
Already healthy from image or compose, left alone: imagecheck, other-one.
Skipped: sidecar (not a web service; no port); quiet (manual; Dan adds it by hand).
## Later
"""

LOGGING = """\
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
"""

HEALTH = """\
    healthcheck:
      test: ["CMD", "true"]
"""


def web_labels(name="myservice", port=8123):
    return f"""\
    labels:
      - traefik.enable=true
      - traefik.http.routers.{name}.rule=Host(`{name}.lan`)
      - traefik.http.routers.{name}.entrypoints=web
      - traefik.http.services.{name}.loadbalancer.server.port=80
      - homelab.name=My Service
      - homelab.group=Apps
      - homelab.icon={name}
      - homelab.audience=family
      - homelab.description=One line
      - homelab.port={port}
      - kuma.{name}.http.name={name}
      - kuma.{name}.http.url=http://lan:{port}
"""


def service(name="myservice", image="example/app:1.2.3", extra="", logging=LOGGING, health=HEALTH,
            labels=None):
    img = f"    image: {image}\n" if image is not None else ""
    lab = web_labels(name) if labels is None else labels
    return f"  {name}:\n{img}{logging}{health}{extra}{lab}"


class LintCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "docs"))
        with open(os.path.join(self.root, "CLAUDE.md"), "w") as f:
            f.write(CLAUDE_MD)
        with open(os.path.join(self.root, "docs", "m1-core.md"), "w") as f:
            f.write(M1_CORE)

    def tearDown(self):
        self.tmp.cleanup()

    def compose(self, rel, *services, raw=None):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(raw if raw is not None else "services:\n" + "".join(services))
        return path

    def run_lint(self, *args):
        p = subprocess.run([sys.executable, LINT, "--root", self.root, *args],
                           capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout.splitlines(), p.stderr

    def rules(self, lines):
        return [line.split(": ")[1] for line in lines]


class TestCli(LintCase):
    def test_clean_repo_exits_0(self):
        self.compose("apps/myservice/compose.yaml", service())
        code, out, _ = self.run_lint()
        self.assertEqual((code, out), (0, []))

    def test_help(self):
        p = subprocess.run([sys.executable, LINT, "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("Usage: scripts/compose-lint.py", p.stdout)
        self.assertIn("Exit codes", p.stdout)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_lint("--nope")[0], 2)
        self.assertEqual(self.run_lint(os.path.join(self.root, "missing.yaml"))[0], 2)
        p = subprocess.run([sys.executable, LINT, "--root", os.path.join(self.root, "nodir")],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_finding_format_and_exit_1(self):
        self.compose("apps/myservice/compose.yaml", service(image="example/app"))
        code, out, _ = self.run_lint()
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], r"^apps/myservice/compose\.yaml:3: image-pinned: myservice: ")

    def test_single_file_argument(self):
        good = self.compose("apps/myservice/compose.yaml", service())
        self.compose("apps/bad/compose.yaml", service("bad", image="x/y", labels=""))
        self.assertEqual(self.run_lint(good)[:2], (0, []))

    def test_dot_dirs_skipped(self):
        self.compose("apps/myservice/compose.yaml", service())
        self.compose(".worktrees/x/compose.yaml", service("x", image="x/y", labels=""))
        self.assertEqual(self.run_lint()[0], 0)

    def test_parse_error(self):
        self.compose("apps/myservice/compose.yaml", raw="services: [unclosed\n")
        code, out, _ = self.run_lint()
        self.assertEqual((code, self.rules(out)), (1, ["parse"]))


class TestImage(LintCase):
    def check(self, image, extra=""):
        self.compose("apps/myservice/compose.yaml", service(image=image, extra=extra))
        return self.rules(self.run_lint()[1])

    def test_latest(self):
        self.assertEqual(self.check("example/app" + LATEST), ["image-pinned"])

    def test_untagged(self):
        self.assertEqual(self.check("example/app"), ["image-pinned"])

    def test_registry_port_is_not_a_tag(self):
        self.assertEqual(self.check("registry:5000/app"), ["image-pinned"])
        self.assertEqual(self.check("registry:5000/app:1.0"), [])

    def test_digest_ok(self):
        self.assertEqual(self.check("example/app@sha256:" + "a" * 64), [])

    def test_build_only(self):
        self.assertEqual(self.check(None, extra="    build: .\n"), ["image-pinned"])


class TestLoggingAndHealth(LintCase):
    def test_no_logging(self):
        self.compose("apps/myservice/compose.yaml", service(logging=""))
        self.assertEqual(self.rules(self.run_lint()[1]), ["logging-cap"])

    def test_wrong_cap(self):
        bad = LOGGING.replace('"3"', '"5"').replace('"10m"', '"50m"')
        self.compose("apps/myservice/compose.yaml", service(logging=bad))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["logging-cap"])
        self.assertIn("max-size '50m'", out[0])
        self.assertIn("max-file '5'", out[0])

    def test_int_max_file_ok(self):
        self.compose("apps/myservice/compose.yaml", service(logging=LOGGING.replace('"3"', "3")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_no_healthcheck(self):
        self.compose("apps/myservice/compose.yaml", service(health=""))
        self.assertEqual(self.rules(self.run_lint()[1]), ["healthcheck"])

    def test_disabled_healthcheck(self):
        self.compose("apps/myservice/compose.yaml",
                     service(health="    healthcheck:\n      disable: true\n"))
        self.assertEqual(self.rules(self.run_lint()[1]), ["healthcheck"])

    def test_docs_exceptions(self):
        for name in ("imagecheck", "other-one", "sidecar", "quiet"):
            self.compose(f"apps/{name}/compose.yaml", service(name, health="", labels=""))
        self.compose("apps/dan/compose.yaml", service("Dan", health="", labels=""))
        out = self.run_lint()[1]
        self.assertEqual(len(out), 1)
        self.assertIn("Dan: no healthcheck", out[0])

    def test_dockerfile_healthcheck(self):
        self.compose("apps/myservice/compose.yaml", service(health="", extra="    build: .\n"))
        with open(os.path.join(self.root, "apps/myservice/Dockerfile"), "w") as f:
            f.write("FROM python:3.12-slim\nHEALTHCHECK --interval=30s CMD true\n")
        self.assertEqual(self.run_lint()[0], 0)
        with open(os.path.join(self.root, "apps/myservice/Dockerfile"), "w") as f:
            f.write("FROM python:3.12-slim\nHEALTHCHECK NONE\n")
        self.assertEqual(self.rules(self.run_lint()[1]), ["healthcheck"])


class TestWebLabels(LintCase):
    def test_missing_traefik_and_kuma(self):
        labels = "".join(line + "\n" for line in web_labels().splitlines()
                         if "traefik.http.routers" not in line and "kuma." not in line)
        self.compose("apps/myservice/compose.yaml", service(labels=labels))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["web-labels"])
        self.assertIn("traefik.http.routers.myservice.rule", out[0])
        self.assertIn("kuma.<id>.<type>.name", out[0])

    def test_router_named_after_service(self):
        labels = web_labels().replace("routers.myservice", "routers.other")
        self.compose("apps/myservice/compose.yaml", service(labels=labels))
        self.assertEqual(self.rules(self.run_lint()[1]), ["web-labels"])

    def test_missing_dashboard_label_and_bad_audience(self):
        labels = web_labels().replace("      - homelab.icon=myservice\n", "").replace(
            "audience=family", "audience=everyone")
        self.compose("apps/myservice/compose.yaml", service(labels=labels))
        out = self.run_lint()[1]
        self.assertEqual(sorted(self.rules(out)), ["web-labels", "web-labels"])
        self.assertTrue(any("homelab.icon" in line for line in out))
        self.assertTrue(any("admin or family" in line for line in out))

    def test_router_service_replaces_loadbalancer(self):
        labels = web_labels().replace("traefik.http.services.myservice.loadbalancer.server.port=80",
                                      "traefik.http.routers.myservice.service=api@internal")
        self.compose("apps/myservice/compose.yaml", service(labels=labels))
        self.assertEqual(self.run_lint()[0], 0)

    def test_host_network_skips_traefik(self):
        labels = "".join(line + "\n" for line in web_labels().splitlines() if "traefik" not in line)
        self.compose("apps/myservice/compose.yaml",
                     service(labels=labels, extra="    network_mode: host\n"))
        self.assertEqual(self.run_lint()[0], 0)

    def test_mapping_labels(self):
        labels = "    labels:\n" + "".join(
            "      " + line.strip()[2:].replace("=", ": ", 1) + "\n"
            for line in web_labels().splitlines()[1:])
        labels = labels.replace("Host(`myservice.lan`)", '"Host(`myservice.lan`)"')
        self.compose("apps/myservice/compose.yaml", service(labels=labels))
        self.assertEqual(self.run_lint()[:2], (0, []))

    def test_non_web_service_needs_no_labels(self):
        self.compose("apps/myservice/compose.yaml", service(labels=""))
        self.assertEqual(self.run_lint()[0], 0)


class TestPorts(LintCase):
    def test_duplicate_port(self):
        self.compose("apps/myservice/compose.yaml", service())
        self.compose("apps/two/compose.yaml", service("two", labels=web_labels("two", 8123)))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out).count("port-unique"), 2)
        self.assertTrue(any("also used by apps/two/compose.yaml (two)" in line for line in out))

    def test_duplicate_seen_when_linting_one_file(self):
        target = self.compose("apps/myservice/compose.yaml", service())
        self.compose("apps/two/compose.yaml", service("two", labels=web_labels("two", 8123)))
        self.assertIn("port-unique", self.rules(self.run_lint(target)[1]))

    def test_port_not_in_table(self):
        self.compose("apps/myservice/compose.yaml", service(labels=web_labels(port=9999)))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["port-table"])
        self.assertIn("not in the CLAUDE.md Ports table", out[0])

    def test_port_listed_for_other_service(self):
        self.compose("apps/myservice/compose.yaml", service(labels=web_labels(port=8124)))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["port-table"])
        self.assertIn("listed for other", out[0])

    def test_dir_name_matches_table(self):
        # The table names the compose dir (e.g. qbittorrent), the label sits on a service in it.
        self.compose("apps/other/compose.yaml", service("other-ui", labels=web_labels("other-ui", 8124)))
        self.assertEqual(self.run_lint()[0], 0)


class TestMounts(LintCase):
    def vol(self, *lines):
        return "    volumes:\n" + "".join(f"      {line}\n" for line in lines)

    def test_sock_outside_proxy(self):
        self.compose("apps/myservice/compose.yaml",
                     service(extra=self.vol(f"- /var/run/{SOCK}:/var/run/{SOCK}:ro")))
        code, out, _ = self.run_lint()
        self.assertEqual(self.rules(out), ["docker-sock"])
        self.assertRegex(out[0], r"compose\.yaml:\d+: docker-sock")

    def test_sock_long_syntax(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- type: bind", f"  source: /var/run/{SOCK}", f"  target: /var/run/{SOCK}")))
        self.assertEqual(self.rules(self.run_lint()[1]), ["docker-sock"])

    def test_sock_in_socket_proxy_ok(self):
        self.compose("core/docker-socket-proxy/compose.yaml", service(
            "docker-socket-proxy", labels="", extra=self.vol(f"- /var/run/{SOCK}:/var/run/{SOCK}:ro")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_media_rw(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- ${MEDIA_PATH}:/mnt/media", "- /mnt/media/tv:/tv")))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["media-ro", "media-ro"])
        self.assertNotEqual(out[0].split(":")[1], out[1].split(":")[1])  # each finding has its own line

    def test_media_ro_ok(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- ${MEDIA_PATH}:/mnt/media:ro", "- /mnt/media/tv:/tv:ro,z")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_media_long_syntax(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- type: bind", "  source: /mnt/media", "  target: /media")))
        self.assertEqual(self.rules(self.run_lint()[1]), ["media-ro"])
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- type: bind", "  source: /mnt/media", "  target: /media", "  read_only: true")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_approval_on_line(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- ${MEDIA_PATH}:/mnt/media  # read-write, approved via the guard")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_approval_in_comment_above(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "# Read-write (approved via the guard): imports hardlink", "# into /mnt/media/movies.",
            "- ${MEDIA_PATH}:/mnt/media")))
        self.assertEqual(self.run_lint()[0], 0)

    def test_approval_does_not_carry_past_a_mount(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "# approved", "- ${MEDIA_PATH}/downloads:/downloads", "- ${MEDIA_PATH}:/mnt/media")))
        out = self.run_lint()[1]
        self.assertEqual(self.rules(out), ["media-ro"])
        self.assertIn("/mnt/media is read-write", out[0])

    def test_other_paths_ignored(self):
        self.compose("apps/myservice/compose.yaml", service(extra=self.vol(
            "- ${APPDATA_PATH}/myservice:/config", "- /mnt/mediaother:/x")))
        self.assertEqual(self.run_lint()[0], 0)


class TestRealRepo(unittest.TestCase):
    def test_runs_on_repo(self):
        p = subprocess.run([sys.executable, LINT], capture_output=True, text=True, timeout=60)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertEqual(p.stderr, "")


if __name__ == "__main__":
    unittest.main()
