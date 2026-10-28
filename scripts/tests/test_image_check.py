"""Tests for scripts/image-check.py tag parsing, comparison and patch/minor/major classification.
All network (http_json, registries, GitHub) is mocked.

Run: python3 -m unittest discover -s scripts/tests
"""
import importlib.util
import os
import unittest
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "image-check.py")
_spec = importlib.util.spec_from_file_location("image_check", SCRIPT)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


class NoNetwork(unittest.TestCase):
    """Any unmocked network call fails the test."""

    def setUp(self):
        for target in ("urllib.request.urlopen",):
            p = mock.patch(target, side_effect=AssertionError(f"network: {target}"))
            p.start()
            self.addCleanup(p.stop)


class SplitRefTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(ic.split_ref("traefik:v3.7.14"), ("traefik", "v3.7.14"))
        self.assertEqual(ic.split_ref("ghcr.io/analogj/scrutiny:v0.9.5-omnibus"),
                         ("ghcr.io/analogj/scrutiny", "v0.9.5-omnibus"))

    def test_digest_dropped(self):
        ref = "ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:" + "ab" * 32
        self.assertEqual(ic.split_ref(ref), ("ghcr.io/immich-app/postgres", "14-vectorchord0.4.3-pgvectors0.2.0"))

    def test_docker_io_prefix(self):
        self.assertEqual(ic.split_ref("docker.io/valkey/valkey:9.0.7"), ("valkey/valkey", "9.0.7"))
        self.assertEqual(ic.split_ref("docker.io/library/redis:7.4.5-alpine"), ("redis", "7.4.5-alpine"))


class ParseTest(unittest.TestCase):
    def test_skeleton(self):
        cases = {
            "v3.7.14": "vN.N.N",
            "2.5.6-rootless": "N.N.N-rootless",
            "version-1.2.3": "version-N.N.N",
            "7.4.5-alpine": "N.N.N-alpine",
            "1.25-alpine3.19": "N.N-alpineN.N",
            "6.4.4.10685-ls318": "N.N.N.N-lsN",
            "5.2.4_v2.0.15-ls479": "N.N.N_vN.N.N-lsN",
            "12.2.20261005-225228": "N.N.N-N",
            "2024.01.15": "N.N.N",
            "latest": "latest",
        }
        for tag, sk in cases.items():
            self.assertEqual(ic.skeleton(tag), sk, tag)

    def test_flavours_differ(self):
        self.assertNotEqual(ic.skeleton("v1.2.3"), ic.skeleton("1.2.3"))
        self.assertNotEqual(ic.skeleton("1.2.3"), ic.skeleton("1.2.3-alpine"))
        self.assertNotEqual(ic.skeleton("1.2.3"), ic.skeleton("1.2.3-rc1"))
        self.assertNotEqual(ic.skeleton("1.2.3"), ic.skeleton("1.2.3.4"))

    def test_nums(self):
        self.assertEqual(ic.nums("v3.7.14"), (3, 7, 14))
        self.assertEqual(ic.nums("version-1.2.3"), (1, 2, 3))
        self.assertEqual(ic.nums("6.4.4.10685-ls318"), (6, 4, 4, 10685, 318))
        self.assertEqual(ic.nums("2024.01.15"), (2024, 1, 15))
        self.assertEqual(ic.nums("latest"), ())

    def test_nums_order_is_numeric_not_lexical(self):
        self.assertGreater(ic.nums("1.10.0"), ic.nums("1.9.9"))
        self.assertGreater(ic.nums("v3.7.14"), ic.nums("v3.7.9"))
        self.assertGreater(ic.nums("4.6.3-ls100"), ic.nums("4.6.3-ls99"))
        self.assertGreater(ic.nums("2024.10.01"), ic.nums("2024.9.30"))

    def test_upstream(self):
        cases = {
            "v3.7.14": "3.7.14",
            "1.2.3": "1.2.3",
            "version-1.2.3": "1.2.3",
            "version-v1.2.3": "1.2.3",
            "7.4.5-alpine": "7.4.5",
            "6.4.4.10685-ls318": "6.4.4.10685",
            "5.2.4_v2.0.15-ls479": "5.2.4",
            "v0.9.5-omnibus": "0.9.5",
            "latest": "",
        }
        for tag, up in cases.items():
            self.assertEqual(ic.upstream(tag), up, tag)


