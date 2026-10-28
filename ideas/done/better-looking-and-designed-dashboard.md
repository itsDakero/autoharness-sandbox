# better looking and designed dashboard

only i use it, act as an expert UI/UX designer specializing in modern DevOps and cloud monitoring interfaces. Help me redesign my basic homelab dashboard into a stunning, premium command center

_Added from the dashboard, 2026-10-14._

## Plan
Goal: Give the admin dashboard (/admin and /login) a dark "command center" look with a live status
  strip at the top. Behaviour stays the same, and the family page at / looks exactly as it does now.
Kind: change to core/dashboard (front end only, no backend or API changes)

Scope note: the idea says "only I use it", but the family view at / is used by the household. So
  every new look applies to the admin view only. All new CSS is scoped under `body.admin`, plus a
  restyle of login.html. The family view's CSS, markup and JS paths must not change.

Files:
- core/dashboard/app/static/index.html (paths below are inside the worktree):
  1. Theme. Add a `body.admin { ... }` block that overrides the CSS variables. The admin view is
     always dark, whatever prefers-color-scheme says:
     --bg #0a0d13; --card #111620; --text #e6e9ef; --muted #8b94a7; --border #1e2533;
     --accent #5b8cff; --accent2 #22d3ee (new); --up #34d399; --down #f87171;
     --pending #fbbf24; --unknown #64748b.
     body.admin background: two faint radial glows (accent at 8% top-left, accent2 at 6%
     top-right) over --bg, plus a 32px grid made from two linear-gradients of
     rgba(255,255,255,.025) 1px lines, with background-attachment: fixed.
     Add `font-variant-numeric: tabular-nums` on body.admin.
     No web fonts or new external assets. The dashboard-icons CDN stays the only external source.
  2. Cards (body.admin .card): border-radius 16px; background
     linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,0)) over var(--card);
     box-shadow 0 1px 0 rgba(255,255,255,.04) inset, 0 8px 24px rgba(0,0,0,.35); on :hover the
     border-color becomes color-mix(in srgb, var(--accent) 35%, var(--border)), with a .15s
     transition. Card h3 becomes a small uppercase label: .8rem, letter-spacing .08em, colour
     --muted; the h3 small text stays as it is.
  3. Gauges and bars (body.admin): bar height 8px with a rgba(255,255,255,.06) track. The fill is
     linear-gradient(90deg, var(--accent), var(--accent2)). Keep the .warn and .crit colours and
     their thresholds (75/90). The gauge value text uses ui-monospace.
  4. Sidebar (body.admin .tabs):
     - The brand shows a 8px var(--up) dot with a 2s pulse (box-shadow ring) before "Homelab".
     - The active tab gets a 3px var(--accent) left bar (inset box-shadow), a background of
       color-mix(accent 12%, transparent) and colour --text.
     - Keep the phone top-bar layout under 760px. The phone bar's background is var(--bg) at
       85% with backdrop-filter: blur(8px).
  5. Admin service tiles (body.admin .tile, Services tab):
     - Horizontal layout using a grid: a 36px icon column on the left, name and description on
       the right. min-height 72px. The admin .grid uses minmax(230px, 1fr).
     - Status dots: an "up" dot gets a glow (0 0 8px var(--up)). A "down" dot pulses (1.5s)
       with box-shadow in var(--down). "pending" dots are amber.
     - Each group h2 shows a count, e.g. "Media · 9/10 up". Change render(): in the admin
       branch, h2 text = `${name} · ${up}/${items.length} up`.
  6. Header bar (admin only, created in JS inside the `if (ADMIN)` block):
     - Right of the h1, add a `<div class="hstat">` with a pill `#sys` and a clock `#clock`.
     - `#sys` reads "All systems operational" (class ok) or "N down" (class bad). If a service
       is pending it adds " · N pending". It comes from window.SERVICES statuses, is updated in
       refresh() right after render(), and only runs when ADMIN.
     - `#clock` shows HH:MM:SS from toLocaleTimeString, updated by setInterval every 1000 ms.
     - The header becomes sticky (top 0, z-index 4, background var(--bg) at 80% + blur) on
       widths of 760px and up.
  7. KPI strip on the Overview tab (admin only):
     - In the `if (ADMIN)` setup, after the panels are built, insert
       `<div id="kpis" class="kpis">` at the top of PANELS.overview, before p.grid.
     - It holds five tiles: Services (up/total), CPU %, RAM %, GPU %, VPN (Protected / Not
       protected).
     - Each tile shows a small uppercase label, a big value (1.6rem, weight 600, tabular-nums)
       and a 4px mini-bar for CPU/RAM/GPU that uses the same warn/crit thresholds.
     - Layout: grid repeat(auto-fit, minmax(150px,1fr)), gap 12px, margin-bottom 12px.
     - Wiring: a `const KPI = { services: null, health: null, vpn: null }` object and a
       `function updateKpis()`.
       - refresh() sets KPI.services = data.services.
       - renderHealth(d, ...) sets KPI.health = d at its start.
       - renderVpn(d, ...) sets KPI.vpn = d.
       - Each of these calls updateKpis() when ADMIN.
       - Missing data, or a widget failure, shows "–". To support this, the pollWidget catch
         block sets KPI.health / KPI.vpn to null for those widget ids and calls updateKpis().
     - The values are colour-coded: Services is red if any service is down. VPN is green when
       protected and red when not.
  8. Motion: wrap every new animation (the pulses, the hover transition) in
     @media (prefers-reduced-motion: no-preference), or switch them off under reduce.
  9. Must not change:
     - CSS rules that apply when body lacks .admin;
     - the family DOM order;
     - the IDs #title #widgets #content #updated #switch #logout #tabs;
     - tab/hash/localStorage behaviour, polling intervals, decks, the idea form, the limit pill,
       the no-referrer meta, and the API calls. No new endpoints.
