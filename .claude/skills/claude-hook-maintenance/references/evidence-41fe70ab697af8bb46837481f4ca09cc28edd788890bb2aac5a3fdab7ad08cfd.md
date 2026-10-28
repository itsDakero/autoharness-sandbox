== bad
compose-check: warning: no .env or docker, skipped config -q and the image/docker.sock check
compose-check: tools/zz-test/compose.yaml
tools/zz-test/compose.yaml:4: image-pinned: zz-test: homelab/zz-test:latest uses :latest (pin an exact version)
tools/zz-test/compose.yaml:38: port-unique: zz-test: homelab.port=8090 also used by tools/books/compose.yaml (books)
rc=2
== no-pyyaml
compose-check: warning: no .env or docker, skipped config -q and the image/docker.sock check
compose-check: warning: PyYAML missing (apt install python3-yaml), lint skipped
rc=0
== no-script
compose-check: warning: scripts/compose-lint.py missing, lint skipped
rc=0
"StopFailure": [ { "matcher": "*", "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh" } ] } ]