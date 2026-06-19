#!/usr/bin/env bash
# Build a website search link for a shop.
#
# None of the target grocers (Walmart, T&T, Costco) have a usable public price API for our region
# (the US-only SerpApi/Scavio Walmart APIs do NOT cover walmart.ca). Direct page fetches are blocked
# by bot defenses (walmart.ca -> HTTP 418, T&T -> HTTP 403). So the reliable path is:
#   1. Use WebSearch for current price/availability (Canada-correct).
#   2. Give the search_url below (or a direct product link WebSearch surfaced) as the buy link.
# For structured data behind logins/bot-walls you need a real browser-automation tool (see
# references/shop-apis.md) -- a plain script cannot reach it.
#
# Requires: curl is NOT needed; just jq.
#
# Usage:
#   bash shop_search.sh walmart "olive oil 750ml"
#   bash shop_search.sh tnt     "bok choy"
#   bash shop_search.sh costco  "rice 10kg"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHOPS_JSON="${SCRIPT_DIR}/../config/shops.json"

shop="${1:-}"
query="${2:-}"
if [[ -z "$shop" || -z "$query" ]]; then
  echo "usage: bash shop_search.sh <walmart|tnt|costco> \"<query>\"" >&2
  exit 2
fi

enc="$(jq -rn --arg q "$query" '$q|@uri')"
search_url="$(jq -r --arg id "$shop" '.shops[] | select(.id==$id) | .search_url' "$SHOPS_JSON" | sed "s/{query}/${enc}/")"
if [[ -z "$search_url" || "$search_url" == "null" ]]; then
  echo "unknown shop: $shop" >&2
  exit 2
fi

jq -n --arg shop "$shop" --arg q "$query" --arg url "$search_url" \
  '{shop:$shop, query:$q, source:"web", search_url:$url,
    note:"No public API for this grocer. Use WebSearch for price/availability, then give this search_url (or a direct product link WebSearch surfaced) as the buy link. Direct fetches are blocked by bot defenses."}'