- core/dashboard/app/static/login.html: always dark, using the same palette as above. Same
  glow/grid background. The form card gets the same gradient, shadow and 16px radius, and the
  button is accent-coloured. Keep the form fields, names, action and the placeholder tokens that
  login_page() fills in exactly as they are.
- core/dashboard/compose.yaml: `image: homelab/dashboard:0.12.0` -> `homelab/dashboard:0.13.0`. Nothing
  else.
- docs/m1-core.md: under "## Dashboard widgets (v1)", add one bullet: "Admin look (0.13.0): always dark
  command-center theme scoped to `body.admin` (family view unchanged); Overview opens with a KPI strip
  (services up, CPU, RAM, GPU, VPN) fed by the existing services/health/vpn polls; header shows overall
  status + clock; service group headings show up counts."

New service: none (port, Kuma and labels unchanged)
New env vars: None
Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/better-looking-and-designed-dashboard/core/dashboard config -q
- git -C /home/dan/homelab/.worktrees/better-looking-and-designed-dashboard diff main -- core/dashboard/app/static/index.html
  Read the diff and confirm that every added or changed CSS selector starts with `body.admin`,
  `.kpi`/`.kpis`, `.hstat`, or sits inside an @keyframes/@media block that wraps only those
  selectors. JS changes must stay inside ADMIN-guarded code, apart from the KPI null-setting in
  pollWidget's catch, which must be guarded by `ADMIN &&`.
- There is no node on the host. To check the JS syntax, extract the <script> body to the
  scratchpad and confirm that the `{}`, `()` and `[]` counts are balanced (a python3 one-liner).
  Also confirm with grep that every new identifier (KPI, updateKpis, #kpis, #sys, #clock) is
  defined once.
- grep -n "latest" core/dashboard/compose.yaml returns nothing.
- Do not run dc.sh build/up on the worktree. That is denied, and the deploy builds it.
Docs: docs/m1-core.md gets the one bullet above. No changes to the CLAUDE.md port table, layout or
  scripts list.

## Manual steps
None beyond the normal deploy, where scripts/deploy-idea.sh runs `dc.sh core/dashboard up -d --build`.
Afterwards, open http://192.168.0.210/admin to check the new look, and http://192.168.0.210/ to
confirm the family page looks the same as before.
