"""Tests for scripts/service-catalog.py, run as a CLI against small temp repos.

Run: python3 -m unittest discover -s scripts/tests
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

CATALOG = os.path.join(os.path.dirname(__file__), "..", "service-catalog.py")

CLAUDE_MD = """\
# Homelab
## Ports
| Port | Service |
|---|---|
| 53 | dns (DNS) |
| 8123 | web |
| 8124 | other (note) |
## Next
"""

WEB = """\
services:
  web:
    image: example/web:1.0
    labels:
      - homelab.name=Web
      - homelab.group=Tools
      - homelab.icon=web
      - homelab.audience=family
      - homelab.description=A web | app
      - homelab.port=8123
  web-db:
    image: example/db:2.0
"""

OTHER = """\
services:
  other:
    image: example/other:1.0
    ports:
      - "53:53/udp"
    labels:
      homelab.name: Other
      homelab.group: Infrastructure
      homelab.audience: admin
      homelab.description: Something else
      homelab.port: "8124"
      homelab.external.box.name: Box
      homelab.external.box.group: Infrastructure
      homelab.external.box.audience: admin
      homelab.external.box.description: Outside Docker
  dns:
    image: example/dns:1.0
    ports:
      - "53:53/tcp"
"""


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.write("CLAUDE.md", CLAUDE_MD)
        self.write("tools/web/compose.yaml", WEB)
        self.write("core/other/compose.yaml", OTHER)
        self.write("templates/compose.yaml", "services:\n  tpl:\n    labels: [homelab.port=1]\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CATALOG, "--root", self.root, *args],
                              capture_output=True, text=True)

    def services_md(self):
        with open(os.path.join(self.root, "docs", "services.md"), encoding="utf-8") as f:
            return f.read()

    def test_generate(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        md = self.services_md()
        self.assertIn("## Tools", md)
        self.assertIn("## Infrastructure", md)
        self.assertLess(md.index("## Infrastructure"), md.index("## Tools"))
        self.assertIn("| Web | `tools/web/compose.yaml` | 8123 | family | A web \\| app |", md)
        self.assertIn("| Other | `core/other/compose.yaml` | 8124 | admin | Something else |", md)
        self.assertIn("| Box | `core/other/compose.yaml` (external `box`) | - | admin | Outside Docker |", md)
        self.assertIn("- `core/other/compose.yaml`: dns", md)
        self.assertIn("- `tools/web/compose.yaml`: web-db", md)
        self.assertNotIn("tpl", md)

    def test_check_clean_after_generate(self):
        self.run_cli()
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_check_missing_file(self):
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale: docs/services.md is missing", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "services.md")))

    def test_check_stale(self):
        self.run_cli()
        self.write("tools/web/compose.yaml", WEB.replace("A web | app", "Changed"))
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale:", r.stdout)

    def test_check_missing_port_row(self):
        self.write("CLAUDE.md", CLAUDE_MD.replace("| 8123 | web |\n", ""))
        self.run_cli()
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing: tools/web/compose.yaml homelab.port=8123", r.stdout)

    def test_check_wrong_service(self):
        self.write("CLAUDE.md", CLAUDE_MD.replace("| 8123 | web |", "| 8123 | nope |"))
        self.run_cli()
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("service: CLAUDE.md Ports row 8123 names 'nope'", r.stdout)

    def test_check_extra_row(self):
        self.write("CLAUDE.md", CLAUDE_MD.replace("## Next", "| 9000 | gone |\n| 9001 | web |\n## Next"))
        self.run_cli()
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("extra: CLAUDE.md Ports row 9000 names 'gone'", r.stdout)
        self.assertIn("extra: CLAUDE.md Ports row 9001 (web)", r.stdout)
        # 53 is published by dns, so it is not extra
        self.assertNotIn("row 53", r.stdout)

    def test_host_network_row_allowed(self):
        self.write("core/omada/compose.yaml", "services:\n  omada:\n    image: x/omada:1\n"
                                              "    network_mode: host\n")
        self.write("CLAUDE.md", CLAUDE_MD.replace("## Next", "| 8043 | omada UI |\n## Next"))
        self.run_cli()
        r = self.run_cli("--check")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_usage_errors(self):
        r = self.run_cli("--bogus")
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, CATALOG, "--root", os.path.join(self.root, "nope")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_help(self):
        r = subprocess.run([sys.executable, CATALOG, "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage: scripts/service-catalog.py", r.stdout)


if __name__ == "__main__":
    unittest.main()
