import { ApiApi, InventoryEntry, InventoryLocation, PatchedInventoryEntry, ShoppingListEntry } from "@/openapi"
import { ErrorMessageType, MessageType, useMessageStore } from "@/stores/MessageStore"
import { useI18n } from "vue-i18n"

// cache the inventory locations across all callers so checking off a long shopping list does not refetch per item
let locationsPromise: Promise<InventoryLocation[]> | null = null

function getLocations(): Promise<InventoryLocation[]> {
  if (!locationsPromise) {
    const api = new ApiApi()
    locationsPromise = api
      .apiInventoryLocationList({ pageSize: 100 })
      .then((r) => r.results)
      .catch(() => {
        // allow a later retry if the request failed
        locationsPromise = null
        return [] as InventoryLocation[]
      })
  }
  return locationsPromise
}

interface FoodGroup {
  food: ShoppingListEntry["food"]
  unit: ShoppingListEntry["unit"]
  foodId: number
  unitId: number | null
  amount: number
}

/**
 * group shopping entries by food + unit, summing their amounts
 */
function groupByFoodUnit(entries: ShoppingListEntry[]): FoodGroup[] {
  const groups = new Map<string, FoodGroup>()
  entries.forEach((e) => {
    if (e.food?.id == null) {
      return
    }
    const unitId = e.unit?.id ?? null
    const key = `${e.food.id}_${unitId ?? "none"}`
    const existing = groups.get(key)
    if (existing) {
      existing.amount += e.amount || 0
    } else {
      groups.set(key, { food: e.food, unit: e.unit, foodId: e.food.id, unitId, amount: e.amount || 0 })
    }
  })
  return [...groups.values()]
}

/**
 * find the single pantry entry that holds the running balance for a food + unit (including empty ones, so a
 * balance that was decremented to zero is reused instead of leaving cruft behind)
 */
async function findEntry(api: ApiApi, foodId: number, unitId: number | null): Promise<InventoryEntry | undefined> {
  const list = await api.apiInventoryEntryList({ foodId, empty: true, pageSize: 100 }).catch(() => null)
  return (list?.results ?? []).find((en) => (en.unit?.id ?? null) === unitId)
}

/**
 * helper for keeping the pantry (inventory) in sync as shopping items are checked off / un-checked.
 * treats the pantry as a running balance per food+unit: checking adds the amount, un-checking subtracts it,
 * so no client-side bookkeeping is needed and it stays correct across reloads.
 */
export function usePantryStock() {
  const { t } = useI18n()

  /**
   * add the given shopping entries' amounts to the pantry (used when an item is checked off).
   * returns true if anything was stocked, false otherwise (e.g. no pantry location exists for a brand new food).
   */
  async function addEntriesToPantry(entries: ShoppingListEntry[]): Promise<boolean> {
    // only stock items actually being bought now (have a food and are not already checked off)
    const groups = groupByFoodUnit(entries.filter((e) => e.food?.id != null && !e.checked))
    if (!groups.length) {
      return false
    }

    const api = new ApiApi()
    let location: InventoryLocation | undefined
    let stocked = false

    for (const g of groups) {
      const delta = g.amount > 0 ? g.amount : 1
      const match = await findEntry(api, g.foodId, g.unitId)
      if (match) {
        await api
          .apiInventoryEntryPartialUpdate({ id: match.id!, patchedInventoryEntry: { amount: (match.amount || 0) + delta } as PatchedInventoryEntry })
          .then(() => (stocked = true))
          .catch((err) => useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err))
      } else {
        if (location === undefined) {
          location = (await getLocations())[0]
        }
        if (!location) {
          useMessageStore().addMessage(MessageType.WARNING, { title: t("NoInventoryLocation"), text: t("NoInventoryLocationHelp") }, 6000)
          return stocked
        }
        await api
          .apiInventoryEntryCreate({ inventoryEntry: { food: g.food, unit: g.unit, amount: delta, inventoryLocation: location } as unknown as InventoryEntry })
          .then(() => (stocked = true))
          .catch((err) => useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err))
      }
    }
    return stocked
  }

  /**
   * subtract the given shopping entries' amounts from the pantry again (used when an item is un-checked).
   * the balance is clamped at zero and never goes negative; nothing happens if the food is not in the pantry.
   */
  async function removeEntriesFromPantry(entries: ShoppingListEntry[]): Promise<void> {
    const groups = groupByFoodUnit(entries.filter((e) => e.food?.id != null))
    if (!groups.length) {
      return
    }

    const api = new ApiApi()
    for (const g of groups) {
      if (g.amount <= 0) {
        continue
      }
      const match = await findEntry(api, g.foodId, g.unitId)
      if (match) {
        const newAmount = Math.max(0, (match.amount || 0) - g.amount)
        await api
          .apiInventoryEntryPartialUpdate({ id: match.id!, patchedInventoryEntry: { amount: newAmount } as PatchedInventoryEntry })
          .catch((err) => useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err))
      }
    }
  }

  return { addEntriesToPantry, removeEntriesFromPantry }
}
