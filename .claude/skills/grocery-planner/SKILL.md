---
name: grocery-planner
description: Plan a grocery run from a Tandoor instance. Reads the Cook Plan, its recipes, the shopping list, and the pantry (with stale/expiry status) over the Tandoor REST API via bash, suggests pantry substitutions and asks the user to decide, compares price/quality across Walmart, T&T, and Costco, and outputs a per-item list of buy links. Use when the user wants to plan shopping, decide what to buy, find substitutions, or compare grocery prices for their meal plan.
---

# Grocery Planner

Turn what's planned (Cook Plan + shopping list) and what's on hand (pantry) into a concrete, link-by-link buy list across Walmart, T&T Supermarket, and Costco — after checking the pantry for substitutions and asking the user to decide.

## 0. Prerequisites (check first)

**First-time setup (do once):**
1. **Memory file** — the skill reads/writes `memory/preferences.md`, which is gitignored (personal).
   Create it from the tracked template:
   ```bash
   cp memory/preferences.md.example memory/preferences.md
   ```
2. **Credentials** — export your Tandoor connection. The token needs **read + write** scope (web UI →
   Settings → API → Access Tokens):
   ```bash
   export TANDOOR_URL="https://your-tandoor.example"   # no trailing slash
   export TANDOOR_TOKEN="tda_…"
   ```
3. **Playwright (browser automation) for live prices** — set up the Playwright MCP per the "working
   setup" in `references/shop-apis.md`: headed full Chromium (`--browser chromium`, **no**
   `--headless`) with `env: {"DISPLAY": ":0"}`, and a `~/.claude/playwright-mcp-config.json` with an
   `outputDir` **outside any git repo** plus the launch flags that keep the headed browser responsive
   while backgrounded:
   ```json
   {
     "outputDir": "/home/<user>/.cache/playwright-mcp",
     "browser": {
       "launchOptions": {
         "args": [
           "--disable-renderer-backgrounding",
           "--disable-background-timer-throttling",
           "--disable-backgrounding-occluded-windows"
         ]
       }
     }
   }
   ```
   Config changes take effect on the next MCP restart. Without it, the skill falls back to WebSearch
   (say so when it does).

Ongoing prerequisites:
- `curl` and `jq` available.
- Env vars set: `TANDOOR_URL` (default `http://localhost:8000`) and `TANDOOR_TOKEN`.
  - The token is an **OAuth2 access token**: Tandoor web UI → Settings → API → Access Tokens. If `TANDOOR_TOKEN` is unset, the scripts error out — tell the user how to create one rather than guessing.
- Paths below are relative to this skill directory.

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
Read `config/shops.json` and `references/shop-apis.md` first. None of these grocers has a usable public price API for Canada, and plain fetches are blocked (418/403). Two ways to get prices:

**Preferred — browser automation (live Canadian prices) if the `mcp__playwright__browser_*` tools are available.** Follow the proven recipes in `references/shop-apis.md`:
- **Walmart**: WebSearch for the `walmart.ca/en/ip/...` link → `browser_navigate` → `browser_evaluate` the JSON-LD `Offer` (price/currency/availability).
- **T&T**: `browser_navigate` the homepage → set Location (`#region`) if you need store-accurate prices → click the `fakeinput` button to reveal `#search` → `browser_type` (submit) → scrape `/eng/<id>-<slug>.html` product cards.
- Requires the headed full-Chromium setup (a browser window appears); if the tools aren't loaded, fall back to web search.
- **First, verify the Playwright config is set up (don't assume).** If `~/.claude/playwright-mcp-config.json` is missing — especially its `outputDir` (kept outside any git repo so it doesn't litter `.playwright-mcp/` into the project) — or the headed-Chromium launch args / `DISPLAY` aren't configured, set it up per the "Browser automation: the working setup" section of `references/shop-apis.md` before browsing (or fall back to WebSearch and say so).

**Fallback — WebSearch.** For Walmart it's Canada-correct and surfaces direct `/en/ip/...` links with CAD prices; for T&T/Costco usually only a search link. Build the buy link via:
```bash
bash scripts/shop_search.sh walmart "apple juice 1L"   # returns the walmart.ca search link
bash scripts/shop_search.sh tnt     "bok choy"
bash scripts/shop_search.sh costco  "rice 10kg"
```
**Matching a specific product (e.g. "raw peeled shrimp, no tail"):** search a BROAD head term (`shrimp`), scroll to load ALL results, then filter locally with synonyms (`peeled`↔`P&D`, `tail off`↔`T/off`) and exclude near-misses (`cooked`, `easy-peel`/`EZ peel` = shell-on, `breaded`). **Confirm attributes from the product's own description, not the tile/carousel** — "easy-peel" ≠ "peeled". If an attribute isn't stated, report it as unspecified rather than assuming. (Details + the gotchas that motivated this: `references/shop-apis.md`.)

For each item, per shop (Walmart, T&T, Costco):
- find current price + a representative product (size/brand), consulting `memory/preferences.md`;
- normalize price to a comparable unit (per 100 g / per unit / per L) before picking a winner — pack sizes differ, especially Costco bulk;
- note quality signals the user cares about (brand, organic, freshness).
State plainly that prices are **web-search estimates as of today**, not live API quotes, and vary by location/availability. If a shop's `api.enabled` is true, use that API and fall back to web search on error.

## 5. Output the buy list
Factor each store's **delivery/shipping fee from `memory/preferences.md`** (currently T&T $5, Walmart $9) into the basket total — a per-item price win can flip once shipping is added, so prefer **consolidating a run to one store** to pay the fee once (and check free-shipping thresholds). Show the per-store subtotal + fee + all-in total.
Produce a clear table / list, grouped by shop, with one clickable **link per item** (deep product link if found, else the `search_url` with the URL-encoded query). For each item include: chosen shop, product/size, price (and normalized price), why it won (price/quality/preference), and any substitution applied. End with a short summary (estimated total, items skipped because already in pantry, replacements due to expiry/staleness).

## 6. Update memory
Append the user's decisions and any new product experiences to `memory/preferences.md` (dated, short) — chosen brands, accepted/rejected substitutions, store-by-category preferences. This file is the long-term memory; read it at the start of every run and keep it current.

## Honesty guardrails
- Don't claim you queried a store API when you used web search — say which you used.
- Don't invent prices, stock, or links. A search link you constructed is fine; a fake product URL is not.
- If the pantry/cook-plan data is empty or the token is missing, say so and stop — don't proceed on assumptions.
