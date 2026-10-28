# Deals review

Value: 5
Effort: 2
Score: 20
Research: yes
Source: dashboard 2026-10-26

Something needs to review what the #deals in discord is outputting and make it make more sense as at the moment it’s not possible to understand what the “deal” is. So maybe something needs to review the output and then interpret it

_Added from the dashboard, 2026-10-26._

## Parked 2026-10-26

## Research
Doable: yes
Size: Effort 1-3. It is 1 if the cause is how the watches are set up (a settings fix in the changedetection UI plus a README section), and 3 if we add a script that rewrites each alert.
What's posting: the only thing feeding #deals is changedetection (tools/changedetection, 8087). The repo only knows the one webhook, DISCORD_WEBHOOK_URL, which posts to #homelab, so Dan must have pasted a separate #deals webhook into changedetection's UI. card-prices.py posts to the main feed through discord.sh, not to #deals.
Likely cause: the README's default Discord body is the raw page diff, and Discord trims it at 2000 characters. The latest snapshot in each watch dir under /srv/homelab/changedetection is about 8.5 KB. That points to whole-page text watches ("Webpage Text/HTML, JSON and PDF changes") rather than the "Re-stock & Price detection" processor, which stores only price and stock. If so, every alert is a trimmed diff of page noise (banners, recommendations), new snapshots appear every few hours with no real deal, and nothing says which product or what price. I couldn't confirm the processor: watch.json and the snapshots are root-only (0600), and the API key lives in the env file. One watch (argos.co.uk/product/7754603) has a 403 Access Denied error from Akamai.
Options:
1. Fix it at the source (Effort 1): switch each product watch to "Re-stock & Price detection for pages with a SINGLE product". It reads the price and stock state from the page's own product data (JSON-LD, microdata, OpenGraph). Set a price-change threshold (%) or alert on restock only. Set a short global notification body template from tokens, for example "{{watch_title}}: {{restock.price}} ... {{watch_url}}". A watch that has to stay a text watch gets a CSS/XPath include filter on the price element. The build is a README "Readable alerts" section with the exact settings, and Dan applies them in the UI (the API could do it too, but that would mean writes to his live watches). Catch: shops without product data (and Argos, which blocks the fetch) won't give a price. (https://www.mintlify.com/dgtlmoon/changedetection.io/features/restock-price-monitoring, https://www.mintlify.com/dgtlmoon/changedetection.io/configuration/notifications-setup, https://newreleases.io/project/github/linuxserver/docker-changedetection.io/release/0.47.04-ls141 for the {{restock.price}} token)
2. Our own formatter (Effort 2): changedetection stops posting to Discord. A cron script, scripts/deals-digest.py, reads its API (/api/v1/watch plus each watch's history, using the existing CHANGEDETECTION_API_KEY), works out old and new price and stock, and posts "LEGO 10333: £299.99 -> £239.99 (-20%), in stock, <link>" to a new DISCORD_DEALS_WEBHOOK_URL. It also needs the cron and Kuma push monitor files. Catch: parsing prices out of text diffs is fragile unless the watches use option 1's processor anyway.
3. Model interpreter (Effort 3): option 2, but the diff goes to the Mac mini's Ollama model, which writes one plain sentence per alert. It works on messy text diffs. Catch: it can get a price or product wrong without saying so, and #deals goes quiet whenever the Mac mini is down. A plain diff would be needed as the fallback.
Recommended: Option 1 first. It fixes the cause (noisy whole-page diffs), costs nothing to run and can't make up a price. Add option 2 only if alerts are still unclear afterwards.
Unknowns: which processor each watch really uses, and what one current #deals post looks like (Dan can see both in the UI and in Discord). Also whether the shops he watches publish product data (LEGO.com usually does; it's unknown for the vinyl shop).

## Questions
1. Which option: 1 (settings fix + README), 2 (formatter script), 3 (model rewrite), or 1 now and 2 later?
2. Can you paste one recent #deals post (or say which shop it came from), so the fix can be checked against it?
3. Should a price drop alert on any change, or only above a threshold (say 5%), with restocks always alerting?
4. If 2 or 3: is a separate DISCORD_DEALS_WEBHOOK_URL (the #deals webhook, set in the env file) OK, with changedetection's own Discord notification switched off?
