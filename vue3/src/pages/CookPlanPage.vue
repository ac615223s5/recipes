<template>
  <v-container>
    <v-row dense>
      <v-col>
        <v-card prepend-icon="fa-solid fa-utensils" :title="$t('CookPlan')">
          <template #subtitle>
            <div class="text-wrap">{{ $t("CookPlanHelp") }}</div>
          </template>
        </v-card>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12" md="6">
        <v-card :title="$t('PlannedRecipes')">
          <v-card-text>
            <v-row dense align="center">
              <v-col>
                <model-select model="Recipe" v-model="recipeToAdd"></model-select>
              </v-col>
              <v-col cols="auto">
                <v-btn color="create" prepend-icon="$create" :disabled="!recipeToAdd" :loading="adding" @click="addRecipe">
                  {{ $t("AddRecipe") }}
                </v-btn>
              </v-col>
            </v-row>

            <v-list v-if="plans.length" lines="two">
              <v-list-item v-for="plan in plans" :key="plan.id" :to="plan.recipe ? { name: 'RecipeViewPage', params: { id: plan.recipe.id } } : undefined">
                <template #prepend>
                  <recipe-image v-if="plan.recipe" :recipe="plan.recipe" width="56" height="56" class="rounded me-2"></recipe-image>
                </template>
                <v-list-item-title>{{ plan.recipe?.name ?? plan.title }}</v-list-item-title>
                <template #append>
                  <v-btn v-if="plan.recipe" icon="fa-solid fa-circle-check" variant="text" color="success" :loading="completingId === plan.id" @click.prevent.stop="markComplete(plan)" :title="$t('MarkComplete')"></v-btn>
                  <v-btn icon="fa-solid fa-trash-can" variant="text" color="delete" :loading="removingId === plan.id" @click.prevent.stop="removeRecipe(plan)" :title="$t('Remove')"></v-btn>
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-medium-emphasis text-body-2 mt-4">{{ $t("NoPlannedRecipes") }}</div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card :title="$t('RecipeIngredients')">
          <v-card-text>
            <template v-if="recipeIds.length">
              <div class="text-overline text-medium-emphasis">{{ $t("InYourPantry") }}</div>
              <inventory-entry-table :key="`${recipeIds.join(',')}:${pantryRefresh}`" :recipes="recipeIds" cook-mode @changed="refreshIngredients"></inventory-entry-table>

              <template v-if="missingFoods.length">
                <v-divider class="my-4"></v-divider>
                <div class="d-flex align-center justify-space-between">
                  <div class="text-overline text-medium-emphasis">{{ $t("NotInPantry") }}</div>
                  <v-btn size="small" variant="text" color="primary" prepend-icon="fa-solid fa-cart-plus" :loading="addingAllShop" @click="addAllMissingToShopping">
                    {{ $t("AddAllToShopping") }}
                  </v-btn>
                </div>
                <v-chip-group column>
                  <v-chip v-for="f in missingFoods" :key="f.id" color="error" variant="tonal" size="small">
                    {{ f.name }}
                    <v-icon v-if="isOnShopping(f)" end icon="fa-solid fa-cart-shopping" class="ms-1 text-success" :title="$t('OnShoppingList')"></v-icon>
                    <v-icon
                      v-else
                      end
                      :icon="addingShopFoodId === f.id ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-cart-plus'"
                      class="ms-1"
                      :title="$t('AddToShopping')"
                      @click.stop="addFoodToShopping(f)"
                    ></v-icon>
                    <v-icon
                      end
                      :icon="addingFoodId === f.id ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-plus'"
                      class="ms-1"
                      :title="$t('AddToPantry')"
                      @click.stop="addToPantry(f)"
                    ></v-icon>
                  </v-chip>
                </v-chip-group>
              </template>
            </template>
            <div v-else class="text-medium-emphasis text-body-2">{{ $t("NoPlannedRecipes") }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ApiApi, CookLog, Food, InventoryEntry, InventoryLocation, MealPlan, RecipeOverview, ShoppingListEntry, ShoppingListEntryBulkCreate, ShoppingListRecipe, Unit } from "@/openapi"
