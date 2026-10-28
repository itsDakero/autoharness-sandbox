# Observed Bash permission refusals

From one episode where a cron-script change was written but could not be tested.

| reasonCode | Trigger | Fix |
|---|---|---|
| cd-compound-read | `cd DIR && cat relative/file` | absolute path, Read tool |
| assigned-variable | `S=...; cmd $S` in one call | inline the literal path |
| too-complex | `mkdir && cd && openssl ... & ... ; cmd` (many parts) | one step per call |
| multi-cd | two `cd` in one call | absolute paths |
| no-rule-match | `bash -n X && echo ok` (a compound with an unmatched part) | split the parts |
| subcommands:* | any part of a compound fails the match | run the parts separately |

The refusals block the whole call, not just the risky part, so one bad part costs every step in it.
