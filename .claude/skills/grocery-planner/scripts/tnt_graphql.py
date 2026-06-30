#!/usr/bin/env python3
"""Query T&T Supermarket's internal GraphQL API (Adobe Commerce / Magento PWA).

T&T sits behind Akamai Bot Manager: plain curl / requests / WebFetch get HTTP 403
"Access Denied" -- Akamai fingerprints the TLS/JA3/HTTP2 stack, so a spoofed
User-Agent or replayed cookies are NOT enough. The trick is `curl_cffi` with
`impersonate="chrome"`, which sends Chrome's real TLS handshake. No browser, no
proxy, no warm-up request needed -- a cold GraphQL GET returns clean JSON.

Endpoint: https://www.tntsupermarket.com/graphql  (GET, url-encoded query/variables)
Currency: CAD. Price/availability are STORE-SCOPED via request headers (see STORE below) —
defaults to a Greater-Toronto store; pass --store-code / --postcode for another location.

Setup (once):  uv pip install curl_cffi    (or: .venv/bin/pip install curl_cffi)

Usage (any command also takes --store-code <CODE> --postcode <FSA>):
  python tnt_graphql.py search "tofu" [--page-size 10]   # search products
  python tnt_graphql.py product 73156801-tnt-fresh-tofu  # detail by url_key OR sku
  python tnt_graphql.py images  73156801-tnt-fresh-tofu [outdir]  # download all imgs as JPEG
  python tnt_graphql.py raw '<graphql query>' '<json vars>'  # escape hatch

Output: JSON on stdout. `search` and `product` return tidied objects with
final_price (current/sale), regular_price (was), stock, image, and product URL.

Reading nutrition facts: T&T has NO structured nutrition data — the Nutrition Facts
panel is published as an IMAGE inside `content_images` (the product's marketing
content). `images` downloads every product+content image to a folder as real JPEGs;
then open them with the vision-capable Read tool to OCR the panel. NOTE the server
content-negotiates and returns AVIF by default (vision can't parse it), so always
request with `Accept: image/jpeg` (this script does).
"""
import json
import sys

try:
    from curl_cffi import requests
except ImportError:
    sys.exit("curl_cffi not installed. Run: uv pip install curl_cffi")

BASE = "https://www.tntsupermarket.com"
GQL = BASE + "/graphql"
IMG_BASE = BASE + "/media/catalog/product"  # + media_gallery_entries[].file
IMPERSONATE = "chrome"  # alias -> latest Chrome fingerprint curl_cffi supports
JPEG_ACCEPT = "image/jpeg,image/png,*/*;q=0.8"  # avoid AVIF default (vision can't read it)

# T&T scopes price/availability to a store via REQUEST HEADERS (not the query). A valid store code
# changes total_count/availability; an invalid one returns 0 results. Default = Greater-Toronto;
# override with --store-code / --postcode. (These ride along on every GraphQL call.)
STORE = {"x-prefered-store-code": "UV", "x-postcode": "L3T",
         "x-current-shipping-method": "delivery", "content-currency": "CAD", "store": "default"}


def gql(query, variables=None, operation=None):
    """Run one GraphQL GET. Returns the parsed `data` dict; raises on errors."""
    s = requests.Session(impersonate=IMPERSONATE)
    params = {"query": query}
    if operation:
        params["operationName"] = operation
    if variables is not None:
        params["variables"] = json.dumps(variables)
    r = s.get(GQL, params=params, headers=STORE, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code}: {r.text[:300]}")
    body = r.json()
    if body.get("errors"):
        raise SystemExit("GraphQL errors: " + json.dumps(body["errors"])[:500])
    return body["data"]


SEARCH_Q = """query ProductSearch($t:String!,$ps:Int!,$cp:Int!){
  products(search:$t pageSize:$ps currentPage:$cp sort:{relevance:DESC}){
    total_count page_info{current_page total_pages}
    items{sku name url_key url_suffix stock_status size_label uom_type weight_uom
      small_image{url}
      price_range{minimum_price{final_price{value currency}}}
      price{regularPrice{amount{value}}} was_price}}}"""

DETAIL_Q = """query Detail($f:ProductAttributeFilterInput!){
  products(filter:$f){items{sku name url_key url_suffix stock_status size_label
    uom_type weight_uom was_price
    breadcrumbs{label url}
    price_range{minimum_price{final_price{value currency}}}
    price{regularPrice{amount{value}}}
    media_gallery_entries{file label position media_type}
    short_description{html}
    new_description{list{label value type}}
    description{html}
    more_infomation{code label value}
    review{review_avg_score review_total_vote}}}}"""


