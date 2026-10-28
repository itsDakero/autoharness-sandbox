# stirling-pdf

Stirling-PDF (`stirlingtools/stirling-pdf`, pinned in `compose.yaml`) merges, splits, converts, compresses and
OCRs PDFs in the browser. Family tile: http://192.168.0.210:8098 (also http://stirling-pdf.lan).

## Where things live
- Settings: `/srv/homelab/stirling-pdf/configs` (`/configs`); OCR language data:
  `/srv/homelab/stirling-pdf/tessdata`; app logs: `/srv/homelab/stirling-pdf/logs`. All under APPDATA, so restic
  backs them up and they survive a recreate or upgrade.
- Uploaded PDFs are processed in memory/temp and not kept. For documents to keep, use Paperless.
- The container gets only `TZ`, `SECURITY_ENABLELOGIN=false`, `SYSTEM_DEFAULTLOCALE` and `LANGS`. No secrets.

## First start
`scripts/dc.sh tools/stirling-pdf up -d`, then open the UI. No login (like every published port, it is
reachable from the LAN and tailnet only; never forward it on the router).

## Health
The healthcheck (`curl`, in the image) and the Kuma monitor hit `/api/v1/info/status` (unauthenticated,
`{"status":"UP"}`) on port 8080 inside / 8098 outside.
