# Autoharness sandbox — report

## Status: blocked before task 1

No tasks were run. The plugin never got installed.

## What happened

- `claude -p` works in this container (test prompt returned `OK`, exit 0).
- `claude plugin list`: no plugins installed.
- The repo settings enable `autoharness@autoharness`, but that does not install it.
- I tried `claude plugin marketplace add tigerless-labs/autoharness`
  and `claude plugin install autoharness@autoharness --scope project`.
- The session's auto-mode permission check denied it.
  Reason given: "Untrusted Code Integration" (third-party plugin code with hooks).
- I did not try to work around that. Installing it another way would defeat the check.

## What Dan needs to decide

Pick one:

- **Run it locally.** On your own machine, in a clone of this repo:
  install the plugin yourself, then run the 15 tasks from `SANDBOX.md`.
- **Allow it here.** Add a permission rule for `claude plugin` commands
  in this environment (or approve the install when asked), then re-run this session.
- **Pre-install it.** Put the install in the cloud environment's setup script,
  so the plugin is already there when the session starts.

## Results so far

- Skills created/changed/archived: none (plugin not installed).
- Background `claude -p` runs by the plugin: 0.
- `claude -p` runs by me: 1 (the smoke test, run outside the repo).
- Nothing unsafe happened.
