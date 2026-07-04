---
name: grocery-planner
description: Plan a grocery run from a Tandoor instance. Reads the Cook Plan, its recipes, the shopping list, and the pantry (with stale/expiry status) over the Tandoor REST API via bash, suggests pantry substitutions and asks the user to decide, compares price/quality across Walmart, T&T, and Costco, and outputs a per-item list of buy links. Use when the user wants to plan shopping, decide what to buy, find substitutions, or compare grocery prices for their meal plan.
---

# Grocery Planner

Turn what's planned (Cook Plan + shopping list) and what's on hand (pantry) into a concrete, link-by-link buy list across Walmart, T&T Supermarket, and Costco — after checking the pantry for substitutions and asking the user to decide.

## 0. Prerequisites (check first)
Setup (Tandoor credentials + the Playwright MCP browser) lives in the **`tandoor-setup` skill** — see
it if `curl`/`jq` are missing, `TANDOOR_URL`/`TANDOOR_TOKEN` are unset, a call 401/403s, or the
`mcp__playwright__browser_*` tools aren't loaded. Quick check: `TANDOOR_TOKEN` set and
`bash scripts/tandoor.sh cookplan` returns JSON. Paths below are relative to this skill directory.

## 1. Read the planning data (bash)
Run the helper (it returns JSON; read it, don't dump raw to the user):
```bash
bash scripts/tandoor.sh all            # cookplan + recipes + shopping + pantry in one object
# or piecemeal:
bash scripts/tandoor.sh cookplan
bash scripts/tandoor.sh recipes        # every recipe on the cook plan, with ingredients
bash scripts/tandoor.sh shopping       # open shopping-list entries
bash scripts/tandoor.sh pantry         # every pantry item + is_stale + expiry status
bash scripts/tandoor.sh pantry-stale
bash scripts/tandoor.sh pantry-expiring
```
If a call fails, surface the actual error (bad token, server down, wrong URL) — don't fabricate data.

## 2. Build the "need to buy" list
Combine sources, de-duplicated by food:
1. **Shopping list** entries (explicit intent to buy).
2. **Recipe ingredients** for the Cook Plan that aren't adequately covered by the pantry.
3. **Pantry items that are expired or stale** and are needed for a planned recipe → flag as *replace*.
Treat shelf-stable staples already in the pantry (salt, oil, sugar, soy sauce, etc.) as covered unless expired. Honor `memory/preferences.md` (dietary hard rules, substitution rules).

## 3. Suggest substitutions from the pantry — then ASK
Before searching any shop, for each needed item check whether the pantry already holds an acceptable substitute (same food, a close variant, or a staple per the substitution rules in `memory/preferences.md`). Present the candidates and **ask the user to decide** (use the AskUserQuestion tool, one question per non-obvious swap, or a single grouped set). Never silently substitute. Record the outcome for step 6.

## 4. Compare price & quality across shops
Read `config/shops.json` and `references/shop-apis.md` first. No grocer has a *documented* price API, but T&T and Walmart are fully reachable — their "blocks" are just Akamai TLS/JA3 fingerprinting, which a Chrome-impersonating client defeats. Pick the method in this order:

**Preferred — the `curl_cffi` scripts (headless, no browser, clean JSON).** Needs `uv pip install curl_cffi` once. These return live, store-scoped prices.
- **T&T** — internal Magento **GraphQL** (best of the three; prices store-scoped via headers the script sends — GTA default, overridable):
  ```bash
  python scripts/tnt_graphql.py search "tofu" --page-size 20      # → total_count + tidied items
  python scripts/tnt_graphql.py product 73156801-tnt-fresh-tofu    # detail by url_key OR sku
  python scripts/tnt_graphql.py images  <url_key|sku> <outdir>     # nutrition-label images → OCR
  ```
- **Walmart** — parses the page's embedded `__NEXT_DATA__` JSON:
  ```bash
  python scripts/walmart_search.py search "tofu" --all-pages       # headless
  python scripts/walmart_search.py product 206880                  # ingredients/specs/price
  ```
- **Costco**: no script yet — use the browser or WebSearch below.
Field lists, store headers, pagination, and nutrition-image OCR are in `references/shop-apis.md`.

**Fallback — browser automation** (when a script is blocked — e.g. a Walmart **Press-&-Hold** challenge: solve it once in the headed browser, then re-run the script — for **Costco**, or interactive flows). Needs the headed full-Chromium Playwright MCP; **verify it's set up (don't assume)** — `claude mcp get playwright` Connected and the `mcp__playwright__browser_*` tools loaded; if not, set it up via the **`tandoor-setup` skill** (§2) or skip to WebSearch and say so. Proven recipes in `references/shop-apis.md`:
- **Walmart**: `browser_navigate` to `https://www.walmart.ca/en/search?q=<broad term>`, scroll to load ALL results, scrape every tile, then `browser_evaluate` the chosen product's `__NEXT_DATA__`/JSON-LD `Offer`. Search is literal — if a term underperforms ("baby carrots" → baby food), retry the broad term ("carrots").
- **T&T**: `browser_navigate` a T&T page (for Akamai cookies), then `browser_evaluate` a same-origin `fetch('/graphql', …)` `ProductSearch` — same store-scoping headers the script uses. DOM scraping is the last-ditch fallback.

