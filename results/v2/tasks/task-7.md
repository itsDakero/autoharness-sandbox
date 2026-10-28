Ran the rules-audit checks too: images pinned, no `docker.sock`, `/mnt/media` is `:ro`, the new keys are in `.env.example` only, the port is in the table, the doc is indexed. Beszel isn't a core service, so `.claude/settings.json` doesn't need a change.

## Summary

I added Beszel as `tools/beszel`: the hub (web UI, admin tile) and its agent. All checks pass, but nothing has been started, since there's no server here.

**Versions:** both images are pinned to `0.21.1` (`henrygd/beszel` and `henrygd/beszel-agent`). Docker Hub shows 0.21.1 as the newest numbered tag for both, pushed 2026-10-22. GitHub's releases page and API were blocked from this session, so I confirmed the version on Docker Hub and in the source tree tagged `v0.21.1` instead.

**Docker API through the socket proxy:** I read the agent's source (`agent/docker.go` at v0.21.1). It only makes GET requests:
- `/version` and `/info`
- `/containers/json`
- `/containers/<id>/stats`, `/containers/<id>/json` and `/containers/<id>/logs`

The proxy already allows all of these (`VERSION`, `INFO` and `CONTAINERS` are on), and writes stay blocked. So the proxy needs no change; I only updated its comments. One thing to know: anyone who can log in to Beszel can read container logs, the same as with Dozzle. The agent strips environment variables before sending container details.

**Gaps:**
- **Host network graph is wrong.** The agent has to run on a normal container network to reach the socket proxy, so the server-wide network graph shows only the agent's own traffic, not the host's network cards. Running it on the host network would fix this, but it would mean publishing the proxy on `127.0.0.1`. That would give every host-network container, such as Omada, read access to the Docker API, so I didn't. Per-container network, CPU, memory, disk usage and disk I/O are all correct.
- **Not monitored:** the GPU (needs the separate NVIDIA agent image) and systemd services (needs the host's D-Bus socket). Neither was added.

**What changed:**
- **`tools/beszel/compose.yaml`:**
  - The hub publishes port **8089**. It has Traefik, dashboard and Kuma labels, the log cap, and a healthcheck using its own `health` command (the image has no curl).
  - The agent publishes no port. It has the log cap and the `/agent health` check, and sits on its own `beszel` network plus `socket-proxy` with `DOCKER_HOST=tcp://docker-socket-proxy:2375`.
  - The agent also mounts `/mnt/media` and `/mnt/backup` read-only so their disk usage is graphed.
- **`tools/beszel/README.md`:** how it's wired, the API-versus-proxy table, first start (the agent's key and token come from the hub's "Add system" dialog and go into `.env`), alerts, health and the gaps.
- **`CLAUDE.md`:** a layout line and a ports row for 8089.
- **`.env.example`:** `BESZEL_AGENT_KEY` and `BESZEL_AGENT_TOKEN`. Until they're set, the agent keeps restarting and shows as unhealthy; the hub runs fine.
- **`docs/README.md`:** an index line for the new README.
- **`docs/m1-core.md`:** both healthchecks added to the table, marked "not yet run live".
- **`core/docker-socket-proxy/compose.yaml`:** comments only.

**Checks:**
- `compose-lint.py`: exit 0.
- `docker compose config -q` on `tools/beszel` and the proxy, using a filled-in copy of `.env.example`: both exit 0.
- `scripts/check.sh`: all passed (bash -n, py_compile, shellcheck, compose-lint, 63 unit tests).

**Not done:** nothing has been started, so the healthchecks and the hub-agent connection are untested. Before deploying, it's worth checking that the agent reports correct numbers for the `/mnt/media` and `/mnt/backup` disks. No commit, as asked.

Sources: [Docker Hub henrygd/beszel](https://hub.docker.com/r/henrygd/beszel), [Docker Hub henrygd/beszel-agent](https://hub.docker.com/r/henrygd/beszel-agent), [beszel v0.21.1 source](https://github.com/henrygd/beszel/tree/v0.21.1), [releasealert.dev beszel-agent](https://releasealert.dev/dockerhub/henrygd/beszel-agent)