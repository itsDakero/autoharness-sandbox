A shellcheck directive only covers the next command, not the rest of a line. So in `backup.sh` and `core-up.sh` I split `set -a; . file; set +a` into separate lines. In `secret-scan.sh` I put `trap` on its own line, and in both `scan_ok`s I split the `echo …; sed …` line in two.

scripts/loop.sh:20:1: note: This function can't be invoked via tmux on line 24. [SC2032]
scripts/loop.sh:24:10: warning: Shell functions can't be passed to external commands. Use separate script or sh -c. [SC2033]

scripts/idea.sh:56:12: warning: Use semicolon or linefeed before 'done' (or quote to make it literal). [SC1010]
scripts/deploy-idea.sh:246:18: note: Note that A && B || C is not if-then-else. C may run when A is true. [SC2015]