# Shop access reality check

**Read this before promising "I searched the store."** None of the three grocers has a *documented*
public price API, but two of them (T&T, Walmart) are fully reachable with a **Chrome TLS-impersonating
client (`curl_cffi`, `impersonate="chrome"`)** — their "blocks" are just TLS/JA3 fingerprinting, which
curl_cffi defeats with no browser. Be honest about how prices/links were obtained.

| Shop | Best method | Notes |
|------|-------------|-------|
| **T&T Supermarket** | **`scripts/tnt_graphql.py`** — internal Magento **GraphQL**, clean structured JSON. | Best of the three. Plain curl → 403 (Akamai TLS fingerprint); curl_cffi chrome → 200. See T&T section. |
| **Walmart** | **`scripts/walmart_search.py`** — parses the page's embedded `__NEXT_DATA__` JSON. | Plain curl/WebFetch → **418**; curl_cffi chrome → 200. Search is headless; product pages need a homepage warm-up (script does it) and can occasionally hit a Press-&-Hold challenge → fall back to headed browser. SerpApi/Scavio Walmart APIs are **US-only**, useless for walmart.ca. See Walmart section. |
| **Costco** | `WebSearch` + `CatalogSearch` link (not yet cracked). | Login/region-gated; warehouse-only items aren't online. Try curl_cffi the same way if needed. |

> Tested June 2026: WebSearch returned direct walmart.ca product links + CAD prices (e.g. Great Value 100% Apple Juice 1L ≈ CAD $1.68). WebFetch of walmart.ca returned **418** and T&T returned **403** — i.e. plain fetches/naive scrapers are refused. **Update (June 2026):** T&T's 403 is purely a TLS-fingerprint block — a Chrome-impersonating client (`curl_cffi`) gets clean JSON from its GraphQL API with no browser needed. See **"T&T — internal GraphQL API"** below.

## T&T — internal GraphQL API (the good path; no browser)

T&T's storefront is **Adobe Commerce / Magento PWA**. All product data — search, prices, images,
categories — comes from one open endpoint: `https://www.tntsupermarket.com/graphql` (GET, url-encoded
`query`/`variables`, prices in **CAD**). No auth.

**Why plain curl fails and how to beat it.** The 403 is **Akamai Bot Manager fingerprinting the
TLS/JA3/HTTP2 stack** — not a missing cookie. A spoofed User-Agent or even replayed `_abck`/`bm_sz`
cookies still 403. The fix is a client that sends Chrome's *real* TLS handshake: **`curl_cffi` with
`impersonate="chrome"`**. A cold GraphQL GET then returns 200 with clean JSON — **no browser, no
proxy, no warm-up**. (Confirmed June 2026: plain `requests`/curl → 403; `curl_cffi` chrome → 200.)

