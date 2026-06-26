<template>
    <v-data-table-server
        return-object
        @update:options="loadItems"
        :items="items"
        :items-length="itemCount"
        :loading="tableLoading"
        :headers="tableHeaders"
        :page="page"
        :items-per-page="pageSize"
        disable-sort
    >
        <template #item.code="{item}">
            <v-chip size="small" label color="warning" class="me-2" prepend-icon="fa-solid fa-barcode">{{ item.code }}</v-chip>
        </template>
        <template #item.food="{item}">
            {{ ingredientToString({food: item.food, unit: item.unit, amount: item.amount} as Ingredient) }}
        </template>
        <template #item.expires="{item}">
            <template v-if="item.expires ">
                <v-chip size="small" label :color="(item.expires < DateTime.now() ? 'error' : 'success')">
                    {{ DateTime.fromJSDate(item.expires).toFormat('yyyy-MM-dd') }}
                </v-chip>
            </template>
        </template>
        <template #item.inventoryLocation="{ item }">
            {{ item.inventoryLocation.name }} <i class="fa-solid fa-snowflake" v-if="item.inventoryLocation.isFreezer"></i>
            <span class="text-body-2 text-disabled">
                                    <br/>
                                {{ item.subLocation }}
                                </span>
        </template>
        <template #item.lastVerifiedAt="{item}">
            <v-chip size="small" label :color="item.isStale ? 'error' : 'success'"
                    :prepend-icon="item.isStale ? 'fa-solid fa-triangle-exclamation' : 'fa-solid fa-check'">
                <template v-if="item.lastVerifiedAt">{{ DateTime.fromJSDate(item.lastVerifiedAt).toRelative() }}</template>
                <template v-else>{{ $t('Never') }}</template>
            </v-chip>
        </template>
        <template #item.action="{item}">
            <v-btn-group divided border density="comfortable">
                <v-btn icon="fa-solid fa-clipboard-check" :color="item.isStale ? 'warning' : undefined" :loading="verifyingId === item.id"
                       @click="verifyEntry(item)" :title="$t('Verify')"></v-btn>
                <v-btn v-if="!cookMode" icon="fa-solid fa-clock-rotate-left" @click="entryLogDialog = true; entryLogEntry = item"></v-btn>
                <v-btn v-if="cookMode" icon="fa-solid fa-xmark" color="delete" :loading="removingId === item.id"
                       @click="markNotInPantry(item)" :title="$t('MarkNotInPantry')"></v-btn>
                <v-btn v-else icon="fa-solid fa-minus" :to="{name: 'InventoryBookingPage', query: {inventoryEntryId: item.id, bookingMode: 'remove'}}"></v-btn>
                <v-btn v-if="!cookMode" icon="fa-solid fa-arrow-right" :to="{name: 'InventoryBookingPage', query: {inventoryEntryId: item.id, bookingMode: 'move'}}"></v-btn>
            </v-btn-group>

        </template>
    </v-data-table-server>

    <inventory-entry-log-dialog v-model="entryLogDialog" :inventory-entry="entryLogEntry"></inventory-entry-log-dialog>
</template>

<script setup lang="ts">

import {DateTime} from "luxon";
import {ingredientToString} from "@/utils/model_utils.ts";
import {ApiApi, ApiInventoryEntryListRequest, Ingredient, InventoryEntry, InventoryLocation} from "@/openapi";
import {computed, PropType, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import InventoryEntryLogDialog from "@/components/dialogs/InventoryEntryLogDialog.vue";
import {VDataTableUpdateOptions} from "@/vuetify.ts";
import {ErrorMessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore.ts";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";

const {t} = useI18n()

const props = defineProps({
    food: {type: Object as PropType<Ingredient | null>, required: false},
    inventoryLocation: {type: Object as PropType<InventoryLocation | null>, required: false},
    stale: {type: Boolean, default: false},
    recipes: {type: Array as PropType<number[]>, default: () => []},
    // cook plan mode: hide the barcode/history/move controls and turn remove into a one-click "mark not in pantry"
    cookMode: {type: Boolean, default: false},
})

const emit = defineEmits(['changed'])

const verifyingId = ref<number | null>(null)
const removingId = ref<number | null>(null)

watch(props, () => {
    loadItems({page: 1, itemsPerPage: useUserPreferenceStore().deviceSettings.general_tableItemsPerPage})
})

// table
const tableLoading = ref(false)

const items = ref([] as InventoryEntry[])
const itemCount = ref(0)
const page = ref(1)
const pageSize = ref(useUserPreferenceStore().deviceSettings.general_tableItemsPerPage)

const entryLogDialog = ref(false)
const entryLogEntry = ref<InventoryEntry | null>(null)

const tableHeaders = computed(() => {
    const headers = [
        {title: t('Code'), key: 'code'},
        {title: t('Food'), key: 'food'},
        {title: t('Expires'), key: 'expires',},
        {title: t('InventoryLocation'), key: 'inventoryLocation',},
        {title: t('LastVerified'), key: 'lastVerifiedAt',},
        {title: 'Actions', key: 'action', align: 'end'},
    ]
    // hide the barcode column in cook plan mode
    return props.cookMode ? headers.filter(h => h.key !== 'code') : headers
})

/**
 * load inventory data based on current props
 */
function loadItems(options: VDataTableUpdateOptions) {
    let api = new ApiApi()

    let parameters = {} as ApiInventoryEntryListRequest

    if (props.food) {
        parameters.foodId = props.food.id!
    }
    if (props.inventoryLocation) {
        parameters.inventoryLocationId = props.inventoryLocation.id!
    }
    if (props.stale) {
        parameters.stale = true
    }
    if (props.recipes && props.recipes.length) {
        parameters.recipes = props.recipes.join(',')
    }

    tableLoading.value = true

    page.value = options.page
    pageSize.value = options.itemsPerPage
    // persist the chosen page size so it survives reloads (shared general tables preference)
    useUserPreferenceStore().deviceSettings.general_tableItemsPerPage = options.itemsPerPage

    parameters.page = options.page
    parameters.pageSize = options.itemsPerPage

    api.apiInventoryEntryList(parameters).then((r: any) => {
        items.value = r.results
        itemCount.value = r.count
    }).catch((err: any) => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        tableLoading.value = false
    })

}

/**
 * mark an entry as verified (still exists) without changing its amount or location
 */
function verifyEntry(item: InventoryEntry) {
    const api = new ApiApi()
    verifyingId.value = item.id!
    api.apiInventoryEntryVerifyCreate({id: item.id!}).then((r: InventoryEntry) => {
        const idx = items.value.findIndex(i => i.id === r.id)
        if (idx !== -1) {
            items.value[idx] = r
        }
        useMessageStore().addPreparedMessage(PreparedMessage.UPDATE_SUCCESS)
    }).catch((err: any) => {
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
    }).finally(() => {
        verifyingId.value = null
    })
}

/**
 * mark an entry as no longer in the pantry by setting its amount to 0 (keeps the entry/history, drops it from stock)
 */
function markNotInPantry(item: InventoryEntry) {
    const api = new ApiApi()
    removingId.value = item.id!
    api.apiInventoryEntryUpdate({id: item.id!, inventoryEntry: {...item, amount: 0} as InventoryEntry}).then(() => {
        items.value = items.value.filter(i => i.id !== item.id)
        itemCount.value = Math.max(0, itemCount.value - 1)
        useMessageStore().addPreparedMessage(PreparedMessage.UPDATE_SUCCESS)
        emit('changed')
    }).catch((err: any) => {
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
    }).finally(() => {
        removingId.value = null
    })
}
</script>


<style scoped>

</style>