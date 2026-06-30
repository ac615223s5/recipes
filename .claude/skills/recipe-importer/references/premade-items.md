# Importing premade / packaged items as recipes

For things that aren't a cook-from-scratch recipe but you still want tracked in Tandoor: **packaged
products** (frozen meals, candies, snacks, drinks, instant noodles), **restaurant / takeout dishes**,
ready-to-eat deli items, etc. The point of these entries is the **nutrition + price on the recipe
itself** — there is usually no meaningful ingredient list to reconcile, so the normal food-matching
flow (`matching.md`, `nutrition.md`) mostly does not apply.

Use this page when the user says "add this premade/packaged item", "don't add ingredients", or the
source is a store product page / restaurant menu rather than a recipe.

## What's different from a normal import
- **No ingredient foods.** Don't create foods or attach an ingredient table. (If the user *does* want
  the packaged item itself to exist as a food too, that's a separate `create-food` — ask.)
- **Nutrition goes on the recipe as `properties`**, not derived from ingredients.
- **Steps are optional** — use them for heating/serving instructions if the package gives them
  ("air-fry 7 min", "microwave 2 min"), otherwise one short step or none.
- Still set the **metadata**: name (brand + size), description, `servings`, `servings_text`,
  `source_url`, image, and a fitting existing **keyword** (`meat`, `snack`, `candy`, `drink`, …).

## The servings ↔ properties convention (get this right — it's the easy thing to flip)
**Tandoor stores `property_amount` PER SERVING and shows the total as `amount × servings`** (it
multiplies, it does **not** divide). So:

> Store the **label's per-serving values**, and set `servings` = number of servings in the package.

Worked example — a 340 g frozen meal whose label reads "per ½ container (170 g)" ⇒ 2 servings/box:

| field | value |
|---|---|
| `servings` | `2` |
| `servings_text` | `"½ container (170 g)"` |
| each property `property_amount` | the **170 g label number** (e.g. Calories 300, mass 170, price 3.495) |

Result in the UI: per-serving = the label (300 kcal, 170 g, $3.50); total = ×2 = the whole box
(600 kcal, 340 g, $6.99). If you instead store the box totals, the UI shows double — that's the bug.
A single-serving package is just `servings: 1` with the label numbers as-is.

## Mapping the label to property types
Fetch `bash scripts/tandoor.sh property-types` and match each label row to an **existing** type by
name (default space, with their exact names/units):

| label row | property type | unit |
|---|---|---|
| Calories | `Calories` | kcal |
| Protein | `Proteins` | g |
| Fat (and Trans) | `Fats` (`trans fat`) | g |
| Carbohydrate (and Fibre) | `Carbohydrates` (`fibre`) | g |
| Sodium / Potassium / Calcium / Iron | `sodium` / `potassium` / `calcium` / `iron` | mg |
| net weight | `mass` | g |
| shelf price | `price` | CAD |

- **No type for cholesterol or sugars** in the default space — skip them, or create the PropertyType
  first (`create-property-type`) **only with the user's OK** (it's a shared row). Note what you skip.
- Unlike foods, **recipe properties DO stick when passed inline to `create-recipe`** — no follow-up
  PATCH needed. Shape: `{"property_amount": N, "property_type": {"id": <id>, "name": "<exact>"}}`.
- To fix amounts later, PATCH `/api/recipe/<id>/` with the properties array **including each row's
  existing `id`** so they update in place instead of duplicating (get ids from a GET first).

## Getting the data (the hard part for store pages)
Many grocer/restaurant sites are bot-walled and the nutrition lives in **package photos**, not text:
- `from-url` typically **400s** on a product page (it's not a recipe site). Don't fight it.
- The product page's DOM often has **no nutrition / ingredient text at all** — only on the box images.
- Plain `curl` / WebFetch **and** Tandoor's server-side `image_url` fetch are commonly **blocked
  (403 / 500)**. (e.g. tntsupermarket.com.)

**Read a nutrition label out of a package image with the Playwright MCP browser** (set up via the
`tandoor-setup` skill; full headed Chromium passes the bot-walls). Navigate to the image, crop+zoom the
Nutrition Facts panel onto a canvas, screenshot it, and Read the screenshot:
```js
// in browser_evaluate, after navigating to the image URL
() => {
  const img = document.querySelector('img'), W = img.naturalWidth, H = img.naturalHeight;
  // tune the fractions to frame just the Nutrition Facts box
  const sx=W*0.30, sy=H*0.12, sw=W*0.33, sh=H*0.22;
  const c = document.createElement('canvas'); c.width=1200; c.height=Math.round(1200*sh/sw);
  const x = c.getContext('2d'); x.imageSmoothingQuality='high';
  x.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
  c.style.cssText='position:fixed;left:0;top:0;z-index:99999;background:#fff';
  document.body.innerHTML=''; document.body.appendChild(c); return [c.width,c.height];
}
```
then `browser_take_screenshot {fullPage:true}` and Read the PNG. Re-crop top/bottom halves if the
table is too small to read in one shot. **Playwright MCP saves screenshots to the project cwd, not
the configured `outputDir` — delete the PNGs when done.**

If there's no package (restaurant dish, deli item), **look up** the nutrition (USDA / brand site) and
**flag it as an estimate** — these are not label-exact. Or ask the user for the figures.

### Attaching the product image when server-side fetch is blocked
`PUT image_url=<url>` 500s if Tandoor can't fetch the image. Instead pull the bytes through the
browser and upload the file:
1. In `browser_evaluate` (same-origin with the image): `fetch(url)` → `arrayBuffer` → base64; return it
   (use the `filename` arg to dump large results to a file).
2. `jq -r '.b64' file | base64 -d > /tmp/front.jpg`.
3. `curl -X PUT -H "Authorization: Bearer $TANDOOR_TOKEN" -F "image=@$(cygpath -w /tmp/front.jpg);type=image/jpeg" "$TANDOOR_URL/api/recipe/<id>/image/"`
   — **use a Windows path via `cygpath -w`**; `-F image=@/tmp/..` (msys path) gives HTTP 000.

## Review gate & honesty
- Still confirm before writing (duplicate check + the plan), unless the user said to just import.
- **Package-label numbers are the product's own stated values — not estimates.** Say so. Numbers you
  *looked up* for a restaurant/unpackaged dish ARE estimates — flag those explicitly.
- Record the import in `memory/import-notes.md` under "Premade-meal / no-ingredient imports".