**Use the script** (`scripts/tnt_graphql.py`, needs `uv pip install curl_cffi` once):
```bash
python scripts/tnt_graphql.py search "tofu" --page-size 10   # → total_count + tidied items
python scripts/tnt_graphql.py product 73156801-tnt-fresh-tofu  # detail by url_key OR sku
python scripts/tnt_graphql.py images 73156801-tnt-fresh-tofu <outdir>  # download imgs as JPEG
python scripts/tnt_graphql.py raw '<gql query>' '<json vars>'  # escape hatch for other queries
```
`search` returns per item: `sku`, `name`, `size`, `final_price` (current/sale), `regular_price`
(was), `on_sale`, `stock`, `image`, and the product `url`. `product` adds `gallery` (product
photos), `content_images` (marketing/spec/**nutrition** images), `breadcrumbs`, `info`, and `rating`.

**Store-scoping (price/availability vary by store).** T&T scopes results to a store via request
**headers**, not the query — `x-prefered-store-code`, `x-postcode`, `x-current-shipping-method`,
`content-currency`, `store`. The script sends a Greater-Toronto default (`x-prefered-store-code: UV`,
`x-postcode: L3T`, delivery); a *valid* store code changes `total_count`/availability (an invalid one
returns 0 results). Override per call with `--store-code <CODE> --postcode <FSA>` for another location.
The same headers work from the browser fetch (below) — confirmed they shift availability (e.g. "egg":
174 items store-scoped vs 169 national).

### Reading nutrition facts from T&T (it works — via image OCR)
T&T has **no structured nutrition fields**, but it *does* publish the **Nutrition Facts panel as an
image** in `content_images` (and an ingredients/specs image alongside). You can read it:
1. `python scripts/tnt_graphql.py images <url_key|sku> <outdir>` — downloads all product + content
   images as real **JPEGs**. (Critical: the media server content-negotiates and returns **AVIF** by
   default, which the vision Read tool can't parse — the script forces `Accept: image/jpeg`. If you
   fetch an image URL yourself, do the same or you'll get an unreadable `ftyp…`/AVIF file.)
2. Open the `*_content*.jpg` files with the **Read tool (vision)** and OCR the panel. Confirmed June
   2026 on T&T Fresh Tofu: the panel read cleanly (Calories 60, Fat 3 g, Protein 6 g, Calcium 15 %,
   ingredients: water, soybeans (non-GMO), calcium sulphate, glucono-delta-lactone — per 88 g).

Caveats: values are per the label's serving size (often not 100 g — convert if you need per-100 g);
the nutrition image isn't always present or isn't always the same content slot, so scan the content
images. For a guaranteed structured source, USDA FoodData Central is still the fallback.

**Search-quality note:** the BROAD-head-term-then-filter-locally rule below still applies — T&T's
relevance search is literal. Search `shrimp`, not `peeled deveined shrimp`, then filter the JSON
yourself. Bump `--page-size` (e.g. 40) to load enough to filter.

**Raw schema cheat-sheet** (for `raw` / extending the script):
- Search: `products(search:$t pageSize:Int currentPage:Int sort:{relevance:DESC} filter:ProductAttributeFilterInput)` → `items{...} total_count page_info{...}`.
- Detail: `products(filter:{url_key:{eq:$k}})` or `{sku:{eq:$k}}`.
- Prices: `price_range.minimum_price.final_price.value` (sale) vs `price.regularPrice.amount.value` / `was_price` (regular).
- Images: `small_image.url` is ready-to-use; gallery = `https://www.tntsupermarket.com/media/catalog/product` + `media_gallery_entries[].file`.
- Categories: `route(url:"…path….html"){...on CategoryInterface{uid}}` → `products(filter:{category_uid:{eq:$uid}})`.
- Weighed items: `uom_type:2` + `weight_uom:"lb"` means priced by the pound. Product link = `https://www.tntsupermarket.com/eng/<url_key><url_suffix>`.
- Other ops seen in traffic: `getProductFiltersBySearch` (facets/aggregations), `categoryList`/`getMegaMenu` (category tree), `ResolveURL` (path→id).
- **Nutrition is image-only** — not a structured field, but published as a JPG in `new_description.list` (`type:"IMAGE"`) → exposed by the script as `content_images`. Readable via the `images` command + vision OCR (see "Reading nutrition facts" above). To put those numbers on a Tandoor recipe/food, see recipe-importer's `references/premade-items.md`.

## Walmart — search & product via `__NEXT_DATA__` (the good path; mostly headless)

walmart.ca is a **Next.js** app: every page embeds a `<script id="__NEXT_DATA__">` JSON blob with the
fully-rendered data — no need to call their internal API. There's no documented price API (and the
US-only SerpApi/Scavio Walmart APIs do **not** cover walmart.ca). Plain curl/WebFetch → **HTTP 418**;
that's just Akamai TLS fingerprinting, so **`curl_cffi` `impersonate="chrome"` → 200**.

**Use the script** (`scripts/walmart_search.py`, needs `uv pip install curl_cffi` once):
```bash
python scripts/walmart_search.py search "tofu" [--page 2] [--all-pages]
python scripts/walmart_search.py product 206880            # usItemId, /en/ip/ path, or full URL
```
- **Search** (`/en/search?q=`) is reliably headless. Per item: `usItemId`, `name`, `brand`, `price`,
  `price_str`, `unit_price`, `was_price`, `on_sale`, `stock`, `seller`, `rating`, `num_reviews`,
  `sponsored`, `image`, `url`. Pagination: `&page=N` (the parsed `max_page`/`total_count` tell you how
  far); `--all-pages` walks up to 10 pages.
- **Product** (`/en/ip/<slug>/<usItemId>`): the script hits the homepage first to pick up cookies,
  which usually gets curl_cffi through. Returns `shortDescription`, `ingredients`, `specifications`,
  `price`, and `nutritionFacts`. **Occasionally** a `/ip/` page still returns a **"Press & Hold"**
  challenge (JS, curl_cffi can't solve it) — the script detects this and tells you. **When it happens:
  open the URL in the headed Playwright browser and solve the Press & Hold once (hold the button until
  it clears), then re-run the script — solving it unblocks the site for your IP/session, so curl_cffi
  goes through again and you can keep using the API.** (You don't have to stay in the browser; but if
  you're already there, you can also just read `__NEXT_DATA__` on the page directly.)

**Nutrition:** the schema exists at `initialData.data.idml.nutritionFacts`
(`calorieInfo`/`keyNutrients`/`vitaminMinerals`/`servingInfo`) but is **often null** on walmart.ca
grocery items; `idml.ingredients` and `idml.specifications` are usually populated. **When
`nutritionFacts` is null, the Nutrition Facts panel is usually one of the product gallery images** —
get them from `initialData.data.product.imageInfo.allImages[].url`, download as JPEG/PNG (append
`?odnHeight=1500&odnWidth=1500` for a legible size), and OCR with the vision Read tool — exactly like
T&T's content images. (Confirmed June 2026 on Sealtest 6% Milk: structured `nutritionFacts` was null,
but a gallery image carried the full panel — 220 cal / 15 g fat / 8 g protein per 250 mL.) USDA
FoodData Central is the last-resort fallback.

**Where the data lives in `__NEXT_DATA__`:**
- Search: `props.pageProps.initialData.searchResult.itemStacks[].items[]` (filter `__typename=="Product"`); counts in `aggregatedCount`/`count`, paging in `paginationV2.maxPage`.
- Product: `props.pageProps.initialData.data.{product, idml, reviews}`.
- Internal API (FYI, not needed): `/orchestra/*/graphql` persisted queries — require PerimeterX cookies + query-hash headers; skip them, `__NEXT_DATA__` already has everything.

## Default strategy: WebSearch (no keys, Canada-correct)
*(legacy fallback — prefer the per-shop scripts above for T&T and Walmart)*
For each item to buy, per shop:
1. `WebSearch` for `"<shop> <item> price <region>"` (add brand/size from `memory/preferences.md`). For Walmart, also try `"<item> walmart.ca /en/ip"` to get a **direct product link**.
2. Build the **buy link** from the result: prefer a direct product URL WebSearch surfaced; otherwise the shop's `search_url` from `config/shops.json` (replace `{query}` with the URL-encoded item). `scripts/shop_search.sh <shop> "<item>"` returns that search link for you.
3. Tell the user prices are **web-search estimates as of <date>**, not live quotes, and vary by store/postal code.

## Browser automation: the working setup + proven recipes
**Prefer the `curl_cffi` scripts above** (T&T + Walmart) — they're faster, headless, and return clean
JSON. Use this browser path as a **fallback**: when curl_cffi hits a Walmart Press-&-Hold challenge,
for Costco, or for any interactive flow. A plain `WebFetch` still can't reach these sites; a real
browser (Playwright MCP, `mcp__playwright__browser_*`) can — **but only the full Chromium, not the
headless shell.** Tested June 2026: with `--headless` (chrome-headless-shell) Akamai returns
**"Forbidden"** (Walmart) / **"Access Denied"** (T&T); the **full Chromium running headed** passes
both. (For Walmart product pages, read `__NEXT_DATA__` in the browser — same JSON shape the script
parses: `initialData.data.{product,idml,reviews}`.)

**Setup lives in the `tandoor-setup` skill (§2)** — registering the headed-Chromium Playwright MCP and
the `~/.claude/playwright-mcp-config.json` (with an `outputDir` outside any git repo). **Before the
first browser action, verify it's up (don't assume):** `claude mcp get playwright` shows Connected and
the `mcp__playwright__browser_*` tools are loaded. If not, set it up there first, or fall back to
WebSearch and say so.

**Recipe — Walmart (FALLBACK — prefer `scripts/walmart_search.py`; use this only if curl_cffi is challenged):**
1. `browser_navigate` to the product page `https://www.walmart.ca/en/ip/<slug>/<id>` (get the link from WebSearch, e.g. `"<item> walmart.ca /en/ip"`).
2. `browser_evaluate` to read the JSON-LD offer:
   ```js
   () => { for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
     try { for (const d of [].concat(JSON.parse(s.textContent))) for (const o of [].concat(d.offers||[]))
       if (o.price!=null) return {price:o.price, currency:o.priceCurrency, availability:(o.availability||'').split('/').pop()};
     } catch(e){} } return null; }
   ```
   → e.g. `{price:1.68, currency:"CAD", availability:"InStock"}`.

**Recipe — T&T browser fallback (same GraphQL, via the browser — prefer `scripts/tnt_graphql.py`; use
this only if curl_cffi is unavailable).** Plain `curl` to `/graphql` gets Akamai 403, but a
**same-origin `fetch` from inside a loaded T&T page** (run via `browser_evaluate`) returns the same
clean JSON the script does — no scrolling, no card scraping. One `ProductSearch` call returns every
result.
1. `browser_navigate` to any T&T page so the browser holds the Akamai cookies, e.g.
   `https://www.tntsupermarket.com/eng/search.html?query=<broad term>`.
2. `browser_evaluate` this fetch (set `pageSize` high to get all items in one call):
   ```js
   async () => {
     const body = { operationName:"ProductSearch",
       variables:{currentPage:1, pageSize:100, filters:{}, inputText:"shrimp", sort:{relevance:"DESC"}},
       query:"query ProductSearch($currentPage:Int=1 $inputText:String! $pageSize:Int=6 $filters:ProductAttributeFilterInput! $sort:ProductAttributeSortInput){products(currentPage:$currentPage pageSize:$pageSize search:$inputText filter:$filters sort:$sort){items{sku name stock_status url_key url_suffix uom_type weight_uom price_range{minimum_price{final_price{value currency}}} small_image{url}}total_count page_info{total_pages current_page}}}" };
     const r = await fetch("/graphql", { method:"POST", headers:{
       "content-type":"application/json", "store":"default", "content-currency":"CAD",
       "x-prefered-store-code":"UV", "x-postcode":"L3T", "x-current-shipping-method":"delivery"
     }, body: JSON.stringify(body) });
     return (await r.json()).data.products;   // {items:[...], total_count, page_info}
   }
   ```
   - **Store-accurate pricing = the request headers** (same as the script): `x-prefered-store-code` +
     `x-postcode` (+ `x-current-shipping-method`, `content-currency`). `UV`/`L3T` is a GTA default;
     change them for another location. No login needed (guest).
   - Product link = `https://www.tntsupermarket.com/eng/<url_key><url_suffix>`. Price =
     `price_range.minimum_price.final_price`. `uom_type:2`+`weight_uom:"lb"` = priced by the pound.
   - Then **filter locally** over the JSON (see gotchas below) — clean fields, not scraped tiles.
   - **Last-ditch DOM scrape** (only if the GraphQL shape changes / fetch refused): scroll the
     `search.html` page to lazy-load all `a[href$=".html"]` cards (`/eng/<id>-<slug>.html`) and read the
     nearest `$price`. e.g. *Ocean Jewel Frozen Raw White Shrimp P&D 31/40 — $8.99*.

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
