#!/usr/bin/env bash
# Read planning data out of a Tandoor instance over its REST API.
#
# Auth: Tandoor's API uses OAuth2 bearer tokens (SessionAuth + OAuth2Authentication).
#   Create one in the web UI: Settings -> API -> Access Tokens, then export it:
#     export TANDOOR_URL="http://localhost:8000"     # no trailing slash
#     export TANDOOR_TOKEN="<your access token>"
#
# Requires: curl, jq
#
# Usage:
#   bash tandoor.sh cookplan          # undated meal plans (the "Cook Plan")
#   bash tandoor.sh recipes           # full detail of every recipe on the cook plan
#   bash tandoor.sh shopping          # open (unchecked) shopping list entries
#   bash tandoor.sh pantry            # every pantry item with stale + expiry status
#   bash tandoor.sh pantry-stale      # only items flagged stale
#   bash tandoor.sh pantry-expiring   # only items expired / expiring within 7 days
#   bash tandoor.sh all               # one JSON object with everything above

set -euo pipefail

TANDOOR_URL="${TANDOOR_URL:-http://localhost:8000}"
TANDOOR_URL="${TANDOOR_URL%/}"

if [[ -z "${TANDOOR_TOKEN:-}" ]]; then
  echo "ERROR: set TANDOOR_TOKEN (Settings -> API -> Access Tokens) and TANDOOR_URL." >&2
  exit 1
fi

api() {
  # api <path-with-leading-slash>
  curl -fsS \
    -H "Authorization: Bearer ${TANDOOR_TOKEN}" \
    -H "Accept: application/json" \
    "${TANDOOR_URL}${1}"
}

# jq helper: classify an inventory entry's expiry relative to today
JQ_EXPIRY='
def expiry_status:
  if (.expires // "") == "" then "none"
  else
    ((.expires | sub("T.*$";"") | strptime("%Y-%m-%d") | mktime) as $exp
     | (now | floor) as $today
     | if   $exp <  $today               then "expired"
       elif $exp < ($today + 7*86400)    then "expiring_soon"
       else "ok" end)
  end;
'

cookplan() {
  # undated meal plans == the Cook Plan
  api "/api/meal-plan/?undated=true&page_size=200" \
    | jq '[.results[] | {id, servings, title, recipe: (.recipe.id // null), recipe_name: (.recipe.name // .title)}]'
}

recipe_ids() {
  api "/api/meal-plan/?undated=true&page_size=200" \
    | jq -r '[.results[].recipe.id | select(. != null)] | unique | .[]'
}

recipes() {
  # full detail (steps -> ingredients -> food/unit/amount) for each recipe on the cook plan
  echo "["
  local first=1
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    [[ $first -eq 0 ]] && echo ","
    first=0
    api "/api/recipe/${id}/" | jq '{
      id, name, servings,
      ingredients: [ .steps[]?.ingredients[]?
        | select(.is_header | not)
        | {food: (.food.name // null), amount, unit: (.unit.name // null), note} ]
    }'
  done < <(recipe_ids)
  echo "]"
}

shopping() {
  # open (unchecked) shopping list entries, aggregated view
  api "/api/shopping-list-entry/?page_size=1000" \
    | jq '[.results[] | select(.checked == false)
        | {id, food: (.food.name // null), amount, unit: (.unit.name // null),
           lists: [(.shopping_lists // [])[].name],
           recipe: (.list_recipe_data.recipe_data.name // null)}]'
}

pantry() {
  # every pantry item with stale + expiry status
  api "/api/inventory-entry/?page_size=1000" \
    | jq "${JQ_EXPIRY}"' [.results[]
        | {id, food: (.food.name // null), amount, unit: (.unit.name // null),
           location: (.inventory_location.name // null),
           is_stale, last_verified_at, expires, expiry: expiry_status}]'
}

pantry_stale() {
  pantry | jq '[.[] | select(.is_stale == true)]'
}

pantry_expiring() {
  pantry | jq '[.[] | select(.expiry == "expired" or .expiry == "expiring_soon")]'
}

all() {
  jq -n \
    --argjson cookplan "$(cookplan)" \
    --argjson recipes "$(recipes)" \
    --argjson shopping "$(shopping)" \
    --argjson pantry "$(pantry)" \
    '{cookplan: $cookplan, recipes: $recipes, shopping: $shopping, pantry: $pantry}'
}

cmd="${1:-all}"
case "$cmd" in
  cookplan)        cookplan ;;
  recipes)         recipes ;;
  shopping)        shopping ;;
  pantry)          pantry ;;
  pantry-stale)    pantry_stale ;;
  pantry-expiring) pantry_expiring ;;
  all)             all ;;
  *) echo "unknown command: $cmd" >&2; exit 2 ;;
esac
