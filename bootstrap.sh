#!/usr/bin/env bash
# Homelab host bootstrap. Idempotent: safe to rerun.
# Usage: sudo ./bootstrap.sh
set -euo pipefail

TARGET_USER="dan"
LOG_FILE="/var/log/homelab-bootstrap.log"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

exec > >(tee -a "$LOG_FILE") 2>&1
log() { echo "[$(date '+%F %T')] $*"; }

log "=== bootstrap start ==="

. /etc/os-release
CODENAME="${VERSION_CODENAME}"
ARCH="$(dpkg --print-architecture)"
export DEBIAN_FRONTEND=noninteractive

is_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"; }

install -m 0755 -d /etc/apt/keyrings
APT_UPDATED=0

# python3-venv: venvs for forensics/ parsers (forensics/.venv)
for p in ca-certificates curl python3-venv; do
  if ! is_installed "$p"; then
    log "Installing prerequisite: $p"
    (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
    apt-get install -y "$p"
  fi
done

# ---------------------------------------------------------------- Docker
log "--- Docker ---"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  if is_installed "$pkg"; then
    log "Removing conflicting package: $pkg"
    apt-get remove -y "$pkg"
  fi
done

if [[ ! -s /etc/apt/keyrings/docker.asc ]]; then
  log "Adding Docker GPG key"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
else
  log "Docker GPG key present"
fi

DOCKER_SRC=/etc/apt/sources.list.d/docker.sources
DOCKER_SRC_CONTENT="Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${CODENAME}
Components: stable
Architectures: ${ARCH}
Signed-By: /etc/apt/keyrings/docker.asc"
if [[ "$(cat "$DOCKER_SRC" 2>/dev/null)" != "$DOCKER_SRC_CONTENT" ]]; then
  log "Writing $DOCKER_SRC"
  printf '%s\n' "$DOCKER_SRC_CONTENT" > "$DOCKER_SRC"
  APT_UPDATED=0
else
  log "Docker apt source present"
fi

DOCKER_PKGS=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)
missing=()
for p in "${DOCKER_PKGS[@]}"; do is_installed "$p" || missing+=("$p"); done
if (( ${#missing[@]} )); then
  log "Installing: ${missing[*]}"
  apt-get update && APT_UPDATED=1
  apt-get install -y "${missing[@]}"
else
  log "Docker packages already installed"
fi

systemctl enable --now docker containerd
log "docker service: $(systemctl is-active docker)"

if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
  log "$TARGET_USER already in docker group"
else
  log "Adding $TARGET_USER to docker group"
  usermod -aG docker "$TARGET_USER"
fi

# ---------------------------------------------------------------- Tailscale
log "--- Tailscale ---"
TS_KEY=/usr/share/keyrings/tailscale-archive-keyring.gpg
TS_LIST=/etc/apt/sources.list.d/tailscale.list
if [[ ! -s "$TS_KEY" ]]; then
  log "Adding Tailscale GPG key"
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.noarmor.gpg" -o "$TS_KEY"
else
  log "Tailscale GPG key present"
fi
if [[ ! -s "$TS_LIST" ]]; then
  log "Adding Tailscale apt source"
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.tailscale-keyring.list" -o "$TS_LIST"
  APT_UPDATED=0
else
  log "Tailscale apt source present"
fi
if ! is_installed tailscale; then
  log "Installing tailscale"
  (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
  apt-get install -y tailscale
else
  log "tailscale already installed"
fi
systemctl enable --now tailscaled
log "tailscaled service: $(systemctl is-active tailscaled)"

# ---------------------------------------------------------------- UFW
log "--- UFW ---"
if ! is_installed ufw; then
  (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
  apt-get install -y ufw
fi
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH            # added before enable so SSH is never cut
ufw allow in on tailscale0
# No LAN rules needed for Docker-published ports (53, 80, 3000, ...): they
# bypass UFW via Docker's own iptables chains. Exception: Omada runs with
# network_mode: host, so its ports go through UFW (docs/m3-omada.md).
# ufw allow skips rules that already exist, so this stays idempotent.
ufw allow from 192.168.0.0/24 to any port 8043 proto tcp comment 'omada ui'
ufw allow from 192.168.0.0/24 to any port 8088 proto tcp comment 'omada ui http'
# Uptime Kuma checks leave via the monitor network. If it changed on a rebuild,
# check the monitor subnet with docker network inspect monitor.
ufw allow from 172.20.0.0/16 to any port 8043 proto tcp comment 'omada kuma check'
ufw allow from 192.168.0.0/24 to any port 29810 proto udp comment 'omada discovery'
ufw allow from 192.168.0.0/24 to any port 29811:29817 proto tcp comment 'omada devices'
if ufw status | grep -q "Status: active"; then
  log "UFW already active"
else
  log "Enabling UFW"
  ufw --force enable
fi

# ---------------------------------------------------------------- Unattended upgrades
log "--- Unattended security updates ---"
if ! is_installed unattended-upgrades; then
  (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
  apt-get install -y unattended-upgrades
fi
AUTO_CONF=/etc/apt/apt.conf.d/20auto-upgrades
AUTO_CONTENT='APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";'
if [[ "$(cat "$AUTO_CONF" 2>/dev/null)" != "$AUTO_CONTENT" ]]; then
  log "Writing $AUTO_CONF"
  printf '%s\n' "$AUTO_CONTENT" > "$AUTO_CONF"
else
  log "$AUTO_CONF already configured"
fi
# Stock 50unattended-upgrades already limits to the -security pocket.
systemctl enable --now unattended-upgrades
log "unattended-upgrades service: $(systemctl is-active unattended-upgrades)"

# ---------------------------------------------------------------- systemd-resolved
# The stub listener holds 127.0.0.53:53, which blocks AdGuard from publishing
# port 53. Disable it and point resolv.conf at resolved's upstream list, so the
# host itself keeps using upstream DNS (not AdGuard).
log "--- systemd-resolved (free port 53) ---"
RESOLVED_DROPIN=/etc/systemd/resolved.conf.d/homelab.conf
RESOLVED_CONTENT='[Resolve]
DNSStubListener=no'
RESOLVED_CHANGED=0
install -m 0755 -d /etc/systemd/resolved.conf.d
if [[ "$(cat "$RESOLVED_DROPIN" 2>/dev/null)" != "$RESOLVED_CONTENT" ]]; then
  log "Writing $RESOLVED_DROPIN"
  printf '%s\n' "$RESOLVED_CONTENT" > "$RESOLVED_DROPIN"
  RESOLVED_CHANGED=1
else
  log "$RESOLVED_DROPIN already configured"
fi
if [[ "$(readlink /etc/resolv.conf)" != "/run/systemd/resolve/resolv.conf" ]]; then
  log "Linking /etc/resolv.conf -> /run/systemd/resolve/resolv.conf"
  ln -sfn /run/systemd/resolve/resolv.conf /etc/resolv.conf
  RESOLVED_CHANGED=1
else
  log "/etc/resolv.conf already linked"
fi
if (( RESOLVED_CHANGED )); then
  log "Restarting systemd-resolved"
  systemctl restart systemd-resolved
  # dockerd caches the resolver it saw at startup (127.0.0.53); without a
  # restart, image pulls and builds keep failing DNS.
  log "Restarting docker to pick up the new resolv.conf"
  systemctl restart docker
fi
if getent hosts download.docker.com >/dev/null; then
  log "Host DNS OK"
else
  log "WARNING: host DNS lookup failed after resolved change"
fi

# ---------------------------------------------------------------- NVIDIA driver
# GTX 970 (Maxwell): the 580 branch is the last that supports it. Package names
# carry the branch, so apt never moves to a newer one. Headless (no X) plus the
# NVENC/NVDEC libraries; Ubuntu's prebuilt signed modules instead of DKMS.
log "--- NVIDIA driver 580 ---"
NV_PKGS=(nvidia-headless-no-dkms-580 linux-modules-nvidia-580-generic nvidia-utils-580
         libnvidia-encode-580 libnvidia-decode-580)
missing=()
for p in "${NV_PKGS[@]}"; do is_installed "$p" || missing+=("$p"); done
if (( ${#missing[@]} )); then
  log "Installing: ${missing[*]}"
  (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
  apt-get install -y "${missing[@]}"
  log "NVIDIA driver installed: reboot required"
else
  log "NVIDIA 580 packages already installed"
fi

# ---------------------------------------------------------------- NVIDIA container toolkit
log "--- NVIDIA container toolkit ---"
NCT_KEY=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
NCT_LIST=/etc/apt/sources.list.d/nvidia-container-toolkit.list
if [[ ! -s "$NCT_KEY" ]]; then
  log "Adding NVIDIA container toolkit GPG key"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o "$NCT_KEY"
else
  log "NVIDIA container toolkit GPG key present"
fi
if [[ ! -s "$NCT_LIST" ]]; then
  log "Adding NVIDIA container toolkit apt source"
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed "s#deb https://#deb [signed-by=$NCT_KEY] https://#g" > "$NCT_LIST"
  APT_UPDATED=0
else
  log "NVIDIA container toolkit apt source present"
fi
if ! is_installed nvidia-container-toolkit; then
  log "Installing nvidia-container-toolkit"
  (( APT_UPDATED )) || { apt-get update && APT_UPDATED=1; }
  apt-get install -y nvidia-container-toolkit
else
  log "nvidia-container-toolkit already installed"
fi
if grep -q '"nvidia"' /etc/docker/daemon.json 2>/dev/null; then
  log "Docker nvidia runtime already configured"
else
  log "Configuring Docker nvidia runtime (restarts docker)"
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
fi

# ---------------------------------------------------------------- Media downloads
# qBittorrent and the arr apps run as dan (PUID 1000). Only the downloads dir
# itself changes owner (it was 130:138); existing contents are left alone.
log "--- Media downloads ---"
DL_DIR=/mnt/media/downloads
if mountpoint -q /mnt/media; then
  if [[ "$(stat -c %U:%G "$DL_DIR" 2>/dev/null)" != "$TARGET_USER:$TARGET_USER" ]]; then
    log "Setting owner of $DL_DIR (not its contents) to $TARGET_USER"
    install -d "$DL_DIR"
    chown "$TARGET_USER:$TARGET_USER" "$DL_DIR"
  else
    log "$DL_DIR owner OK"
  fi
  for d in temp movies tv movies-remote tv-remote; do
    if [[ ! -d "$DL_DIR/$d" ]]; then
      log "Creating $DL_DIR/$d"
      install -d -o "$TARGET_USER" -g "$TARGET_USER" -m 0755 "$DL_DIR/$d"
    fi
  done
else
  log "WARNING: /mnt/media not mounted, skipping downloads setup"
fi

# ---------------------------------------------------------------- App data
log "--- App data ---"
APPDATA_DIR=/srv/homelab
if [[ -d "$APPDATA_DIR" && "$(stat -c %U:%G "$APPDATA_DIR")" == "$TARGET_USER:$TARGET_USER" ]]; then
  log "$APPDATA_DIR present"
else
  log "Creating $APPDATA_DIR (owner $TARGET_USER)"
  install -d -o "$TARGET_USER" -g "$TARGET_USER" -m 0755 "$APPDATA_DIR"
fi

# ---------------------------------------------------------------- Backups
# Nightly restic backup (scripts/backup.sh), its off-site copy to B2 and the monthly restore drill
# (scripts/restore-drill.sh), via systemd units kept in the repo's systemd/. The disk (/mnt/backup), restic, both restic repos, /etc/restic/password and
# /etc/restic/b2.env are set up by hand; only checked here.
log "--- Backups ---"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
UNITS_CHANGED=0
for u in homelab-backup.service homelab-backup.timer homelab-backup-failure.service \
         homelab-backup-offsite.service homelab-backup-offsite-failure.service \
         homelab-restore-drill.service homelab-restore-drill.timer homelab-restore-drill-failure.service; do
  if cmp -s "$REPO_DIR/systemd/$u" "/etc/systemd/system/$u"; then
    log "$u up to date"
  else
    log "Installing /etc/systemd/system/$u"
    install -m 0644 "$REPO_DIR/systemd/$u" "/etc/systemd/system/$u"
    UNITS_CHANGED=1
  fi
done
(( UNITS_CHANGED )) && systemctl daemon-reload
systemctl enable --now homelab-backup.timer
log "homelab-backup.timer: $(systemctl is-active homelab-backup.timer)"
systemctl enable --now homelab-restore-drill.timer
log "homelab-restore-drill.timer: $(systemctl is-active homelab-restore-drill.timer)"
mountpoint -q /mnt/backup || log "WARNING: /mnt/backup not mounted: backups will fail"
[[ -s /etc/restic/password ]] || log "WARNING: /etc/restic/password missing: backups will fail"
[[ -s /etc/restic/b2.env ]] || log "WARNING: /etc/restic/b2.env missing: off-site copies will fail"

# ---------------------------------------------------------------- Docker firewall
# Published ports skip UFW. homelab-docker-user.service re-adds the DOCKER-USER rule that limits
# core/ha-backups (SMB, tcp 445) to the Home Assistant Pi after every docker start
# (scripts/docker-user-rules.sh).
log "--- Docker firewall ---"
u=homelab-docker-user.service
if cmp -s "$REPO_DIR/systemd/$u" "/etc/systemd/system/$u"; then
  log "$u up to date"
else
  log "Installing /etc/systemd/system/$u"
  install -m 0644 "$REPO_DIR/systemd/$u" "/etc/systemd/system/$u"
  systemctl daemon-reload
fi
systemctl enable --now "$u"
log "$u: $(systemctl is-active "$u")"

# ---------------------------------------------------------------- Summary
log "--- Summary ---"
log "$(docker --version)"
log "$(docker compose version)"
log "tailscale $(tailscale version | head -n1)"
log "nvidia-container-toolkit: $(nvidia-ctk --version 2>/dev/null | head -n1)"
ufw status verbose
log "=== bootstrap done ==="
cat <<EOF

Next steps (manual):
  1. Log out and back in (or 'newgrp docker') so '$TARGET_USER' picks up the docker group.
  2. sudo tailscale up
  3. If the NVIDIA driver was just installed: reboot, then check nvidia-smi.
EOF
