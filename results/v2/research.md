# Research list (run 2)

Read only. Nothing here was installed or run, except the autoharness plugin.

| Name | URL | What it does | Used? | Bring to real homelab? |
|---|---|---|---|---|
| awesome-claude-code | https://github.com/hesreallyhim/awesome-claude-code | Big list of Claude Code skills, hooks, plugins | Browsed for ideas | Worth a skim now and then |
| hookify (Anthropic plugin) | https://github.com/anthropics/claude-plugins-official/tree/main/plugins/hookify | Hook rules as small markdown files (`.claude/hookify.*.local.md`); warn/block on bash, file, stop events | Idea borrowed: Stop-hook check (task 14) | Maybe. The guard does the blocking already; the "remind before stop" idea is the useful bit |
| claude-md-management (Anthropic plugin) | https://github.com/anthropics/claude-plugins-official | Audits and trims CLAUDE.md | Idea borrowed: move the scripts list out of CLAUDE.md (task 10) | Yes, the idea. CLAUDE.md loads every session |
| code-review / commit-commands / claude-security (Anthropic plugins) | https://github.com/anthropics/claude-plugins-official | PR review, git commit flow, vuln scan | No (built-in `/code-review`, `/security-review` already exist) | No |
| claude-code-security-review | https://github.com/anthropics/claude-code-security-review | GitHub Action: security review of PR diffs | No | Maybe, if PRs are used |
| DCLint | https://github.com/zavoloklom/docker-compose-linter | Lints compose files (Node) | Idea borrowed: own rule checker (task 1) | No; our own checker knows homelab rules |
| compose-lint | https://github.com/tmatens/compose-lint | Security-focused compose linter (Python + PyYAML) | Idea borrowed (task 1) | No |
| Beszel | https://github.com/henrygd/beszel | Light hub+agent monitor: per-container CPU/RAM/net history, SMART, alerts | Yes, as a service (task 7) | Yes. Fills the "which container eats RAM" gap Kuma can't |
| Immich | https://immich.app/ | Family photo/video backup from phones | Yes, as a service (task 8) | Yes, high family value. Heavy (Postgres + ML) |
| Vaultwarden | https://github.com/dani-garcia/vaultwarden | Bitwarden-compatible password server | No: clients need HTTPS, homelab is HTTP only | Later, after HTTPS |
| Backrest | https://github.com/garethgeorge/backrest | Web UI for restic | No | Maybe; a restore drill (task 6) covers the main need |
| Restore drill guide | https://simeononsecurity.com/articles/homelab-backup-restore-drill/ | Restore into an empty dir, time it, check RPO | Idea borrowed (task 6) | Yes |
| restic `restore --verify` | https://manpages.debian.org/testing/restic/restic-restore.1 | Verifies restored file contents | Used in task 6 | Yes |
| Healthchecks | https://healthchecks.io/ | Dead-man pings for cron jobs | No; Kuma push monitors already do this | No |
| Karakeep / linkding | https://karakeep.app/ , https://linkding.link/ | Bookmarks | No (linkding removed in run 1) | No |
| OliveTin | https://www.olivetin.app/ | Web buttons for shell commands | No | No; the dashboard already has action buttons |
| Gatus | (search results) | Status checks as config | No; Kuma covers it | No |
| Renovate presets for compose | https://gitea.rknet.org/github/renovate-presets | Image update PRs | No; `image-check.py` covers it | No |
| EZ-Homelab | https://gitea.kelinreij.duckdns.org/kelin/EZ-Homelab | Example homelab compose repo | Compared; nothing new | No |
| Docker Homelab skill (itlackey) | claudskills.com (host blocked by the network policy) | SKILL.md for compose stacks | Could not read | Unknown |