def _tidy(it):
    """Flatten a product item into a compact, comparison-ready dict."""
    fp = (((it.get("price_range") or {}).get("minimum_price") or {}).get("final_price") or {})
    rp = (((it.get("price") or {}).get("regularPrice") or {}).get("amount") or {})
    url_key = it.get("url_key")
    suffix = it.get("url_suffix") or ".html"
    out = {
        "sku": it.get("sku"),
        "name": it.get("name"),
        "size": it.get("size_label") or None,
        "final_price": fp.get("value"),          # current / sale price (CAD)
        "regular_price": rp.get("value") or it.get("was_price"),  # original price
        "currency": fp.get("currency") or "CAD",
        "on_sale": fp.get("value") is not None and (rp.get("value") or it.get("was_price"))
        not in (None, fp.get("value")),
        "stock": it.get("stock_status"),
        "image": (it.get("small_image") or {}).get("url"),
        "url": f"{BASE}/eng/{url_key}{suffix}" if url_key else None,
    }
    if "media_gallery_entries" in it:
        out["gallery"] = [IMG_BASE + g["file"] for g in (it["media_gallery_entries"] or [])]
        # content_images = marketing/spec/NUTRITION images (Nutrition Facts panel lives here)
        nd = (it.get("new_description") or {}).get("list") or []
        out["content_images"] = [e["value"] for e in nd if e.get("type") == "IMAGE"]
        out["breadcrumbs"] = [b["label"] for b in (it.get("breadcrumbs") or [])]
        out["info"] = {m["label"]: m["value"] for m in (it.get("more_infomation") or [])}
        rev = it.get("review") or {}
        out["rating"] = rev.get("review_avg_score")
        out["rating_count"] = rev.get("review_total_vote")
    return out


def cmd_search(term, page_size=10):
    data = gql(SEARCH_Q, {"t": term, "ps": int(page_size), "cp": 1}, "ProductSearch")
    p = data["products"]
    return {"query": term, "total_count": p["total_count"],
            "items": [_tidy(i) for i in p["items"]]}


def cmd_product(key):
    # key may be a url_key (contains a dash) or a numeric sku
    field = "sku" if key.isdigit() else "url_key"
    data = gql(DETAIL_Q, {"f": {field: {"eq": key}}}, "Detail")
    items = data["products"]["items"]
    if not items:
        raise SystemExit(f"no product found for {field}={key}")
    return _tidy(items[0])


def cmd_images(key, outdir="tnt_images"):
    """Download every product + content image for one product as real JPEGs.

    Returns the saved paths. content_* files are the marketing/nutrition images —
    open them with the vision Read tool to OCR the Nutrition Facts panel.
    """
    import os
    p = cmd_product(key)
    os.makedirs(outdir, exist_ok=True)
    s = requests.Session(impersonate=IMPERSONATE)
    saved = []
    jobs = [("gallery", i, u) for i, u in enumerate(p.get("gallery") or [])]
    jobs += [("content", i, u) for i, u in enumerate(p.get("content_images") or [])]
    for kind, i, url in jobs:
        r = s.get(url, headers={"Accept": JPEG_ACCEPT}, timeout=30)
        if r.status_code != 200 or not r.content[:3] == b"\xff\xd8\xff":
            saved.append({"url": url, "ok": False, "status": r.status_code,
                          "note": "not a JPEG (got %s)" % r.headers.get("content-type")})
            continue
        path = os.path.join(outdir, f"{p['sku']}_{kind}{i}.jpg")
        with open(path, "wb") as f:
            f.write(r.content)
        saved.append({"url": url, "ok": True, "path": path, "kind": kind})
    return {"sku": p["sku"], "name": p["name"], "outdir": outdir,
            "hint": "open content_* files with the vision Read tool to read Nutrition Facts",
            "images": saved}


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    # global store-scoping overrides (apply to every command)
    if "--store-code" in a:
        STORE["x-prefered-store-code"] = a[a.index("--store-code") + 1]
    if "--postcode" in a:
        STORE["x-postcode"] = a[a.index("--postcode") + 1]
    cmd = a[0]
    if cmd == "search":
        if len(a) < 2:
            sys.exit("usage: tnt_graphql.py search \"<term>\" [--page-size N]")
        ps = 10
        if "--page-size" in a:
            ps = a[a.index("--page-size") + 1]
        print(json.dumps(cmd_search(a[1], ps), indent=2, ensure_ascii=False))
    elif cmd == "product":
        if len(a) < 2:
            sys.exit("usage: tnt_graphql.py product <url_key|sku>")
        print(json.dumps(cmd_product(a[1]), indent=2, ensure_ascii=False))
    elif cmd == "images":
        if len(a) < 2:
            sys.exit("usage: tnt_graphql.py images <url_key|sku> [outdir]")
        outdir = a[2] if len(a) > 2 and not a[2].startswith("--") else "tnt_images"
        print(json.dumps(cmd_images(a[1], outdir), indent=2, ensure_ascii=False))
    elif cmd == "raw":
        variables = json.loads(a[2]) if len(a) > 2 else None
        print(json.dumps(gql(a[1], variables), indent=2, ensure_ascii=False))
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
