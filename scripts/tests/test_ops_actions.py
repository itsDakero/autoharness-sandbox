"""Tests for scripts/ops-actions.py decision logic. Docker (dc.sh), Discord, ntfy, syslog and time are mocked;
state files go to a temp dir.

Run: python3 -m unittest discover -s scripts/tests
"""
import gc
import importlib.util
import json
import os
import tempfile
import types
import unittest
import warnings
from pathlib import Path
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "ops-actions.py")
_spec = importlib.util.spec_from_file_location("ops_actions", SCRIPT)
ops = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops)

T0 = 1_800_000_000.0
HOUR, DAY = 3600, 86400


class OpsActionsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        self.clock = [T0]
        self.health = {}  # service -> (state, health); default running/healthy
        self.restarted = []
        self.discord_msgs = []
        self.ntfy_msgs = []
        patches = {
            "STATE_DIR": d, "STATE_FILE": d / "state.json", "AUDIT": d / "audit.jsonl",
            "PAUSE": d / "PAUSE", "LOCK": d / ".lock", "DRY": False,
            "time": types.SimpleNamespace(time=lambda: self.clock[0]),
            "syslog": mock.MagicMock(),
            "health": lambda s, _d: self.health.get(s, ("running", "healthy")),
            "discord": self.discord_msgs.append,
            "ntfy": lambda title, msg: self.ntfy_msgs.append(msg),
            "subprocess": types.SimpleNamespace(run=self._run, TimeoutExpired=TimeoutError,
                                                SubprocessError=Exception),
        }
        for name, val in patches.items():
            p = mock.patch.object(ops, name, val)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, cmd, **_kw):
        self.assertTrue(cmd[0].endswith("scripts/dc.sh"), cmd)
        self.assertEqual(cmd[2], "restart", cmd)
        self.restarted.append(cmd[3])
        return types.SimpleNamespace(returncode=0)

    def run_main(self, dry=False):
        with mock.patch.object(ops, "DRY", dry), mock.patch("sys.argv", ["ops-actions.py"]), \
                warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)  # main() holds .lock open "until exit"
            rc = ops.main()
            gc.collect()
            return rc

    def state(self):
        return json.loads(ops.STATE_FILE.read_text())

    def write_state(self, services):
        ops.STATE_FILE.write_text(json.dumps({"services": services}))

    def audit_rows(self):
        if not ops.AUDIT.exists():
            return []
        return [json.loads(x) for x in ops.AUDIT.read_text().splitlines()]

    # --- streak ---

    def test_unhealthy_once_does_not_restart(self):
        self.health["radarr"] = ("running", "unhealthy")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.state()["services"]["radarr"]["streak"], 1)

    def test_unhealthy_twice_restarts(self):
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.clock[0] += 300
        self.run_main()
        self.assertEqual(self.restarted, ["radarr"])
        rec = self.state()["services"]["radarr"]
        self.assertEqual(rec["streak"], 0)
        self.assertEqual(rec["restarts"], [T0 + 300])
        rows = self.audit_rows()
        self.assertEqual([(r["service"], r["action"], r["result"]) for r in rows], [("radarr", "restart", "ok")])
        self.assertEqual(len(self.discord_msgs), 1)

    def test_healthy_in_between_resets_streak(self):
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.health["radarr"] = ("running", "healthy")
        self.run_main()
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.state()["services"]["radarr"]["streak"], 1)

    def test_unhealthy_but_not_running_is_ignored(self):
        self.write_state({"radarr": {"streak": 5, "restarts": [], "needs_dan": False}})
        self.health["radarr"] = ("exited", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.state()["services"]["radarr"]["streak"], 0)

    def test_health_unknown_keeps_streak(self):
        self.write_state({"radarr": {"streak": 1, "restarts": [], "needs_dan": False}})
        self.health["radarr"] = None
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.state()["services"]["radarr"]["streak"], 1)

    # --- per-service caps ---

    def test_hourly_cap(self):
        self.write_state({"radarr": {"streak": 1, "restarts": [T0 - 30 * 60], "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertTrue(self.state()["services"]["radarr"]["needs_dan"])
        self.assertEqual(len(self.discord_msgs), 1)
        self.assertIn("needs Dan", self.discord_msgs[0])
        self.assertEqual(self.audit_rows()[0]["result"], "cap reached")
        # "needs Dan" is sent only once while it stays unhealthy
        self.clock[0] += 300
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertEqual(len(self.discord_msgs), 1)

    def test_restart_allowed_after_an_hour(self):
        self.write_state({"radarr": {"streak": 1, "restarts": [T0 - HOUR - 1], "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, ["radarr"])

    def test_daily_cap(self):
        old = [T0 - 5 * HOUR, T0 - 4 * HOUR, T0 - 2 * HOUR]
        self.write_state({"radarr": {"streak": 1, "restarts": old, "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertTrue(self.state()["services"]["radarr"]["needs_dan"])

    def test_daily_cap_window_expires(self):
        old = [T0 - DAY - 1, T0 - 4 * HOUR, T0 - 2 * HOUR]
        self.write_state({"radarr": {"streak": 1, "restarts": old, "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, ["radarr"])
        self.assertEqual(len(self.state()["services"]["radarr"]["restarts"]), 3)

    def test_needs_dan_resets_when_healthy(self):
        self.write_state({"radarr": {"streak": 3, "restarts": [T0 - 60], "needs_dan": True}})
        self.run_main()
        self.assertFalse(self.state()["services"]["radarr"]["needs_dan"])

    # --- global breaker / PAUSE ---

    def three_recent_restarts(self):
        return {s: {"streak": 0, "restarts": [T0 - 10 * 60], "needs_dan": False}
                for s in ("prowlarr", "sonarr", "seerr")}

    def test_breaker_writes_pause_on_fourth(self):
        st = self.three_recent_restarts()
        st["radarr"] = {"streak": 1, "restarts": [], "needs_dan": False}
        self.write_state(st)
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertTrue(ops.PAUSE.exists())
        self.assertIn("breaker", ops.PAUSE.read_text())
        self.assertEqual(len(self.ntfy_msgs), 1)
        self.assertTrue(any("breaker tripped" in m for m in self.discord_msgs))
        self.assertEqual(self.audit_rows()[-1]["action"], "pause")

    def test_breaker_stops_the_run(self):
        # radarr trips the breaker; later registry entries are not acted on in the same run
        st = self.three_recent_restarts()
        st["radarr"] = {"streak": 1, "restarts": [], "needs_dan": False}
        st["books"] = {"streak": 1, "restarts": [], "needs_dan": False}
        self.write_state(st)
        self.health["radarr"] = ("running", "unhealthy")
        self.health["books"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.state()["services"]["books"]["streak"], 1)

    def test_two_recent_restarts_do_not_trip_breaker(self):
        st = {s: {"streak": 0, "restarts": [T0 - 10 * 60], "needs_dan": False} for s in ("prowlarr", "sonarr")}
        st["radarr"] = {"streak": 1, "restarts": [], "needs_dan": False}
        self.write_state(st)
        self.health["radarr"] = ("running", "unhealthy")
        self.run_main()
        self.assertEqual(self.restarted, ["radarr"])
        self.assertFalse(ops.PAUSE.exists())

    def test_pause_stops_everything(self):
        ops.PAUSE.write_text("manual\n")
        self.write_state({"radarr": {"streak": 5, "restarts": [], "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.discord_msgs, [])
        self.assertEqual(self.state()["services"]["radarr"]["streak"], 5)  # state untouched

    # --- never-list / core ---

    def test_registry_has_no_core_or_never_services(self):
        for name, d in ops.REGISTRY.items():
            self.assertFalse(d.startswith("core/"), name)
            self.assertNotIn(name, ops.NEVER)

    def test_core_service_in_registry_refuses_to_run(self):
        self.health["adguard"] = ("running", "unhealthy")
        self.write_state({"adguard": {"streak": 5, "restarts": [], "needs_dan": False}})
        with mock.patch.dict(ops.REGISTRY, {"adguard": "core/adguard"}):
            self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.restarted, [])

    def test_never_service_in_registry_refuses_to_run(self):
        with mock.patch.dict(ops.REGISTRY, {"gluetun": "media/qbittorrent"}):
            self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.restarted, [])

    def test_unregistered_core_service_is_never_checked(self):
        checked = []
        with mock.patch.object(ops, "health", lambda s, _d: checked.append(s) or ("running", "unhealthy")):
            self.run_main()
            self.run_main()
        self.assertTrue(set(checked) <= set(ops.REGISTRY))
        self.assertFalse({"adguard", "traefik", "uptime-kuma", "gluetun", "qbittorrent", "hermes"} & set(checked))
        self.assertFalse(any(ops.REGISTRY[s].startswith("core/") for s in self.restarted))

    # --- dry run ---

    def test_dry_run_never_restarts_or_writes(self):
        self.write_state({"radarr": {"streak": 1, "restarts": [], "needs_dan": False}})
        before = ops.STATE_FILE.read_text()
        self.health["radarr"] = ("running", "unhealthy")
        with mock.patch("builtins.print"):
            self.assertEqual(self.run_main(dry=True), 0)
        self.assertEqual(self.restarted, [])
        self.assertEqual(self.discord_msgs, [])
        self.assertEqual(ops.STATE_FILE.read_text(), before)
        self.assertFalse(ops.AUDIT.exists())
        self.assertFalse(ops.LOCK.exists())

    def test_dry_run_breaker_does_not_write_pause(self):
        st = self.three_recent_restarts()
        st["radarr"] = {"streak": 1, "restarts": [], "needs_dan": False}
        self.write_state(st)
        self.health["radarr"] = ("running", "unhealthy")
        with mock.patch("builtins.print") as pr:
            self.run_main(dry=True)
        self.assertFalse(ops.PAUSE.exists())
        self.assertEqual(self.ntfy_msgs, [])
        self.assertTrue(any("would write PAUSE" in str(c) for c in pr.call_args_list))

    def test_dry_run_cap_does_not_send(self):
        self.write_state({"radarr": {"streak": 1, "restarts": [T0 - 60], "needs_dan": False}})
        self.health["radarr"] = ("running", "unhealthy")
        with mock.patch("builtins.print"):
            self.run_main(dry=True)
        self.assertEqual(self.discord_msgs, [])
        self.assertEqual(self.restarted, [])


if __name__ == "__main__":
    unittest.main()