**Last resort — WebSearch.** For Walmart it's Canada-correct and surfaces direct `/en/ip/...` links with CAD prices; for T&T/Costco usually only a search link. Build the buy link via:
```bash
bash scripts/shop_search.sh walmart "apple juice 1L"   # returns the walmart.ca search link
bash scripts/shop_search.sh tnt     "bok choy"
bash scripts/shop_search.sh costco  "rice 10kg"
```
**Matching a specific product (e.g. "raw peeled shrimp, no tail"):** search a BROAD head term (`shrimp`), scroll to load ALL results, then filter locally with synonyms (`peeled`↔`P&D`, `tail off`↔`T/off`) and exclude near-misses (`cooked`, `easy-peel`/`EZ peel` = shell-on, `breaded`). **Confirm attributes from the product's own description, not the tile/carousel** — "easy-peel" ≠ "peeled". If an attribute isn't stated, report it as unspecified rather than assuming. (Details + the gotchas that motivated this: `references/shop-apis.md`.)

For each item, per shop (Walmart, T&T, Costco):
- **search the store and compare the full result set — never settle on the first hit.** Surface the realistic options (sizes/brands) and pick the winner on price/quality, consulting `memory/preferences.md`;
- normalize price to a comparable unit (per 100 g / per unit / per L) before picking a winner — pack sizes differ, especially Costco bulk;
- note quality signals the user cares about (brand, organic, freshness).
Be honest about the source: prices from the **scripts/browser GraphQL are live, store-scoped quotes** (still note the store/postal they're scoped to); prices from **WebSearch are estimates as of today** that vary by location. If a shop's `api.enabled` is true, use that script/API and fall back to browser → WebSearch on error.

## 5. Output the buy list
Factor each store's **delivery/shipping fee from `memory/preferences.md`** (currently T&T $5 over $59 min, Walmart free over $35 min) into the basket total — a per-item price win can flip once shipping is added, so prefer **consolidating a run to one store** to pay the fee once (and check free-shipping thresholds). Show the per-store subtotal + fee + all-in total.
Produce a clear table / list, grouped by shop, with one clickable **link per item** (deep product link if found, else the `search_url` with the URL-encoded query). For each item include: chosen shop, product/size, price (and normalized price), why it won (price/quality/preference), and any substitution applied. End with a short summary (estimated total, items skipped because already in pantry, replacements due to expiry/staleness).

## 6. Update memory
Append the user's decisions and any new product experiences to `memory/preferences.md` (dated, short) — chosen brands, accepted/rejected substitutions, store-by-category preferences. This file is the long-term memory; read it at the start of every run and keep it current.

## Honesty guardrails
- Don't claim you queried a store API when you used web search — say which you used.
- Don't invent prices, stock, or links. A search link you constructed is fine; a fake product URL is not.
- If the pantry/cook-plan data is empty or the token is missing, say so and stop — don't proceed on assumptions.