class KindTest(unittest.TestCase):
    def k(self, a, b):
        return ic.kind(ic.nums(a), ic.nums(b))

    def test_semver(self):
        self.assertEqual(self.k("1.2.3", "1.2.4"), "patch")
        self.assertEqual(self.k("1.2.3", "1.3.0"), "minor")
        self.assertEqual(self.k("1.2.3", "2.0.0"), "major")
        self.assertEqual(self.k("v0.107.79", "v0.108.0"), "minor")
        self.assertEqual(self.k("version-1.2.3", "version-1.2.4"), "patch")

    def test_suffixes(self):
        self.assertEqual(self.k("2.5.6-rootless", "2.5.7-rootless"), "patch")
        self.assertEqual(self.k("7.4.5-alpine", "7.5.0-alpine"), "minor")
        self.assertEqual(self.k("4.0.20-ls326", "4.0.20-ls327"), "build")
        self.assertEqual(self.k("4.0.20-ls326", "4.0.21-ls327"), "patch")

    def test_four_part(self):
        self.assertEqual(self.k("6.2.14.11", "6.2.14.12"), "build")
        self.assertEqual(self.k("6.2.14.11", "6.2.15.1"), "patch")
        self.assertEqual(self.k("6.4.4.10685-ls318", "6.5.0.10700-ls319"), "minor")

    def test_short_and_dates(self):
        self.assertEqual(self.k("14", "15"), "major")
        self.assertEqual(self.k("1.25", "1.26"), "minor")
        self.assertEqual(self.k("2024.01.15", "2024.02.01"), "minor")
        self.assertEqual(self.k("2024.12.31", "2025.01.01"), "major")
        self.assertEqual(self.k("12.2.20261005-225228", "12.2.20261012-101010"), "patch")


class PatchBumpTest(unittest.TestCase):
    def test_true(self):
        self.assertTrue(ic.is_patch_bump("1.2.3", "1.2.4"))
        self.assertTrue(ic.is_patch_bump("v3.7.14", "v3.7.15"))
        self.assertTrue(ic.is_patch_bump("2.5.6-rootless", "2.5.10-rootless"))
        self.assertTrue(ic.is_patch_bump("7.4.5-alpine", "7.4.6-alpine"))

    def test_minor_major_or_older(self):
        self.assertFalse(ic.is_patch_bump("1.2.3", "1.3.0"))
        self.assertFalse(ic.is_patch_bump("1.2.3", "2.0.0"))
        self.assertFalse(ic.is_patch_bump("1.2.4", "1.2.3"))
        self.assertFalse(ic.is_patch_bump("1.2.3", "1.2.3"))

    def test_flavour_mismatch(self):
        self.assertFalse(ic.is_patch_bump("v1.2.3", "1.2.4"))
        self.assertFalse(ic.is_patch_bump("1.2.3", "v1.2.4"))
        self.assertFalse(ic.is_patch_bump("1.2.3-alpine", "1.2.4"))
        self.assertFalse(ic.is_patch_bump("1.2.3-alpine", "1.2.4-slim"))

    def test_not_strict_semver(self):
        for cur, new in [
            ("version-1.2.3", "version-1.2.4"),
            ("6.2.14.11", "6.2.14.12"),
            ("6.2.14.11", "6.2.15.0"),
            ("6.4.4.10685-ls318", "6.4.5.10700-ls319"),
            ("1.2.3-ls10", "1.2.4-ls11"),  # -lsN changes every build: suffix differs
            ("1.25-alpine3.19", "1.25-alpine3.20"),
            ("2024.01.15", "2024.01.16"),
            ("12.2.20261005-225228", "12.2.20261006-1"),
            ("1.2.3-RC", "1.2.4-RC"),
            ("latest", "1.2.3"),
        ]:
            self.assertFalse(ic.is_patch_bump(cur, new), (cur, new))


