---
name: gpu-container-policy
description: Use when adding GPU, CUDA or NVENC to a container.
category: deployment
---

# GPU containers on this homelab

The only GPU is a GTX 970 (Maxwell, compute 5.2) on NVIDIA driver branch 580, the last branch that supports it. Never install a newer driver branch.

- Default to the CPU image. Use a GPU variant only when its CUDA runtime still supports Maxwell on driver 580. Check the upstream prerequisites (compute capability, minimum driver, CUDA version).
- Upstream notes such as "CUDA 13 and newer" can silently drop Maxwell. Pin the GPU variant to a version that works today, and write the upgrade risk in the service README. Do not let the newest tag float.
- The card is shared: Jellyfin uses NVENC on it. Check VRAM and concurrent use before giving a second container GPU access.
- Confirm the GPU path in a live container (`docker exec`), not from docs alone. Until then, record it as "not yet run live".
