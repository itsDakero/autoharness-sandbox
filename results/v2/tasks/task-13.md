I added `scripts/tests/test_image_check.py` with 32 tests. Writing them turned up three real bugs in `scripts/image-check.py`, which I fixed. All tests pass on the fixed script; on the original script, 8 of them fail.

**Bugs fixed:**
1. **Images pinned by digest couldn't be checked.** The script split the image name from its tag at the last `:`. For `ghcr.io/immich-app/postgres:14-…@sha256:bcf…` that is the colon inside the digest, so the "tag" came out as the hex hash and the lookup went to a bogus registry path. Every weekly run reported "couldn't check". `split_ref` now drops the `@sha256:…` part first.
2. **Images written as `docker.io/...` couldn't be checked.** `docker.io/valkey/valkey:9.0.7` produced the Docker Hub lookup URL `/v2/repositories/docker.io/valkey/valkey/tags`, which fails. That also broke the GitHub release-notes match and the Hub link in proposal notes. `split_ref` now strips `docker.io/` (and `library/`).
3. **The security check silently skipped `version-1.2.3` tags.** It used `tag.lstrip("v")`, which turned `version-1.2.3` into `ersion-1.2.3`, so no version number was found. The release-notes security check was then skipped with no "not checked" note. `upstream()` now takes the first dotted number in the tag. Results for the tags currently in use (`v…`, `-lsN`, `_v…`, `-omnibus`) don't change.

**One behaviour change:** zero-padded date tags like `2024.01.15` → `2024.01.16` matched the strict semver pattern and would have got a Risk 1 "patch" note. Real semver doesn't allow leading zeros, so the pattern now rejects them, and I updated the script's help text to say so. Date tags without zeros (`2024.1.16`) still match. No image in the repo uses date tags today.

**What the tests cover:**
- **Tag parsing:** splitting image from tag; turning a tag into its numbers and its pattern, so only tags of the same style are compared (`version-` prefix, `-alpine`, `-alpine3.19`, `-ls123`, `5.2.4_v2.0.15-ls479`, Jellyfin's date-style tags, four-part versions, `latest`); comparing numbers as numbers rather than text.
- **Classification:** patch, minor, major or build across semver, suffixed, four-part, short and date tags.
- **Patch-note rule:** which bumps get a Risk 1 note, and which are refused (different prefix or suffix, not strict semver, older or same version).
- **Lookups and outputs:**
  - Finding newer tags: Docker Hub and GHCR responses are mocked, including the digest-pinned case.
  - Docker Hub lookup URL and paging.
  - Registry links.
  - Security tags from GitHub release notes, including rate limits and skipping builds with no version change.
  - The proposal note's wording.

Any unmocked network call fails the test.

**Checks:** `scripts/check.sh` passes all steps (bash -n, py_compile, shellcheck, compose-lint, service-catalog, 126 unit tests), and `image-check.py --help` still works.

**Not done:**
- Tags with `-lsN` suffixes (all the linuxserver images) never get a patch note, because the build number changes with every release. The script's help text says this is intended, so I left it and only pinned it in a test. Relaxing it would be a separate decision.
- I didn't commit, as instructed. The `.claude/autoharness/` entries in `git status` come from the harness, not from me.