class SlugTest(unittest.TestCase):
    def test_bump_slug(self):
        self.assertEqual(ic.bump_slug("seerr", "v3.5.2"), "bump-seerr-v3-5-2")
        self.assertEqual(ic.bump_slug("uptime-kuma", "2.5.7-rootless"), "bump-uptime-kuma-2-5-7-rootless")
        long = ic.bump_slug("x" * 60, "1.2.3")
        self.assertLessEqual(len(long), 50)
        self.assertFalse(long.endswith("-"))


class CandidatesTest(NoNetwork):
    def run_hub(self, ref, tags):
        with mock.patch.object(ic, "hub_tags", return_value=tags) as hub:
            out = ic.candidates(ref)
        return out, hub

    def test_same_flavour_newer_sorted(self):
        tags = ["v3.7.9", "v3.7.15", "v3.7.14", "v3.8.0", "v3.10.0", "3.7.20", "latest", "v3.8.0-rc1", "v3.7.15"]
        (name, cands), hub = self.run_hub("traefik:v3.7.14", tags)
        self.assertEqual(name, "traefik")
        self.assertEqual(cands, ["v3.7.15", "v3.8.0", "v3.10.0"])
        hub.assert_called_once_with("traefik", "v3.7.14")

    def test_ls_suffix(self):
        tags = ["6.4.4.10685-ls318", "6.4.4.10685-ls319", "6.4.5.10700-ls320", "6.4.5.10700", "develop-6.5.0.1-ls1"]
        (_, cands), _ = self.run_hub("linuxserver/radarr:6.4.4.10685-ls318", tags)
        self.assertEqual(cands, ["6.4.4.10685-ls319", "6.4.5.10700-ls320"])

    def test_version_prefix(self):
        tags = ["version-1.2.3", "version-1.2.10", "version-1.10.0", "1.2.4"]
        (_, cands), _ = self.run_hub("linuxserver/foo:version-1.2.3", tags)
        self.assertEqual(cands, ["version-1.2.10", "version-1.10.0"])

    def test_alpine_suffix(self):
        tags = ["7.4.5-alpine", "7.4.6-alpine", "7.4.6", "8.0.0-alpine3.21", "7.4.6-alpine3.21"]
        (_, cands), _ = self.run_hub("redis:7.4.5-alpine", tags)
        self.assertEqual(cands, ["7.4.6-alpine"])

    def test_docker_io_and_lowercase(self):
        (name, cands), hub = self.run_hub("docker.io/valkey/valkey:9.0.7", ["9.0.8", "9.0.7"])
        self.assertEqual((name, cands), ("valkey/valkey", ["9.0.8"]))
        hub.assert_called_once_with("valkey/valkey", "9.0.7")

    def test_no_flavour_raises(self):
        with self.assertRaises(ValueError):
            self.run_hub("foo/bar:1.2.3", ["latest", "v1.2.4"])

    def test_ghcr_with_digest(self):
        cur = "14-vectorchord0.4.3-pgvectors0.2.0"
        ref = f"ghcr.io/Immich-App/postgres:{cur}@sha256:" + "cd" * 32
        tags = [cur, "14-vectorchord0.4.4-pgvectors0.2.0", "15-vectorchord0.4.3-pgvectors0.2.0", "14"]
        with mock.patch.object(ic, "ghcr_tags", return_value=tags) as gh:
            name, cands = ic.candidates(ref)
        gh.assert_called_once_with("Immich-App/postgres")
        self.assertEqual(name, "immich-app/postgres")
        self.assertEqual(cands, ["14-vectorchord0.4.4-pgvectors0.2.0", "15-vectorchord0.4.3-pgvectors0.2.0"])