import InventoryEntryTable from "@/components/display/InventoryEntryTable.vue"
import ModelSelect from "@/components/inputs/ModelSelect.vue"
import RecipeImage from "@/components/display/RecipeImage.vue"
import { ErrorMessageType, MessageType, PreparedMessage, useMessageStore } from "@/stores/MessageStore"
import { useShoppingStore } from "@/stores/ShoppingStore"
import { useUserPreferenceStore } from "@/stores/UserPreferenceStore"
import { useI18n } from "vue-i18n"

const { t } = useI18n()

// a planned recipe's foods scaled to the planned servings, used for shopping-list amounts/units and recipe grouping
interface PlannedIngredient {
  food: Food
  amount: number
  unit: Unit | null
  ingredientId: number | null
}
interface PlannedRecipe {
  recipeId: number
  servings: number
  ingredients: PlannedIngredient[]
}

const plans = ref<MealPlan[]>([])
const recipeToAdd = ref<RecipeOverview | undefined>(undefined)
const adding = ref(false)
const removingId = ref<number | null>(null)
const completingId = ref<number | null>(null)
const addingFoodId = ref<number | null>(null)
const addingShopFoodId = ref<number | null>(null)
const addingAllShop = ref(false)
// bumped to force the pantry table to re-fetch after the stock changes
const pantryRefresh = ref(0)

// foods used by the planned recipes, which of those are currently in the pantry, and the available pantry locations
const neededFoods = ref<Food[]>([])
const recipeData = ref<PlannedRecipe[]>([])
const inStockFoodIds = ref<Set<number>>(new Set())
// foods that already have an open (unchecked) entry on the shopping list, to avoid adding duplicates
const onShoppingFoodIds = ref<Set<number>>(new Set())
const inventoryLocations = ref<InventoryLocation[]>([])

// recipe ids backing the ingredient table; cook plan entries may have no recipe (free text), so filter those out
const recipeIds = computed(() => plans.value.map((p) => p.recipe?.id).filter((id): id is number => id != null))

// ingredients the recipes need that are not on hand in the pantry
const missingFoods = computed(() => neededFoods.value.filter((f) => f.id != null && !inStockFoodIds.value.has(f.id)))

onMounted(() => {
  loadPlans()
  loadLocations()
  // make sure the user's selected shopping lists are available for new entries
  useShoppingStore().loadShoppingLists()
  loadShoppingFoods()
})

// recompute the needed-vs-stocked ingredient breakdown whenever the set of planned recipes changes
watch(
  () => recipeIds.value.join(","),
  () => refreshIngredients(),
)

/**
 * load the undated meal plans that make up the cook plan
 */
