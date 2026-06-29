#!/usr/bin/env python3
"""Query walmart.ca product search via its embedded Next.js data (no public API).

walmart.ca is a Next.js app: every page ships a `<script id="__NEXT_DATA__">` JSON
blob with the fully-rendered data. There is no documented price API, and plain
curl/requests/WebFetch get HTTP 418 -- the block is Akamai TLS fingerprinting, so
`curl_cffi` with `impersonate="chrome"` sails past it for **search pages** and we
parse the results straight out of __NEXT_DATA__. No browser needed.

  Search page  -> reachable with curl_cffi (this script).      [headless OK]
  /ip/ product -> usually reachable too (the `product` command hits the homepage
                  first to pick up cookies). OCCASIONALLY a "Press & Hold" JS
                  challenge appears that curl_cffi CANNOT solve -- the command
                  detects it and says so. Fix: open the URL in the headed
                  Playwright browser, solve the Press & Hold once, then RE-RUN
                  this script -- solving it unblocks the site for your IP/session
                  and curl_cffi goes through again (see references/shop-apis.md).

Internal API: walmart.ca uses `/orchestra/*/graphql` (persisted queries) under the
hood, but those need PerimeterX/bot cookies + query-hash headers -- not worth it
when __NEXT_DATA__ already carries the data.

Setup (once):  uv pip install curl_cffi

Usage:
  python walmart_search.py search "tofu" [--page 1] [--all-pages]
  python walmart_search.py product 206880   # or a full /en/ip/... URL (needs browser)

Output: JSON. `search` returns tidied items: usItemId, name, brand, price,
unit_price, was_price, on_sale, stock, image, rating, url. Prices in CAD; results
are national/default-store -- a selected store/postal code can differ.
"""
import json
import re
import sys

try:
    from curl_cffi import requests
except ImportError:
    sys.exit("curl_cffi not installed. Run: uv pip install curl_cffi")

BASE = "https://www.walmart.ca"
IMPERSONATE = "chrome"
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _next_data(html):
    m = NEXT_RE.search(html)
    if not m:
        if "Verify Your Identity" in html or "Robot or human" in html or "px-captcha" in html:
            raise SystemExit("BLOCKED: Walmart served a Press-&-Hold/CAPTCHA challenge. "
                             "Open this URL in the headed Playwright browser, solve the Press & Hold "
                             "once, then re-run this script -- it unblocks the site for your "
                             "IP/session and curl_cffi goes through again (see shop-apis.md).")
        raise SystemExit("no __NEXT_DATA__ in page (layout changed or blocked)")
    return json.loads(m.group(1))


def _session():
    return requests.Session(impersonate=IMPERSONATE)


def _tidy(it):
    pi = it.get("priceInfo") or {}
    img = (it.get("imageInfo") or {}).get("thumbnailUrl")
    url = it.get("canonicalUrl") or ""
    av = it.get("availabilityStatusV2") or {}
    return {
        "usItemId": it.get("usItemId"),
        "name": it.get("name"),
        "brand": it.get("brand"),
        "price": it.get("price"),
        "price_str": pi.get("linePriceDisplay") or pi.get("linePrice"),
        "unit_price": (pi.get("unitPrice") or "").strip() or None,
        "was_price": (pi.get("wasPrice") or "").strip() or None,
        "on_sale": bool((pi.get("savingsAmt") or 0)),
        "stock": av.get("value") or it.get("availabilityStatusDisplayValue"),
        "seller": it.get("sellerName"),
        "rating": it.get("averageRating"),
        "num_reviews": it.get("numberOfReviews"),
        "sponsored": bool(it.get("isSponsoredFlag")),
        "image": img,
        "url": (BASE + url) if url.startswith("/") else url,
    }


def _parse_search(html):
    sr = _next_data(html)["props"]["pageProps"]["initialData"]["searchResult"]
    stacks = sr.get("itemStacks") or []
    items = []
    for st in stacks:
        for it in (st.get("items") or []):
            if it.get("__typename") == "Product":
                items.append(_tidy(it))
    pg = sr.get("paginationV2") or {}
    return {
        "total_count": sr.get("aggregatedCount"),
        "per_page": sr.get("count"),
        "max_page": pg.get("maxPage"),
        "items": items,
    }


def cmd_search(term, page=1, all_pages=False):
    s = _session()
    from urllib.parse import quote
    q = quote(term)
    first = _parse_search(s.get(f"{BASE}/en/search?q={q}&page={page}", timeout=30).text)
    if not all_pages:
        first["page"] = page
        return first
    maxp = min(first.get("max_page") or 1, 10)
    for p in range(page + 1, maxp + 1):
        more = _parse_search(s.get(f"{BASE}/en/search?q={q}&page={p}", timeout=30).text)
        first["items"].extend(more["items"])
    first["pages_fetched"] = list(range(page, maxp + 1))
    return first


def cmd_product(ref):
    """Fetch a product page and pull structured detail from __NEXT_DATA__.

    Will usually hit the Press-&-Hold challenge under curl_cffi -- if so it says so,
    and you should load the URL in the headed Playwright browser and read
    __NEXT_DATA__ there (initialData.data.{product,idml,reviews}).
    """
    url = ref if ref.startswith("http") else (
        ref if ref.startswith("/en/ip/") else f"{BASE}/en/ip/{ref}")
    if not url.startswith("http"):
        url = BASE + url
    s = _session()
    s.get(f"{BASE}/", timeout=30)  # warm up
    data = _next_data(s.get(url, timeout=30).text)
    d = data["props"]["pageProps"]["initialData"]["data"]
    p = d.get("product") or {}
    idml = d.get("idml") or {}
    nf = idml.get("nutritionFacts") or {}
    return {
        "usItemId": p.get("usItemId"),
        "name": p.get("name"),
        "brand": p.get("brand"),
        "price": (p.get("priceInfo") or {}).get("currentPrice") or p.get("priceInfo"),
        "shortDescription": p.get("shortDescription"),
        "ingredients": ((idml.get("ingredients") or {}).get("ingredients") or {}).get("value"),
        "specifications": {s2.get("name"): s2.get("value") for s2 in (idml.get("specifications") or [])},
        # nutritionFacts schema: calorieInfo / keyNutrients / vitaminMinerals / servingInfo
        # -- present for some grocery items, often null. Falls back to USDA when null.
        "nutritionFacts": nf if any(nf.get(k) for k in
                                    ("calorieInfo", "keyNutrients", "vitaminMinerals", "servingInfo")) else None,
        "url": url,
    }


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "search":
        if len(a) < 2:
            sys.exit('usage: walmart_search.py search "<term>" [--page N] [--all-pages]')
        page = int(a[a.index("--page") + 1]) if "--page" in a else 1
        print(json.dumps(cmd_search(a[1], page, "--all-pages" in a), indent=2, ensure_ascii=False))
    elif cmd == "product":
        if len(a) < 2:
            sys.exit("usage: walmart_search.py product <usItemId|/en/ip/...|url>")
        print(json.dumps(cmd_product(a[1]), indent=2, ensure_ascii=False))
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
