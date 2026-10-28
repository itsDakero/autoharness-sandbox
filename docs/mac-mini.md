# Mac mini: headless model server (M6 stage C)

Mac mini M2, 16 GB. On 24/7, headless, serving Ollama to the homelab over Tailscale. It holds only
models: no secrets, no repo, no backups. Set up by hand from this runbook (nothing here is in compose).

Names used below: account `dan`, computer name `mac-mini`, `<TS_IP>` = the Mac's Tailscale IP (100.x.y.z,
found in part 2).

Commands for the Mac have no `#` comments: zsh doesn't treat them as comments when pasted.

**Exposure**: Ollama has no auth, so it listens on `<TS_IP>:11434` only: reachable from the homelab and
your tailnet devices, not from the LAN, never forwarded. At boot it starts before Tailscale is up, fails to
bind, and launchd retries every 15 s until Tailscale is up. No pf rules needed.

## Part 1: at the Mac (monitor, USB keyboard + mouse)

Wi-Fi or Ethernet both work: the Mac only exchanges small text requests with the homelab. Ethernet is
steadier if it can ever sit near a port; switching later changes nothing else here (the Tailscale IP
stays the same). macOS joins a saved Wi-Fi network at boot, before login, so power-cut recovery works.

**1. Erase** (skip if it's already at the "Hello" screen). Copy off anything you want to keep first.
System Settings → General → Transfer or Reset → **Erase All Content and Settings** → admin password →
Continue. If it asks for an Apple Account password, that's Activation Lock / Find My: enter it so the erase
also signs it out. The Mac restarts to the activation screen: on Wi-Fi, pick the home network and enter
its password (it needs internet to activate); on Ethernet it activates by itself.

**2. Setup Assistant**
- Language, Country/Region. Accessibility: **Not Now**.
- Network: on Wi-Fi, join the home network (the 5 GHz one if the APs show 2.4 and 5 GHz separately);
  on Ethernet it shows as connected.
- Data & Privacy: Continue. Migration Assistant: **Not Now**.
- Apple Account: **Set Up Later** → Skip. Terms: Agree.
- Create a Computer Account: Full name `dan`, Account name `dan`, a strong password (keep it in your
  password manager; SSH won't use it, but sudo and Screen Sharing will). Hint: leave empty.
- Location Services: off. Time Zone: pick your local one (the homelab host clock is UTC; that's fine).
- Analytics: untick everything. Screen Time: **Set Up Later**. Siri: off.
- **FileVault** screen, if shown: untick "Turn on FileVault" / choose **Not Now**. (With it on, the Mac
  stops at an unlock screen after a power cut.)
- Touch ID / Apple Pay: skip. Appearance: any.

**3. System Settings** (Apple menu → System Settings)
- **Privacy & Security → FileVault**: must say *FileVault is turned off*. If not: Turn Off, and wait
  until it finishes decrypting before going on.
- **Users & Groups → Automatically log in as**: `dan` (enter the password). It's only offered with
  FileVault off.
- **Lock Screen**: "Turn display off when inactive" **10 minutes**; "Require password after screen saver
  begins or display is turned off" **Immediately**. (Auto-login gets services going; the screen still
  locks.)
- **Energy**: Prevent automatic sleeping when the display is off **on**; Wake for network access **on**;
  Start up automatically after a power failure **on**. (Part 2 sets the same with `pmset` and checks it.)
- **General → Software Update → (i) next to Automatic Updates**: Check for updates **on**, Download new
  updates when available **on**; Install macOS updates **off**; Install application updates from the App
  Store **off**; Install Security Responses and system files **off**. Nothing installs or restarts on its
  own; you install updates by hand (see Maintenance).
- **General → Sharing**:
  - Local hostname → Edit → `mac-mini`.
  - **Remote Login** on → (i): Allow full disk access for remote users **off**; Allow access for
    **Only these users**: `dan`.
  - **Screen Sharing** on (for the odd GUI task; reach it at `vnc://<TS_IP>` from a Mac, or any VNC client).
  - Everything else off.
- **Network**, for the DHCP reservation in part 3:
  - Wi-Fi: Wi-Fi → **Details…** next to the home network → **Private Wi-Fi address: Off** (otherwise the
    MAC address can change and the reservation misses); "Automatically join" on; note the Wi-Fi MAC
    address shown there.
  - Ethernet: Ethernet → Details → Hardware: note the MAC address.

**4. Tailscale** (the standalone app, not the App Store one)
- Safari → https://tailscale.com/download/mac → download the **standalone** `.pkg` → open it → install.
- Open Tailscale (Applications). Allow the **system extension** when asked (System Settings → General →
  Login Items & Extensions → Network Extensions: Tailscale on), and **Allow** the VPN configuration.
- Log in from the menu-bar icon with the same account as the homelab's tailnet.
- Menu-bar icon → Settings: **Launch at login** on.
- Menu-bar icon: note the IP next to "This Device: mac-mini" — that's `<TS_IP>`.
- In the Tailscale admin console (https://login.tailscale.com/admin/machines): mac-mini → ⋯ →
  **Disable key expiry** (otherwise it drops off the tailnet in 180 days).

**5. Ollama app** (only for its signed `ollama` binary; the app itself won't run)
- Safari → https://ollama.com/download/mac → open the `.dmg` → drag Ollama to Applications.
- Open it once (so Gatekeeper approves it). If it offers to install the command line tool, skip it;
  then quit it from its menu-bar icon (Quit Ollama).
- System Settings → General → Login Items & Extensions → **Open at Login**: remove Ollama (select, `−`).
  The launchd agent from part 2 runs the server instead, with our settings; the app would start a second
  one on localhost.

From here on everything is done from the homelab over SSH. The monitor and keyboard can go once part 2's
SSH login works.

## Part 2: from the homelab (in a terminal on the homelab, or `!` commands in Claude Code)

**6. SSH key** (on the homelab; the password prompt is the Mac's `dan` password, once):
```sh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_mac_mini -C homelab-to-mac-mini -N ""
cat >>~/.ssh/config <<'EOF'

Host mac-mini
  HostName <TS_IP>
  User dan
  IdentityFile ~/.ssh/id_ed25519_mac_mini
  IdentitiesOnly yes
EOF
ssh-copy-id -i ~/.ssh/id_ed25519_mac_mini.pub mac-mini
ssh mac-mini 'hostname; sw_vers -productVersion'
```
The last line must not ask for a password. (Replace `<TS_IP>` in `~/.ssh/config` with the real IP. To SSH from your laptop too, append its public key
to the Mac's `~/.ssh/authorized_keys` now, before step 7.)

**7. Key-only SSH** (on the Mac: `ssh mac-mini`, then):
```sh
sudo tee /etc/ssh/sshd_config.d/000-homelab.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication)'
```
Both must say `no`. Keep that session open. From a **second** homelab terminal:
`ssh mac-mini true` must still work, and `ssh -o PubkeyAuthentication=no mac-mini` must say
`Permission denied (publickey)`. (macOS starts sshd per connection, so no restart is needed.)

**8. Power settings** (on the Mac):
```sh
sudo pmset -a sleep 0 disksleep 0 displaysleep 10 womp 1 autorestart 1 powernap 0
pmset -g | grep -E ' (sleep|disksleep|displaysleep|womp|autorestart|powernap) '
```
Expect `sleep 0`, `disksleep 0`, `displaysleep 10`, `womp 1`, `autorestart 1`, `powernap 0`.

**9. `ollama` on the PATH, pointed at the server** (on the Mac):
```sh
sudo mkdir -p /usr/local/bin
sudo ln -sf /Applications/Ollama.app/Contents/Resources/ollama /usr/local/bin/ollama
TS_IP=$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4); echo "$TS_IP"
echo "export OLLAMA_HOST=$TS_IP:11434" >>~/.zshenv
echo 'export PATH=/usr/local/bin:$PATH' >>~/.zshenv
```
`~/.zshenv` is read by every zsh, including one-off `ssh mac-mini <command>` calls, which don't get
`/usr/local/bin` otherwise.

**10. Ollama as a launchd agent** (on the Mac, same shell as step 9 so `$TS_IP` is set):
```sh
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
cat >~/Library/LaunchAgents/com.homelab.ollama.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.homelab.ollama</string>
  <key>ProgramArguments</key>
  <array><string>/Applications/Ollama.app/Contents/Resources/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>$TS_IP:11434</string>
    <key>OLLAMA_CONTEXT_LENGTH</key><string>65536</string>
    <key>OLLAMA_FLASH_ATTENTION</key><string>1</string>
    <key>OLLAMA_KV_CACHE_TYPE</key><string>q8_0</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>24h</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/ollama.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/ollama.log</string>
</dict>
</plist>
EOF
plutil -lint ~/Library/LaunchAgents/com.homelab.ollama.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.homelab.ollama.plist
sleep 3; tail -n 5 ~/Library/Logs/ollama.log
```
The log must say `Listening on 100.x.y.z:11434`. Ignore its `default_num_ctx=4096` line: that's Ollama's
own guess, and `OLLAMA_CONTEXT_LENGTH` overrides it (the `server config` line shows `65536`). The settings are the scout's (Hermes needs ≥ 64K context; q8_0 KV cache needs flash attention).
After editing the plist: `launchctl bootout gui/$(id -u)/com.homelab.ollama`, then the `bootstrap` line again.

**11. Models** (on the Mac; ~20 GB in `~/.ollama/models`). The bench candidates from the scout's first
report; check each tag exists on https://ollama.com/library first (the scout's tags weren't re-checked):
```sh
ollama pull gemma4:12b-it-qat
ollama pull qwen3.5:9b
ollama pull qwen3.5:9b-q4_K_M
ollama pull granite4.1:8b
ollama list
```
Plain `qwen3.5:9b` is the MLX (safetensors) build; `qwen3.5:9b-q4_K_M` is the GGUF one (6.6 GB).

**12. Check from the homelab** (exit the Mac shell first):
```sh
curl -s http://<TS_IP>:11434/api/version
curl -s http://<TS_IP>:11434/api/tags | python3 -c 'import json,sys; print([m["name"] for m in json.load(sys.stdin)["models"]])'
curl -s http://<TS_IP>:11434/api/generate -d '{"model":"qwen3.5:9b","prompt":"Say hi in five words.","stream":false}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["response"]); print(round(d["eval_count"]/d["eval_duration"]*1e9,1), "tok/s")'
```
And from the LAN it must **not** answer: `curl -m 5 http://<mac LAN IP>:11434/api/version` → connection refused.

## Part 3: finish

**13. DHCP reservation** (optional; everything uses `<TS_IP>`): on the router, where the homelab's
192.168.0.210 is reserved, reserve an address for the MAC address from step 3.

**14. Pull-the-plug test** (on Wi-Fi this also proves it rejoins the network before login): pull the Mac's power for 10 s, plug back in, touch nothing. Within ~3 minutes,
from the homelab: `ssh mac-mini true` works and step 12's `api/version` answers. If not, plug the monitor
in and see where it stopped (FileVault unlock screen = step 3; login window = auto-login).

**15. Uptime Kuma**: monitor `mac-mini-ollama` (labels in `core/uptime-kuma/compose.yaml`) checks
`http://<TS_IP>:11434/api/version` every minute; ntfy after 3 failed retries. If the Tailscale IP ever
changes, update it there, in `~/.ssh/config`, in the plist and in `~/.zshenv`.

## Model bench
Hermes needs at least 64K context, and macOS gives the GPU about 2/3 of the 16 GB.

Run from the homelab (about 10-20 min; add `--no-write` to print only):
```sh
scripts/model-bench.py http://<TS_IP>:11434
```
It unloads models between runs, so the Mac has no model loaded afterwards until the next request (first
request = cold load). Columns: load time, prefill and decode tok/s, resident GB and GPU % (from `/api/ps`),
context, and tool-call results out of 10 (valid = parseable `tool_calls`; right = correct tool and
arguments). Resident GB near 11.8 GiB, or GPU % under 100, means it won't hold up under Hermes.
Commit the updated table after a run. For stacked loads and macOS memory pressure see `--memory` under
Memory budget below.

<!-- model-bench:start -->
Run 2026-10-15 19:12 UTC, Ollama 0.40.4, num_ctx 65536, prefill prompt 23329 tokens.

| Model | Format | Load s | Prefill tok/s | Decode tok/s | Resident GB | GPU % | ctx | Valid tool calls | Right tool+args | s/tool call |
|---|---|---|---|---|---|---|---|---|---|---|
| gemma4:12b-it-qat | gguf Q4_0 | 7.4 | 83.2 | 11.2 | 7.6 | 100 | 65536 | 9/10 | 9/10 | 13.4 |
| qwen3.5:9b-q4_K_M | gguf Q4_K_M | 5.4 | 148.3 | 16.3 | 6.9 | 100 | 65536 | 8/10 | 8/10 | 10.4 |
| qwen3.5:9b | safetensors mlx | 3.7 | 111.6 | 18.5 | 8.9 | 100 | 65536 | 10/10 | 10/10 | 6.1 |
| granite4.1:8b | gguf Q4_K_M | 3.6 | 97.9 | 16.8 | 11.2 | 100 | 65536 | 10/10 | 10/10 | 2.1 |
<!-- model-bench:end -->

## Memory budget
How much of the 16 GB the models really use when they sit side by side. Run from the homelab (about 3-5 min;
needs the step-6 SSH key; add `--no-write` to print only; `--third` is an Ollama model of about 3 GB standing in
for a Whisper-sized load, since Whisper itself isn't in Ollama):
```sh
scripts/model-bench.py --memory http://<TS_IP>:11434 [--third <model>]
```
Scenarios: (a) Hermes's model alone (`--base`, default `qwen3.5:9b`), (b) plus the wardrobe's (`--second`,
default `gemma4:12b-it-qat`), (c) plus `--third`. It unloads everything it loaded when done, so Hermes cold
loads on its next message. Reading guide: any eviction, pressure warn/critical, or swap above 1 GB in a
scenario means that combination doesn't fit. New Mac mini ideas (hermes-discord-voice, Paperless AI) cite the
row they need. Commit the updated table after a run.

<!-- memory-budget:start -->
Not run yet.
<!-- memory-budget:end -->

## Batch slots
Every job that calls the Mac mini (host clock is UTC):

| Job | When | Model |
|---|---|---|
| Hermes | on demand (Discord) | qwen3.5:9b |
| Wardrobe vision tagging | on upload (one worker; retries every 5 min while Ollama is down) | gemma4:12b-it-qat |
| Fitness weekly summary (`fitness-weekly.sh`) | Sundays 19:00 | qwen3.5:9b |
| Model bench / memory run | by hand, never Sundays 18:30-19:30 | several |
| Reserved: future Paperless indexing | nightly 01:00-05:00, no other batch job there | tbd |

`morning-brief.py` (07:00) does not call the model. Rule: a new cron job that calls the Mac takes a free
slot from this table and adds its row here.

## Ollama memory settings
Dan applies these by hand in the Ollama plist (step 10), then `launchctl bootout` / `bootstrap`:
- `OLLAMA_NUM_PARALLEL=1`: each parallel slot adds another 64K context.
- Keep `OLLAMA_KEEP_ALIVE=24h` so Hermes's model stays loaded.
- `OLLAMA_MAX_LOADED_MODELS=1` if row (b) shows eviction, pressure warn or swap above 1 GB (then also consider
  `WARDROBE_MODEL=qwen3.5:9b` so tagging shares Hermes's model); otherwise `2`.

## Maintenance
- **Updates**, monthly or when a security fix lands: Screen Sharing in, System Settings → General →
  Software Update → install; it restarts and comes back by itself (auto-login, launchd, Tailscale).
- **Ollama update**: download the new app, replace it in Applications, open it once and quit it (and
  remove it from Open at Login again if it re-added itself), then
  `launchctl kickstart -k gui/$(id -u)/com.homelab.ollama` over SSH.
- **Logs**: `ssh mac-mini tail -n 50 ~/Library/Logs/ollama.log`.
- **Free a model's RAM**: `ollama stop <model>`; remove one: `ollama rm <model>`.