function loadPlans() {
  const api = new ApiApi()
  api
    .apiMealPlanList({ undated: true })
    .then((r) => {
      plans.value = r.results
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
}

/**
 * work out which foods the planned recipes need and which of those are currently stocked in the pantry,
 * so ingredients that are missing (not in the pantry) can be surfaced as well
 */
async function refreshIngredients() {
  const ids = recipeIds.value
  if (!ids.length) {
    neededFoods.value = []
    recipeData.value = []
    inStockFoodIds.value = new Set()
    return
  }
  const api = new ApiApi()

  // collect the foods used across all planned recipes (recipe -> steps -> ingredients -> food),
  // keeping per-recipe amounts/units (scaled to the planned servings) for the shopping list
  const recipes = await Promise.all(ids.map((id) => api.apiRecipeRetrieve({ id }).catch(() => null)))
  const foodMap = new Map<number, Food>()
  const planned: PlannedRecipe[] = []
  recipes.forEach((r, idx) => {
    if (!r) {
      return
    }
    const recipeId = ids[idx]!
    const plan = plans.value.find((p) => p.recipe?.id === recipeId)
    const planServings = plan?.servings || r.servings || 1
    const factor = planServings / (r.servings || 1)
    const ingredients: PlannedIngredient[] = []
    r.steps?.forEach((s) => {
      s.ingredients?.forEach((ing) => {
        if (ing.food?.id != null && !ing.isHeader) {
          foodMap.set(ing.food.id, ing.food)
          ingredients.push({ food: ing.food, amount: (ing.amount ?? 0) * factor, unit: ing.unit ?? null, ingredientId: ing.id ?? null })
        }
      })
    })
    planned.push({ recipeId, servings: planServings, ingredients })
  })
  neededFoods.value = [...foodMap.values()].sort((a, b) => a.name.localeCompare(b.name))
  recipeData.value = planned

  // which of those foods are actually on hand (the recipes filter only returns entries with amount > 0)
  const inventory = await api.apiInventoryEntryList({ recipes: ids.join(","), pageSize: 200 }).catch(() => null)
  inStockFoodIds.value = new Set((inventory?.results ?? []).map((e) => e.food?.id).filter((id): id is number => id != null))
}

/**
 * load the available pantry locations so a missing ingredient can be added to one
 */
function loadLocations() {
  const api = new ApiApi()
  api
    .apiInventoryLocationList({ pageSize: 100 })
    .then((r) => {
      inventoryLocations.value = r.results
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
}

/**
 * add a missing ingredient to the pantry as a new inventory entry (amount 1, first available location)
 */
function addToPantry(food: Food) {
  const location = inventoryLocations.value[0]
  if (!location) {
    useMessageStore().addMessage(MessageType.WARNING, { title: t("NoInventoryLocation"), text: t("NoInventoryLocationHelp") }, 6000)
    return
  }
  const api = new ApiApi()
  addingFoodId.value = food.id!
  api
    .apiInventoryEntryCreate({ inventoryEntry: { food, inventoryLocation: location, amount: 1 } as unknown as InventoryEntry })
    .then(() => {
      useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
      pantryRefresh.value++
      refreshIngredients()
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    })
    .finally(() => {
      addingFoodId.value = null
    })
}

/**
 * load the foods that already have an open entry on the shopping list, so we don't add them again
 */
function loadShoppingFoods() {
  const api = new ApiApi()
  api
    .apiShoppingListEntryList({ pageSize: 1000 })
    .then((r) => {
      onShoppingFoodIds.value = new Set(
        (r.results ?? [])
          .filter((e) => !e.checked)
          .map((e) => e.food?.id)
          .filter((id): id is number => id != null),
      )
    })
    .catch(() => {})
}

/**
 * whether a food already has an open entry on the shopping list
 */
function isOnShopping(food: Food): boolean {
  return food.id != null && onShoppingFoodIds.value.has(food.id)
}

/**
 * find the first planned-recipe occurrence of a food, to reuse its (scaled) amount and unit
 */
function plannedIngredientFor(food: Food): PlannedIngredient | null {
  for (const r of recipeData.value) {
    const ing = r.ingredients.find((i) => i.food.id === food.id)
    if (ing) {
      return ing
    }
  }
  return null
}

/**
 * the shopping lists the user currently has selected (new entries are added to these)
 */
function selectedShoppingLists() {
  const selected = useUserPreferenceStore().deviceSettings.shopping_selected_shopping_lists
  return useShoppingStore().shoppingLists.filter((sl) => sl.id != null && selected.includes(sl.id))
}

/**
 * add a single missing ingredient to the shopping list (with its recipe amount/unit) via the shopping store
 */
function addFoodToShopping(food: Food) {
  if (isOnShopping(food)) {
    return
  }
  const ing = plannedIngredientFor(food)
  addingShopFoodId.value = food.id!
  const entry = {
    amount: ing ? ing.amount : 1,
    unit: ing?.unit ?? null,
    food,
    shoppingLists: selectedShoppingLists(),
  } as unknown as ShoppingListEntry
  useShoppingStore()
    .createObject(entry, true)
    .then((r) => {
      if (r) {
        onShoppingFoodIds.value = new Set(onShoppingFoodIds.value).add(food.id!)
        useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
      }
    })
    .finally(() => {
      addingShopFoodId.value = null
    })
}

/**
 * add every missing ingredient to the shopping list, grouped under its recipe so amounts/units and provenance are kept
 */
async function addAllMissingToShopping() {
  const api = new ApiApi()
  addingAllShop.value = true
  const shoppingListsIds = selectedShoppingLists().map((sl) => sl.id!)
  const added = new Set<number>()
  try {
    for (const r of recipeData.value) {
      // only add foods that are missing from the pantry AND not already on the shopping list
      const missing = r.ingredients.filter((i) => i.food.id != null && !inStockFoodIds.value.has(i.food.id!) && !onShoppingFoodIds.value.has(i.food.id!))
      if (!missing.length) {
        continue
      }
      const slr = await api.apiShoppingListRecipeCreate({ shoppingListRecipe: { recipe: r.recipeId, servings: r.servings } as unknown as ShoppingListRecipe })
      await api.apiShoppingListRecipeBulkCreateEntriesCreate({
        id: slr.id!,
        shoppingListEntryBulkCreate: {
          entries: missing.map((i) => ({ amount: i.amount, foodId: i.food.id!, unitId: i.unit?.id ?? null, ingredientId: i.ingredientId })),
          shoppingListsIds,
        } as unknown as ShoppingListEntryBulkCreate,
      })
      missing.forEach((i) => added.add(i.food.id!))
    }
    if (added.size) {
      const updated = new Set(onShoppingFoodIds.value)
      added.forEach((id) => updated.add(id))
      onShoppingFoodIds.value = updated
      useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
    } else {
      useMessageStore().addMessage(MessageType.INFO, { title: t("AlreadyOnShoppingList"), text: "" }, 4000)
    }
  } catch (err) {
    useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
  } finally {
    addingAllShop.value = false
  }
}

/**
 * add the selected recipe to the cook plan as an undated meal plan (no date, meal type defaulted by the backend)
 */
function addRecipe() {
  if (!recipeToAdd.value) {
    return
  }
  const api = new ApiApi()
  adding.value = true
  api
    .apiMealPlanCreate({ mealPlan: { recipe: recipeToAdd.value, servings: 1, title: "", shared: [] } as unknown as MealPlan })
    .then((r) => {
      plans.value.push(r)
      recipeToAdd.value = undefined
      useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    })
    .finally(() => {
      adding.value = false
    })
}

/**
 * mark a planned recipe as cooked: record it in the cook log, then remove it from the cook plan
 */
function markComplete(plan: MealPlan) {
  if (!plan.recipe?.id) {
    return
  }
  const api = new ApiApi()
  completingId.value = plan.id!
  api
    .apiCookLogCreate({ cookLog: { recipe: plan.recipe.id, servings: plan.servings ? Math.round(plan.servings) : undefined } as unknown as CookLog })
    .then(() => api.apiMealPlanDestroy({ id: plan.id! }))
    .then(() => {
      plans.value = plans.value.filter((p) => p.id !== plan.id)
      useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    })
    .finally(() => {
      completingId.value = null
    })
}

/**
 * remove a recipe from the cook plan
 */
function removeRecipe(plan: MealPlan) {
  const api = new ApiApi()
  removingId.value = plan.id!
  api
    .apiMealPlanDestroy({ id: plan.id! })
    .then(() => {
      plans.value = plans.value.filter((p) => p.id !== plan.id)
      useMessageStore().addPreparedMessage(PreparedMessage.DELETE_SUCCESS)
    })
    .catch((err) => {
      useMessageStore().addError(ErrorMessageType.DELETE_ERROR, err)
    })
    .finally(() => {
      removingId.value = null
    })
}
</script>

<style scoped></style>
