---
name: recipe-importer
description: Import a recipe from a website URL or pasted text into a Tandoor instance over the REST API, reconciled against the existing database. Scrapes/parses the source, attaches matching existing keywords, renames each ingredient food to the matching "store item" already in the DB (creating new foods — with supermarket category and looked-up nutrition — when none match), folds unit spelling variants into existing units (creating new units plus sensible global/food-specific conversions), then saves the recipe after a review step. Use when the user wants to add/import a recipe from a link or pasted text and have it cleanly matched to their existing foods, units, and keywords.
---

# Recipe Importer

Take a recipe from a **URL or pasted text** and land it in Tandoor as a clean, fully-reconciled
recipe: existing keywords attached, every ingredient's food/unit matched to what's already in the
database (new ones created and enriched), saved only after you've shown the user the plan.

The value of this skill is the **reconciliation layer** — Tandoor's importer parses the page, but it
does not intelligently merge "crushed garlic" into your existing "garlic", look up nutrition for a
new food, or add unit conversions. That judgment is the work here.

## 0. Prerequisites

**First-time setup (do once):**
1. **Memory file** — the skill reads/writes `memory/import-notes.md`, which is gitignored (personal).
   Create it from the tracked template:
   ```bash
   cp memory/import-notes.md.example memory/import-notes.md
   ```
2. **Credentials** — export your Tandoor connection. The token needs **read + write** scope (web UI →
   Settings → API → Access Tokens):
   ```bash
   export TANDOOR_URL="https://your-tandoor.example"   # no trailing slash
   export TANDOOR_TOKEN="tda_…"
   ```

Ongoing prerequisites:
- `curl` + `jq` available. Env: `TANDOOR_URL` (default `http://localhost:8000`) and `TANDOOR_TOKEN`
  (web UI → Settings → API → Access Tokens). If the token is unset the scripts error — tell the user
  how to make one, don't guess. All paths below are relative to this skill directory.
- The token needs **read + write** scope. A token scoped only `mealplan` (or read-only) returns **403**
  on every call — if you see 403s, the scope is the cause; tell the user to recreate the token with
  read+write.

## 1. Get the parsed recipe
- **From a URL:** `bash scripts/tandoor.sh from-url "<url>"`. This calls Tandoor's scraper
  (recipe-scrapers / JSON-LD) and returns a parsed recipe object **without saving it**. The response
  has `.recipe` (steps → ingredients with `food.name`/`unit.name`/`amount`/`note`, plus `keywords`,
  `properties`, `servings`, `working_time`, `waiting_time`, `source_url`, `image_url`) and a
  `.duplicates` list of same-named recipes already in the space. If the scrape fails, fall back to
  fetching the page yourself (WebFetch) and either pipe the HTML to `from-html`, or parse it directly.
