# Shop access reality check

**Read this before promising "I searched the store."** None of the three target grocers expose a usable public price API for Canada, and direct page fetches are blocked. Be honest with the user about how prices/links were obtained.

| Shop | Public price API? | Direct fetch? | What actually works |
|------|-------------------|---------------|---------------------|
| **Walmart** | No. Walmart.io is seller-only; SerpApi/Scavio Walmart APIs are **US (walmart.com) only** — they do **not** cover walmart.ca. | Blocked (HTTP **418**). | `WebSearch` — it *is* Canada-correct and surfaces real `walmart.ca/en/ip/...` product links with CAD prices. |
| **T&T Supermarket** | No — none exists. | Blocked (HTTP **403**). | `WebSearch` — but product pages are poorly indexed; usually only the **search link** is available. Delivery-zone gated. |
| **Costco** | No. | Often blocked / login-gated. | `WebSearch` + `CatalogSearch` link. Warehouse-only items aren't online. |

> Tested June 2026: WebSearch returned direct walmart.ca product links + CAD prices (e.g. Great Value 100% Apple Juice 1L ≈ CAD $1.68). WebFetch of walmart.ca returned **418** and T&T returned **403** — i.e. plain fetches/naive scrapers are refused.

## Default strategy: WebSearch (no keys, Canada-correct)
For each item to buy, per shop:
1. `WebSearch` for `"<shop> <item> price <region>"` (add brand/size from `memory/preferences.md`). For Walmart, also try `"<item> walmart.ca /en/ip"` to get a **direct product link**.
2. Build the **buy link** from the result: prefer a direct product URL WebSearch surfaced; otherwise the shop's `search_url` from `config/shops.json` (replace `{query}` with the URL-encoded item). `scripts/shop_search.sh <shop> "<item>"` returns that search link for you.
3. Tell the user prices are **web-search estimates as of <date>**, not live quotes, and vary by store/postal code.

## Browser automation: the working setup + proven recipes
A plain script/`WebFetch` cannot reach walmart.ca/T&T (418/403). A real browser (Playwright MCP, `mcp__playwright__browser_*` tools) can — **but only the full Chromium, not the headless shell.** Tested June 2026: with `--headless` (chrome-headless-shell) Akamai returns **"Forbidden"** (Walmart) / **"Access Denied"** (T&T); the **full Chromium running headed** passes both.

**Config that works** (`~/.claude.json` → mcpServers.playwright): `args: ["-y","@playwright/mcp@latest","--browser","chromium","--config","/home/<user>/.claude/playwright-mcp-config.json"]` (NO `--headless`), `env: {"DISPLAY": ":0"}`. Browsers install without root: `npx -y playwright install chromium` (and `npx -y @playwright/mcp@latest install-browser chrome-for-testing` if asked). A real browser window appears during runs (headed) — that's required to beat the bot defenses. First browser action prompts for permission.

**Before the first browser action this run, check the config is set up — don't assume.** If the
`mcp__playwright__browser_*` tools aren't loaded, or there's no `~/.claude/playwright-mcp-config.json`,
set it up first (or fall back to WebSearch and say so):
- `~/.claude/playwright-mcp-config.json` should exist and include **`"outputDir": "<dir outside any repo>"`**
  (e.g. `~/.cache/playwright-mcp`). Playwright MCP defaults its output (console logs + page snapshots) to
  the **current working directory** — if cwd is a git repo, it litters a `.playwright-mcp/` folder into it.
  Setting `outputDir` keeps those artifacts out of the project. Config changes take effect on the next
  MCP server restart.
- The launch args / `DISPLAY` above must be present (headed full Chromium), or the grocers' bot defenses
  return 403/Access-Denied.