class RegistryTest(NoNetwork):
    def test_hub_url_and_paging(self):
        pages = [
            (200, {"results": [{"name": "latest"}], "next": "https://hub/next"}, {}),
            (200, {"results": [{"name": "9.0.8"}], "next": "https://hub/next2"}, {}),
        ]
        with mock.patch.object(ic, "http_json", side_effect=pages) as hj:
            self.assertEqual(ic.hub_tags("valkey/valkey", "9.0.7"), ["latest", "9.0.8"])
        first = hj.call_args_list[0].args[0]
        self.assertTrue(first.startswith("https://hub.docker.com/v2/repositories/valkey/valkey/tags?"), first)
        self.assertEqual(hj.call_args_list[1].args[0], "https://hub/next")
        self.assertEqual(hj.call_count, 2)

    def test_hub_official_image(self):
        with mock.patch.object(ic, "http_json", return_value=(200, {"results": [], "next": None}, {})) as hj:
            ic.hub_tags("redis", "7.4.5-alpine")
        self.assertIn("/repositories/library/redis/tags", hj.call_args.args[0])

    def test_registry_url(self):
        self.assertEqual(ic.registry_url("redis:7.4.5-alpine"), "https://hub.docker.com/_/redis")
        self.assertEqual(ic.registry_url("docker.io/valkey/valkey:9.0.7"),
                         "https://hub.docker.com/r/valkey/valkey/tags")
        self.assertEqual(ic.registry_url("ghcr.io/immich-app/postgres:14@sha256:" + "ab" * 32),
                         "https://github.com/immich-app/postgres/pkgs/container/postgres")


class SecurityTagsTest(NoNetwork):
    def gh(self, rels):
        g = ic.GitHub({"github": {}})
        g.releases = mock.Mock(return_value=rels)
        return g

    RELS = [
        {"tag": "v1.2.4", "pre": False, "sec": True},
        {"tag": "v1.2.5", "pre": False, "sec": False},
        {"tag": "v1.2.6-rc1", "pre": True, "sec": True},
        {"tag": "v1.2.3", "pre": False, "sec": True},
        {"tag": "v1.3.0", "pre": False, "sec": True},
    ]

    def test_range(self):
        with mock.patch.dict(ic.GITHUB, {"x/y": "X/Y"}):
            sec, note = ic.security_tags(self.gh(self.RELS), "x/y", "v1.2.3", "v1.2.6")
        self.assertEqual((sec, note), (["v1.2.4"], ""))

    def test_version_prefix_and_ls_suffix(self):
        with mock.patch.dict(ic.GITHUB, {"x/y": "X/Y"}):
            g = self.gh(self.RELS)
            self.assertEqual(ic.security_tags(g, "x/y", "version-1.2.3", "version-1.2.6"), (["v1.2.4"], ""))
            g.releases.assert_called_once_with("X/Y")
            g = self.gh(self.RELS)
            self.assertEqual(ic.security_tags(g, "x/y", "1.2.3-ls10", "1.2.6-ls14"), (["v1.2.4"], ""))

    def test_build_only_bump_skips_lookup(self):
        with mock.patch.dict(ic.GITHUB, {"x/y": "X/Y"}):
            g = self.gh(self.RELS)
            self.assertEqual(ic.security_tags(g, "x/y", "1.2.3-ls10", "1.2.3-ls11"), ([], ""))
            g.releases.assert_not_called()

    def test_unknown_repo_and_rate_limit(self):
        self.assertEqual(ic.security_tags(self.gh([]), "nope/nope", "1.0.0", "1.0.1"), ([], "notes not checked"))
        g = ic.GitHub({"github": {}})
        g.releases = mock.Mock(side_effect=ic.RateLimited())
        with mock.patch.dict(ic.GITHUB, {"x/y": "X/Y"}):
            self.assertEqual(ic.security_tags(g, "x/y", "1.0.0", "1.0.1"),
                             ([], "notes not checked (GitHub rate limit)"))


class ProposalTextTest(unittest.TestCase):
    def test_note(self):
        text = ic.proposal_text("louislam/uptime-kuma:2.5.6-rootless", ["uptime-kuma"],
                                ["tools/kuma/compose.yaml"], "2.5.6-rootless", "2.5.7-rootless",
                                "louislam/uptime-kuma", ["2.5.7", "nonsemver-1"])
        self.assertIn("# Bump uptime-kuma to 2.5.7-rootless (patch)", text)
        self.assertIn("Risk: 1    (patch bump within 2.5, same tag flavour)", text)
        self.assertIn("Release notes mention security: 2.5.7.", text)
        self.assertIn("`2.5.6-rootless` -> `2.5.7-rootless`", text)
        self.assertIn("https://github.com/louislam/uptime-kuma/releases", text)
        self.assertIn("scripts/dc.sh tools/kuma config -q", text)


if __name__ == "__main__":
    unittest.main()