- **From pasted text:** parse it **yourself** into the same recipe shape (don't depend on the
  server's AI provider). Split into steps/instructions; extract each ingredient line. You can let
  `parse-ingredients` do the amount/unit/food split:
  `echo '["2 cups flour","1 clove garlic, minced"]' | bash scripts/tandoor.sh parse-ingredients`.
- **Capture the metadata**, don't drop it: name, description, servings + servings_text,
  working_time, waiting_time, `source_url` (set it so the recipe links back), and the image URL.

## 2. Check for an existing duplicate — then decide
If `.duplicates` is non-empty (or a `food-search`-style title check finds one), surface it and **ask**
whether to create a new recipe anyway, update, or abort. Don't silently create a second copy.

## 3. Load the database + memory for matching
Fetch the current lists once and keep them in context:
```bash
bash scripts/tandoor.sh keywords        # id, name, DESCRIPTION, full_name
bash scripts/tandoor.sh foods           # id, name, plural_name, category, has_nutrition
bash scripts/tandoor.sh units           # id, name, plural_name, base_unit
bash scripts/tandoor.sh conversions     # existing unit conversions
bash scripts/tandoor.sh property-types  # nutrition property types
bash scripts/tandoor.sh categories      # supermarket categories
```
Also read `memory/import-notes.md` (past normalizations) and `references/matching.md` (the rules).

## 4. Reconcile (the core) — see `references/matching.md` for the full rules
- **Keywords:** attach existing keywords whose name **or description** fits the recipe (cuisine /
  course / diet / method). Only existing ones — list any obviously-missing keyword as a suggestion,
  don't create it.
- **Foods:** for each ingredient, find the existing food that is the **same store item**. Prep/cut/
  form do not change the food — rename to the DB food and move the descriptor to the ingredient
  `note` ("crushed garlic" → food **garlic**, note "crushed"). But a different SKU is a different
  food ("tomato sauce" ≠ tomato; "garlic powder" ≠ garlic). For genuine judgment calls, ask. Foods
  with no match get **created** (step 4a).
- **Units:** fold spelling/abbreviation variants into the existing unit (tbsp = tablespoon = T). Only
  genuinely new units get created — then add conversions: density-independent ones global
  (`1 tbsp = 3 tsp`), anything ingredient-dependent **food-specific** (`1 clove garlic = 5 g`).
  Never add a volume↔weight conversion as global.

### 4a. Create + enrich each new food — see `references/nutrition.md`
Canonical singular name + plural; assign an existing supermarket **category**; look up
nutrition **per 100 g** (USDA FoodData Central — store the `fdc_id`); ensure the Calories/Protein/
Fat/Carbohydrates **PropertyTypes** exist; create the food with `properties_food_amount: 100` +
`properties_food_unit: {name:"g"}` and the property values. Nutrition is an estimate — say so.

## 5. Show the plan and get the go-ahead (review gate)
Before writing anything, present a concise table:
- keywords to attach; per ingredient: source text → matched food (or **NEW**) + unit (or **NEW**) +
  amount + note; new units + conversions to add; new foods + their category/nutrition.
Flag every **NEW** create and every non-obvious merge. Use AskUserQuestion for the judgment-call
swaps. Writes mutate the **shared** space (foods/units/conversions everyone sees), so confirm first —
unless the user has said to just import without asking.

## 6. Write to the database (order matters)
Create dependencies before the recipe so they resolve by name:
1. New **PropertyTypes** (if any) → `create-property-type`.
2. New **foods** → `create-food`, then **PATCH the nutrition properties** onto each (two steps — see
   `nutrition.md`; inline properties on create do not stick).
3. New **units** → `create-unit`; then **conversions** → `create-conversion`.
4. The **recipe** → `create-recipe` (full nested body on stdin): steps → ingredients referencing the
   resolved `food`/`unit`, `amount`, `note`, `is_header`; plus matched `keywords`, `servings`,
   `servings_text`, `working_time`, `waiting_time`, `source_url`, `description`.
   - **Each nested `food` and `unit` must include `name`** (even when you pass `id`) — the ingredient
     serializer requires the name field or the whole POST 400s. Pass `{"id":<id>,"name":"<exact>"}`.
     A unit-less ingredient (e.g. "1 egg") takes `"unit": null`.
   - The scraper dumps every ingredient onto step 0; re-group sensibly. A common clean shape: merge
     the source's alternating "title" / "detail" steps into one step each (title → step `name`,
     detail → `instruction`) and attach the ingredient list to the first step with
     `show_ingredients_table: true`.
5. **Image** (optional, nice): `curl -X PUT -F "image_url=<url>" /api/recipe/<id>/image/` — the recipe
   `image` action fetches and stores it server-side.
Report the new recipe's id/URL. If a write fails, surface the real error (don't fabricate success).

## 7. Update memory
Append the non-obvious decisions to `memory/import-notes.md` (dated): food normalizations, foods kept
separate, unit spellings folded, new units/conversions, new foods + category + fdc_id. Keep it short.

## Honesty guardrails
- Say how the recipe was obtained (scraper vs your own parse of the page/text).
- Nutrition values are looked-up estimates — flag them; never fabricate an `fdc_id`.
- Don't silently merge two foods or create shared rows without the review step (unless told to).
- If the source can't be parsed or the token is missing, say so and stop — don't invent a recipe.
