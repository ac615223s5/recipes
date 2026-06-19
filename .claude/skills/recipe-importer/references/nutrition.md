# Creating a new food (with nutrition & properties)

When an ingredient has no acceptable existing match, create the food well the first time — a bare
name with no category or nutrition is what makes the food list messy and breaks shopping/nutrition.

## 1. Decide the canonical name
- Singular, generic, brand-free store item (see `matching.md`). Set `plural_name`.
- Reuse an existing supermarket **category** so the item groups correctly on the shopping list
  (links to the grocery-planner skill). Fetch options with `tandoor.sh categories`; pick the best
  existing one. Only create a new category if none fits.

## 2. Look up nutrition (per 100 g, the Tandoor default basis)
- Source order: **USDA FoodData Central** (https://fdc.nal.usda.gov) is the canonical source —
  capture its numeric `fdc_id` and store it on the food (`fdc_id`) for provenance. If FDC is
  impractical, use a reputable nutrition reference via WebSearch.
- Collect the four core macros **per 100 g of the raw/as-sold food**:
  - Calories (kcal), Protein (g), Fat (g), Carbohydrates (g). Add Fiber/Sugar/Sodium if readily
    available and the space has those property types.
- These are **estimates** — they vary by variety/brand. Say so to the user; don't present them as exact.

## 3. Ensure the PropertyTypes exist
Nutrition values hang off `PropertyType` rows (Calories, Protein, ...). Fetch existing ones with
`tandoor.sh property-types`. If a needed type is missing, create it with the right unit:
```json
{"name":"Calories","unit":"kcal"}
{"name":"Protein","unit":"g"}
{"name":"Fat","unit":"g"}
{"name":"Carbohydrates","unit":"g"}
```
Match an existing type by name first (don't create "Calories" if "Energy" already plays that role —
ask if ambiguous). Reuse the same property types across all foods.

## 4. Create the food, THEN PATCH the properties (two steps — important)
`POST /api/food/` does **not** reliably attach `properties` inline: its create path requires each
`property_type` to carry a numeric **`id`** (a name-only property_type 500s), and if a food with that
name already exists it returns early and silently ignores properties. The robust sequence is:

**4a. Create the food** with name, plural, category, fdc_id, and the per-100 g basis (no properties):
```json
{
  "name": "shallot", "plural_name": "shallots",
  "supermarket_category": {"name": "Produce"},
  "fdc_id": "11677",
  "properties_food_amount": 100,
  "properties_food_unit": {"name": "g"}
}
```
Capture the returned food `id`.

**4b. PATCH the properties onto it** — the update path (writable-nested) handles them correctly:
`echo '{...}' | bash scripts/tandoor.sh patch /api/food/<id>/` with
```json
{"properties": [
  {"property_type": {"id": 1, "name": "Calories"},      "property_amount": 82},
  {"property_type": {"id": 2, "name": "Proteins"},      "property_amount": 17.9},
  {"property_type": {"id": 3, "name": "Fats"},          "property_amount": 0.7},
  {"property_type": {"id": 4, "name": "Carbohydrates"}, "property_amount": 0}
]}
```
- Pass `property_type` with the **id from step 3** (and the name) — get the ids from
  `tandoor.sh property-types`. The default space uses names **Calories / Proteins / Fats /
  Carbohydrates** (note the plurals) — match the existing names, don't create near-duplicates.
- `properties_food_amount` + `properties_food_unit` declare "these numbers are per 100 g" — always set
  both on create (4a), or the values are meaningless. Use a unit that exists (usually `g`).

## 5. Other useful food fields (set when known)
- `description` — short note (e.g. "small mild onion").
- `url` — a reference/source link for the food.
- `verification_interval_days` — leave default unless the user tracks this food's pantry freshness.
- Leave hierarchy (`parent`) alone unless the user organizes foods into a tree.

## Honesty
- Nutrition is looked up and may be approximate; cite FDC id where used and flag estimates.
- Don't fabricate an `fdc_id`. Omit it rather than guess.
