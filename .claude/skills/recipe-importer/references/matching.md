# Matching rules: keywords, foods, units

The import endpoint gives you a *parsed* recipe (names as written on the source page).
Your job is to reconcile those names with what already exists in the Tandoor database so
you don't create near-duplicates ("Garlic" vs "garlic" vs "garlic clove"). Read the live
DB lists first (`tandoor.sh keywords|foods|units|conversions|property-types`) and also
`memory/import-notes.md` for decisions made on past imports.

General rule for all three: **match case-insensitively, trimmed, singular/plural-folded.**
Never create a new row when an existing one is the same thing under a different surface form.

---

## Keywords (attach existing matches only)

- Fetch every keyword with its `description`. The description is the disambiguator — a keyword
  named "Mexican" with description "dishes from Mexican cuisine" should match a taco recipe.
- Attach a keyword when the recipe's cuisine / course / diet / method / season clearly fits the
  keyword's **name or its description**. Judge from the whole recipe (title, ingredients, steps),
  not just a literal word match.
- **Only attach keywords that already exist.** Do not invent new keywords. If the recipe obviously
  wants a keyword the space lacks (e.g. "Thai"), you may *list it as a suggestion* for the user,
  but do not create it unless they say so.
- Keywords are a tree; attach the specific child, not the parent, when both fit.

---

## Foods (rename to the existing "store item"; create if missing)

**The identity test: two names are the same food iff they are the same item you'd put in one
shopping-cart line at the store.** Prep state, cut, and form do NOT change the food.

- Same food → rename to the existing DB food, move the descriptor to the ingredient `note`:
  - "crushed garlic", "minced garlic", "garlic clove" → food **garlic** (note: "crushed" / "minced")
  - "finely chopped yellow onion" → food **onion** (note: "finely chopped"; "yellow" only if the DB
    distinguishes onion colors — usually it doesn't)
  - "boneless skinless chicken breast" → food **chicken breast** (note: "boneless, skinless")
  - "grated parmesan" → food **parmesan** (note: "grated")
  - "ripe roma tomatoes" → food **tomato** (note: "ripe, roma")
- Different store item → a DIFFERENT food, even if the words overlap. Do not collapse these:
  - "tomato sauce" ≠ tomato; "tomato paste" ≠ tomato; "sun-dried tomato" ≠ tomato
  - "garlic powder" ≠ garlic; "coconut milk" ≠ coconut; "almond flour" ≠ almond
  - "chicken broth" ≠ chicken; "vanilla extract" ≠ vanilla
  - Heuristic: if it sits in a different store aisle / is a different SKU, it's a different food.
- **Brands and grades drop out of the name**: "Kerrygold butter" → butter; "00 flour" → keep
  only if the DB cares about flour types, else **flour** (note: "00").
- Prefer the **singular, generic** name already in the DB. If the DB has "egg", use "egg" (amount 2),
  not "eggs".
- When a match is a genuine judgment call (e.g. "scallion" vs an existing "green onion", or whether
  "heavy cream" should map to an existing "cream"), **ask the user** rather than guessing — getting
  this wrong silently pollutes the shared food list and the shopping list grouping.
- For each food with no acceptable existing match, create it (see `nutrition.md` for the full
  new-food procedure — name, plural, supermarket category, nutrition).

---

## Units (match spelling variants; create new + add conversions)

- Match against existing units by name **and** `plural_name` **and** common spellings/abbreviations:
  - tbsp = tablespoon = tablespoons = T; tsp = teaspoon = t; g = gram = grams; ml = milliliter =
    millilitre; oz = ounce; lb = lbs = pound; c = cup; clove = cloves; can = cans; pinch; bunch; clove.
  - If an existing unit covers it under any spelling, reuse that unit — do not create a synonym row.
- If it's genuinely new, create the unit (set `plural_name`). Then add conversions **only when you're
  confident**:
  - **Global conversions** — safe, density-independent, pure measurement equivalences. Add these as
    global (no `food`): `1 tbsp = 3 tsp`, `1 tbsp = 15 ml`, `1 cup = 240 ml`, `1 oz = 28.35 g`,
    `1 lb = 453.6 g`, `1 stick butter`… (no — that's food-specific, see below).
  - **Food-specific conversions** — anything whose ratio depends on the ingredient. Attach a `food`:
    - count/volume↔weight: `1 clove garlic = 5 g`, `1 can (tomatoes) = 400 g`, `1 cup flour = 120 g`,
      `1 cup water = 240 g`, `1 stick butter = 113 g`, `1 bunch cilantro = 40 g`.
    - **Never** add a volume↔weight conversion as global — 1 cup of flour and 1 cup of honey weigh
      different amounts. If you can't make it food-specific safely, skip it and note why.
  - Conversion body shape (see `tandoor.sh create-conversion`):
    ```json
    {"base_amount":1,"base_unit":{"name":"clove"},
     "converted_amount":5,"converted_unit":{"name":"g"},
     "food":{"name":"garlic"}}            // omit "food" for a global conversion
    ```
  - Don't duplicate a conversion that already exists (check `tandoor.sh conversions [food_id]`).

---

## Amounts (while reconciling ingredients)

- Normalize fractions and ranges: `½`/`1/2` → 0.5; `1 ½` → 1.5; ranges like "2-3 cloves" → take the
  lower or the midpoint and put the range in the note ("2-3").
- "a pinch of", "to taste", "for garnish" → amount empty / `no_amount: true`, text in the note.
- Section headers in the ingredient list ("For the sauce:") → an ingredient row with `is_header: true`.
- Keep the source's exact wording in `original_text` so nothing is lost.

---

## Record what you decided

After an import, append non-obvious mappings to `memory/import-notes.md`:
the food normalizations you chose ("crushed garlic → garlic"), any unit spelling you folded,
category assignments for new foods, and conversions you added. Future imports read it first and
stay consistent (and faster).
