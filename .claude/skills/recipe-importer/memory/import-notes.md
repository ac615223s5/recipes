# Recipe-import memory

Long-term memory for the recipe-importer skill. Read this **before** reconciling an import so
choices stay consistent; append to it **after** an import. Keep entries short and dated (YYYY-MM-DD).

## Food normalizations (source name → DB food, + where descriptor went)
<!-- e.g. 2026-06-19 - "crushed garlic" / "minced garlic" / "garlic clove" → food **garlic**, prep → note -->
- 2026-06-19 - "green onion" → **Scallion** (#73); "oil" (neutral) → **Canola Oil** (#203);
  "egg" / "1 egg" → **Egg (Large)** (#25); "rice" → **Rice white long grain** (#90);
  "ginger" → **Ginger root** (#115). (sliced-fish-congee import)

## Foods kept SEPARATE (do not merge — different store items)
<!-- e.g. tomato / tomato sauce / tomato paste / sun-dried tomato are four different foods -->
- 2026-06-19 - "white pepper" is its own food, NOT black pepper (created **White Pepper**).

## Unit spellings folded into an existing unit
<!-- e.g. "T" / "Tbsp" / "tablespoon(s)" → unit **tbsp** -->
- (oz/lb/cup/tbsp/tsp all already existed and matched directly)

## New units created + conversions added
<!-- e.g. 2026-06-19 - created unit "clove"; food-specific: 1 clove garlic = 5 g -->
- 2026-06-19 - created unit **stalk** (#17); food-specific conversion **1 stalk Scallion = 15 g**.
  (Note: Tandoor normalizes a unit's `plural_name` to the singular on create, and PATCH /api/unit/<id>/
  500s with a KeyError — leave plural as-is, it's cosmetic.)

## New foods created (name → category, fdc_id, nutrition source)
<!-- e.g. 2026-06-19 - "shallot" → Produce, FDC 11677, USDA per-100g -->
- 2026-06-19 - **White Fish** → Fish and Seafood, FDC 171955 (USDA raw cod proxy): 82 kcal / 17.9 P / 0.7 F / 0 C per 100 g.
- 2026-06-19 - **White Pepper** → Herbs and Spices, FDC 170933 (USDA): 296 kcal / 10.4 P / 2.12 F / 68.61 C per 100 g.

## Category assignments (food → supermarket category)
<!-- helps future foods land in the right aisle / shopping group -->
- (none recorded yet)

## Keyword-matching notes
<!-- e.g. keyword "Weeknight" (desc: quick <30min) — attach when working_time <= 30 -->
- (none recorded yet)
