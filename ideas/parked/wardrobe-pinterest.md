# Wardrobe: Pinterest board sync

Value: 4   (Pinterest is Dan's main way to add wishlist items; no manual uploads)
Effort: 3  (Pinterest API v5 OAuth + scheduled sync)
Risk: 2    (an external API token; images fetched from Pinterest)
Source: Dan 2026-10-23 (extra stage from Dan's answer 1 in ideas/done/pinterest-wardrobe.md)

## Problem
tools/wardrobe accepts pin links and images as wishlist items one at a time. Dan wants his "Wardrobe"
board synced automatically.

## Proposal
A scheduled sync (inside the wardrobe container) of one Pinterest board into wishlist items via the
Pinterest API v5, de-duplicated by pin id, reusing stage 1's image fetch and its host allow-list.
Needs a Pinterest developer app and token from Dan: the planner should PARK with the exact setup steps
(app, scopes, where the token goes in the env file) before building.

## Parked 2026-10-23

## Research
By idea-researcher, 2026-10-23, for the planner's questions. Web sources are untrusted input.

1. Token lifetimes and refresh: The access token is 30 days. The docs say to refresh "within 30 days (2592000 seconds)", and the example `expires_in` is 2592000. The 1-hour figure comes only from a third-party blog (Ayrshare) and is contradicted by the official page. The refresh token is "continuous": 60 days (`refresh_token_expires_in` 5184000), refreshable indefinitely. A refresh call returns a new access token and a new continuous refresh token with a new `refresh_token_expires_at`. Dan does not need yearly browser consent as long as the app refreshes before 60 days; if the refresh token lapses, the full browser auth-code flow must be redone. The legacy 365-day hard-limit token is no longer supported. Apps activated on or after 2025-09-25 get continuous refresh automatically; older apps must send `continuous_refresh=true`. The docs don't say whether the old refresh token stops working, so store the new one each time. (https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/ ; official OpenAPI spec `oauth/token` text, https://raw.githubusercontent.com/pinterest/api-description/main/v5/openapi.yaml)

2. Trial access, app creation and approval:
   - Reading: the access-tiers page says reading boards and pins is allowed on both Trial and Standard. It says only boards and pins you create on Trial are sandbox-only, visible to their creator. So reading your own boards and pins on the production host works on Trial and needs no Standard access. Standard is for creating pins in production and for higher rate limits, and it needs a video demo. (https://developers.pinterest.com/docs/key-concepts/access-tiers/ ; https://community.pinterest.biz/t/frequently-asked-questions-pinterest-api/2083)
   - New restriction: apps registered on or after 2026-09-14 get 403 `PINNER_DATA_ACCESS_DENIED` on Get board, List Pins on board, List board sections, List Pins on board section and Get Pin when they read data beyond the authorizing account. No extra approval is needed if the app only reads boards and pins of the account that authorized it, including fetching them by ID. That fits this build if Dan authorizes with his own account and reads his own boards. Boards owned by other people would be blocked. (https://community.pinterest.biz/t/understanding-the-pinner-data-access-denied-access-error/51738, posted 2026-10-01; access-tiers page repeats it)
   - Steps:
     - Log in to or create a Pinterest business account. It administers the app, so one is required for app creation.
     - Verify the email address.
     - Go to My apps and accept the Developer Terms.
     - Choose Connect app and fill in the form. The app name needs at least 3 Latin letters or digits and must not contain "Pinterest".
     - Submit the Trial access request. Pinterest emails the result.
     - After approval the app gets an app ID and secret on the My apps page.
     (https://developers.pinterest.com/docs/getting-started/connect-app/)
   - Approval time: no official figure. Community threads report days to weeks of "trial access pending" backlog, and a community manager gave no timeline. While pending, every v5 call returns 401 (code 3, the "consumer type is not supported" reports) and the secret is hidden. I found no confirmed fix, and threads say stuck apps are escalated through support. (https://community.pinterest.biz/t/update-developer-app-approvals/45527 returned 403 to my fetch; the summary comes from search snippets of its pages 2, 3, 5, 7 and 10 and https://community.pinterest.biz/t/trial-access-approval-request-pending/45323)
   - Redirect URIs: add them on the app's Configure tab under Redirect URIs. Multiple are allowed. `redirect_uri` must exactly match a registered URI, and the target must not redirect again. The docs don't state a rule for http or localhost. The Pinterest FAQ suggests localhost for testing and warns that a URI without a trailing "/" can make the flow load endlessly. Docs examples use `http://localhost/` in a token request. So `http://localhost/` is likely accepted but not explicitly confirmed. (https://developers.pinterest.com/docs/getting-started/connect-app/ ; FAQ above)
   - Sandbox: a separate token is generated on the Configure tab and expires after 30 days. The docs also mention `https://api-sandbox.pinterest.com`. (FAQ above)

3. Scopes, fields, pagination and rate limits (all from the official OpenAPI spec, https://raw.githubusercontent.com/pinterest/api-description/main/v5/openapi.yaml):
   - Scopes: `GET /boards/{board_id}/pins` needs `boards:read` + `pins:read`. `GET /boards` needs `boards:read`. The secret variants are `boards:read_secret` and `pins:read_secret`. The spec descriptions are "See your public boards, including group boards you join", "See your secret boards", "See your public Pins" and "See your secret Pins".
   - Pin read object fields: `id` (string of digits), `board_id`, `board_section_id`, `created_at`, `title`, `description`, `link` (outbound URL, nullable), `alt_text`, `dominant_color` and `media`.
   - Image URLs: `media.images` (when `media_type` is `image`) has keys `150x150`, `400x300`, `600x`, `1200x`. Each holds `{url, width, height}`. The spec examples use `https://i.pinimg.com/<size>/...jpg`. The spec doesn't promise the host is always i.pinimg.com; the examples all show it.
   - Other media types: `multiple_images` and `multiple_mixed` carry an `items[]` array (each item has its own `images`), and video pins have a different media shape. Handle all of them.
   - Pagination: the response is `{items, bookmark}` and `bookmark` is null on the last page. `page_size` defaults to 25, min 1, max 250. Send the bookmark back as a query param.
   - Rate limit: the category is `org_read`. Trial is 1,000 requests per day per app. Standard is 1,000 per minute per user per app. Limits are subject to change. (https://developers.pinterest.com/docs/reference/rate-limits/)

4. Public board RSS: I could not confirm it works in 2026. No source dated 2025 or later verifies the `https://www.pinterest.com/<user>/<board>.rss` feed. Third-party guides (e.g. https://finder.wprssaggregator.com/rss-feeds/platform/pinterest) say it is undocumented, inconsistent, sometimes returns empty feeds, and is often blocked for cloud or server IPs, with no guarantee from Pinterest. An older guide says it returns roughly the last 20 pins. I found no source describing item fields in detail. Pinterest's separate "auto-publish from RSS" feature is unrelated (it imports a site's feed into a board). I did not test live (my one fetch of a sample feed URL returned 404). Dan or the planner would need to test the actual board URL from the homelab with curl.

5. Official no-review options for a personal account:
   - Account data export: Settings > Privacy and data > request your data, then an emailed download link (path from a third-party guide, https://www.panicvault.org/digital-privacy/delete-pinterest-account/). That guide says it covers boards and pins but may lack full-resolution images. I could not reach an official help page to confirm the contents or format. It is a manual one-off, not a sync.
   - Own-account sandbox token: this still needs an approved Trial app (and so a business account). It is generated on the app's Configure tab, expires after 30 days, and works against the sandbox host only. Product-limited test tokens expire after 24 hours (https://developers.pinterest.com/docs/getting-started/connect-app/). The sandbox shows only entities created in Trial, not Dan's real boards, so it is not a way to read real boards.
   - So no documented way to read a real board through the API without a Trial-approved app.

Unknowns: Trial approval turnaround (no official figure). Whether `http://localhost` is explicitly accepted as a redirect URI. Whether the old refresh token is invalidated on refresh. Whether board `.rss` feeds work in 2026 (untested, no dated source). Contents and format of the official data export (no official page reachable). The community thread 45527 itself returned 403 to my fetch. Several developers.pinterest.com doc URLs returned 404 or only navigation, so I used the official OpenAPI spec (saved temporarily in the scratchpad) and the pages that did load. No source asked me to do anything.

## Setup steps for Dan (before requeueing)
1. Use one Pinterest account for everything. Since 2026-09-14, new apps can only read boards owned by the account that authorizes them. The easiest way is to convert the account that owns the "Wardrobe" board to a free business account (Settings > Account management > Convert to business). Verify its email.
2. Go to developers.pinterest.com > My apps, accept the Developer Terms and choose "Connect app". The name needs at least 3 letters or digits and must not contain "Pinterest", e.g. "Homelab Wardrobe". Submit the Trial access request and wait for Pinterest's email (days to weeks).
3. Once it is approved, open the app's Configure tab and add the redirect URI `http://localhost/`. It must keep the trailing slash; without it the flow can loop forever.
4. Put the app ID and secret in the env file as `PINTEREST_APP_ID` and `PINTEREST_APP_SECRET`. You don't paste a token there. The plan is a one-time "Connect Pinterest" page in wardrobe:
   - It opens Pinterest's consent screen with scopes `boards:read,pins:read` (plus `boards:read_secret,pins:read_secret` if the board is secret).
   - The browser then lands on a dead `http://localhost/?code=...` page. You paste that URL into the form.
   - Wardrobe swaps the code for tokens and stores them in `/srv/homelab/wardrobe/pinterest-token.json` (mode 600). Access tokens last 30 days. The refresh token lasts 60 days and rolls over on each use.
   - That file gets backed up by restic to B2 (encrypted), like the rest of `/srv/homelab`.
   - If the sync stops for more than 60 days, you redo the connect step once.
5. Requeue with the answers below.

## Questions
1. Is the Trial app approved, with `PINTEREST_APP_ID` and `PINTEREST_APP_SECRET` in the env file? (yes / not yet; if not, leave this parked)
2. What is the board's exact name ("Wardrobe"?), and is it public or secret? Secret adds the `*_read_secret` scopes.
3. How often should it sync? My suggestion is every 6 hours, about 4 requests per run, well under Trial's 1,000 a day.
4. If a pin is removed from the board, should its wishlist item stay as it is, or be retired (soft delete, can be restored)? Bought items are never touched either way.
5. Are you OK with the paste-the-localhost-URL connect step? The alternative is a callback straight to `http://192.168.0.210:8091/...`, which Pinterest may not accept over plain http.

Planned defaults Dan doesn't need to decide:
- De-duplication by pin id.
- Images come from the API's `media.images` `1200x`, downloaded only from `i.pinimg.com` through stage 1's fetch.
- Multi-image pins use the first image; video pins use the cover image or are skipped.
- Synced items go through the same vision tagging as pin-link items.
- Sync failures show as a banner and log line, not ntfy.