**Recipe — Walmart (clean, structured):**
1. `browser_navigate` to the product page `https://www.walmart.ca/en/ip/<slug>/<id>` (get the link from WebSearch, e.g. `"<item> walmart.ca /en/ip"`).
2. `browser_evaluate` to read the JSON-LD offer:
   ```js
   () => { for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
     try { for (const d of [].concat(JSON.parse(s.textContent))) for (const o of [].concat(d.offers||[]))
       if (o.price!=null) return {price:o.price, currency:o.priceCurrency, availability:(o.availability||'').split('/').pop()};
     } catch(e){} } return null; }
   ```
   → e.g. `{price:1.68, currency:"CAD", availability:"InStock"}`.

**Recipe — T&T (interactive; search box is collapsed):**
1. `browser_navigate` straight to `https://www.tntsupermarket.com/eng/search.html?query=<broad term>` (works directly). **Set the "* Location" (`#region`) first** if you need store-accurate prices — results render without it but prices/availability vary by store. (If you start on `/`, reveal the box via `[...document.querySelectorAll('button')].find(b=>/fakeinput/i.test(b.className)).click()`, then `browser_type` into `#search` with `submit:true`.)
2. **Scroll to load everything** before scraping — results lazy-load, so the first render is only a partial page:
   ```js
   async () => { let last=0; for (let i=0;i<15;i++){ window.scrollTo(0,document.body.scrollHeight); await new Promise(r=>setTimeout(r,700)); const n=document.querySelectorAll('a[href$=".html"]').length; if(n===last&&i>3)break; last=n; } }
   ```
3. Scrape product cards: anchors `a[href$=".html"]` like `/eng/<id>-<slug>.html`, with the `$price` in the nearest container, then **filter locally** (see gotchas below). e.g. *Ocean Jewel Frozen Raw White Shrimp P&D 31/40 — $8.99 — /eng/74190301-oj-raw-white-shrimp-p-d31-40.html*.

**Costco**: same idea (`browser_navigate` to `CatalogSearch?keyword=`), but warehouse-only items aren't online.

## Search-strategy gotchas (learned the hard way)
These cost real misses — follow them:
- **Search a BROAD head term, then filter locally — don't search the exact descriptive phrase.** T&T's search is literal/curated: `query=peeled shrimp` returned only **4** items and *excluded* "Ocean Jewel … **P&D**"; `query=shrimp` returned **157** including it. Query the head noun (`shrimp`, `apple juice`), load all, then match attributes yourself.
- **Expand synonyms/abbreviations when filtering.** "peeled" ↔ **"P&D"** (Peeled & Deveined); "tail off" ↔ "tail-off"/"T/off"; "deveined" ↔ "P&D". A name lacking the literal word may still match.
- **"Easy-peel" / "EZ Peel" ≠ peeled.** Those are **shell-on** (easy to peel), the opposite of what "peeled" usually means. Walmart's Great Value "Raw Pacific White Shrimp" line reads *peeled/tail-off* in the related-items carousel but each product's own description says **"easy-peel, shell-on"**.
- **Verify attributes from the product's OWN description, not the tile or the related-items carousel.** The carousel/facet labels are unreliable (the same item showed both "Tail Off" and "Tail-On"). Open the page and read "About this item".
- **If an attribute isn't stated, say "unspecified" — don't infer.** Ocean Jewel "P&D" pages never state tail on/off; only the explicit *"…/Tail Off"* product guarantees no tail. Report the gap rather than assuming.
- **Always scroll to load all results** before concluding something is absent — the first render is partial.

Caveats: tough challenges (captcha/Press-&-Hold) can still appear; honor robots/ToS and keep volume low. Docs: https://playwright.dev/docs/getting-started-mcp and https://code.claude.com/docs/en/mcp.md

## Price + quality comparison
- **Price**: normalize to a comparable unit (per 100 g / per unit / per L) before declaring a winner — pack sizes differ wildly (esp. Costco bulk).
- **Quality**: lean on the user's own notes in `memory/preferences.md` first; web ratings are a weak signal. Note organic/brand/freshness where it matters to the user.
