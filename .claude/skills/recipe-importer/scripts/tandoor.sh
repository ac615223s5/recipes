#!/usr/bin/env bash
# Read + write helper for importing recipes into a Tandoor instance over its REST API.
#
# Auth: Tandoor's API uses OAuth2 bearer tokens (SessionAuth + OAuth2Authentication).
#   Create one in the web UI: Settings -> API -> Access Tokens, then export it:
#     export TANDOOR_URL="http://localhost:8000"     # no trailing slash
#     export TANDOOR_TOKEN="<your access token>"
#
# Requires: curl, jq
#
# READ (matching context — fetch these before resolving an import):
#   bash tandoor.sh keywords                 # every keyword: id, name, description, full_name
#   bash tandoor.sh foods                    # every food: id, name, plural_name, category, full_name
#   bash tandoor.sh food-search "garlic"     # foods whose name matches a query
#   bash tandoor.sh units                    # every unit: id, name, plural_name, base_unit
#   bash tandoor.sh conversions [food_id]    # unit conversions (all, or for one food)
#   bash tandoor.sh property-types           # nutrition property types (Calories, Protein, ...)
#   bash tandoor.sh categories               # supermarket categories
#
# IMPORT / PARSE:
#   bash tandoor.sh from-url "https://..."   # scrape a website -> parsed recipe JSON (NOT yet saved)
#   bash tandoor.sh from-html < page.html    # same, from pasted HTML/JSON-LD on stdin
#   echo '["2 cups flour","1 clove garlic, minced"]' | bash tandoor.sh parse-ingredients
#
# WRITE (each reads a JSON body on stdin; prints the created object):
#   echo '{"name":"shallot","plural_name":"shallots"}'        | bash tandoor.sh create-food
#   echo '{"name":"clove","plural_name":"cloves"}'            | bash tandoor.sh create-unit
#   echo '{"base_amount":1,"base_unit":{"name":"clove"},...}' | bash tandoor.sh create-conversion
#   echo '{"name":"Calories","unit":"kcal"}'                  | bash tandoor.sh create-property-type
#   bash tandoor.sh create-recipe < recipe.json              # POST a full nested recipe
#
# GENERIC escape hatch:
#   bash tandoor.sh get  /api/food/?query=egg
#   echo '{...}' | bash tandoor.sh post /api/food/
#   echo '{...}' | bash tandoor.sh patch /api/food/42/

set -euo pipefail

TANDOOR_URL="${TANDOOR_URL:-http://localhost:8000}"
TANDOOR_URL="${TANDOOR_URL%/}"

if [[ -z "${TANDOOR_TOKEN:-}" ]]; then
  echo "ERROR: set TANDOOR_TOKEN (web UI -> Settings -> API -> Access Tokens) and TANDOOR_URL." >&2
  exit 1
fi

# ---- low-level HTTP -------------------------------------------------------
_get() {
  curl -fsS \
    -H "Authorization: Bearer ${TANDOOR_TOKEN}" \
    -H "Accept: application/json" \
    "${TANDOOR_URL}${1}"
}

_send() {
  # _send <METHOD> <path>   (JSON body on stdin)
  curl -fsS -X "$1" \
    -H "Authorization: Bearer ${TANDOOR_TOKEN}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "${TANDOOR_URL}${2}"
}

# Walk a paginated list endpoint and concatenate every page's .results.
# Pages are streamed to a temp file (NOT argv) and merged with `jq -s`, so this
# stays well clear of ARG_MAX no matter how many rows the endpoint returns.
_paged() {
  # _paged <path-with-query>   -> JSON array of all results
  local next="${TANDOOR_URL}${1}" page
  local tmp; tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  while [[ -n "$next" && "$next" != "null" ]]; do
    page="$(curl -fsS -H "Authorization: Bearer ${TANDOOR_TOKEN}" -H "Accept: application/json" "$next")"
    jq -c '.results // []' <<<"$page" >>"$tmp"
    next="$(jq -r '.next // ""' <<<"$page")"
  done
  jq -s 'add // []' "$tmp"
}

urlencode() { jq -rn --arg s "$1" '$s|@uri'; }

# ---- read: matching context ----------------------------------------------
keywords() {
  _paged "/api/keyword/?page_size=200" \
    | jq '[.[] | {id, name, description, full_name}]'
}

foods() {
  _paged "/api/food/?page_size=200" \
    | jq '[.[] | {id, name, plural_name,
                  category: (.supermarket_category.name // null),
                  full_name, fdc_id,
                  has_nutrition: ((.properties // []) | length > 0)}]'
}

food_search() {
  _get "/api/food/?query=$(urlencode "${1:?usage: food-search <query>}")&page_size=50" \
    | jq '[(.results // .)[] | {id, name, plural_name,
            category: (.supermarket_category.name // null), full_name}]'
}

units() {
  _paged "/api/unit/?page_size=200" \
    | jq '[.[] | {id, name, plural_name, description, base_unit}]'
}

conversions() {
  local q="/api/unit-conversion/?page_size=200"
  [[ $# -ge 1 && -n "${1:-}" ]] && q="${q}&food_id=${1}"
  _paged "$q" \
    | jq '[.[] | {id, name,
                  base_amount, base_unit: (.base_unit.name // null),
                  converted_amount, converted_unit: (.converted_unit.name // null),
                  food: (.food.name // null)}]'
}

property_types() {
  _paged "/api/property-type/?page_size=200" \
    | jq '[.[] | {id, name, unit, fdc_id}]'
}

categories() {
  _paged "/api/supermarket-category/?page_size=200" \
    | jq '[.[] | {id, name}]'
}

# ---- import / parse -------------------------------------------------------
from_url() {
  jq -n --arg u "${1:?usage: from-url <url>}" '{url:$u}' \
    | _send POST "/api/recipe-from-source/"
}

from_html() {
  # HTML / JSON-LD on stdin
  jq -Rs '{data: .}' \
    | _send POST "/api/recipe-from-source/"
}

parse_ingredients() {
  # JSON array of ingredient strings on stdin
  jq '{ingredients: .}' \
    | _send POST "/api/ingredient-parser/"
}

# ---- write ----------------------------------------------------------------
create_food()          { _send POST  "/api/food/"; }
create_unit()          { _send POST  "/api/unit/"; }
create_conversion()    { _send POST  "/api/unit-conversion/"; }
create_property_type() { _send POST  "/api/property-type/"; }
create_recipe()        { _send POST  "/api/recipe/"; }

cmd="${1:-}"; shift || true
case "$cmd" in
  keywords)            keywords ;;
  foods)               foods ;;
  food-search)         food_search "${1:-}" ;;
  units)               units ;;
  conversions)         conversions "${1:-}" ;;
  property-types)      property_types ;;
  categories)          categories ;;
  from-url)            from_url "${1:-}" ;;
  from-html)           from_html ;;
  parse-ingredients)   parse_ingredients ;;
  create-food)         create_food ;;
  create-unit)         create_unit ;;
  create-conversion)   create_conversion ;;
  create-property-type) create_property_type ;;
  create-recipe)       create_recipe ;;
  get)                 _get "${1:?usage: get <path>}" ;;
  post)                _send POST  "${1:?usage: post <path>}" ;;
  patch)               _send PATCH "${1:?usage: patch <path>}" ;;
  *) echo "unknown command: ${cmd:-<none>}" >&2
     echo "see header of this script for usage" >&2
     exit 2 ;;
esac
