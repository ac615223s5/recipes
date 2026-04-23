<template>
    <v-card>
        <v-card-title>
            <v-icon icon="fa-solid fa-arrows-to-dot" class="mr-2"></v-icon>
            {{ $t('MergeFoods') }}
        </v-card-title>
        <v-card-subtitle>
            {{ $t('MergeFoodsDescription') }}
        </v-card-subtitle>
        <v-card-text>
            <v-row>
                <v-col cols="12" md="6">
                    <model-select
                        :model="'Food'"
                        v-model="sources"
                        mode="tags"
                        :label="$t('SourceFoods')"
                        :hint="$t('SourceFoodsHint')"
                        persistent-hint
                        allow-create
                    ></model-select>
                </v-col>
                <v-col cols="12" md="6">
                    <model-select
                        :model="'Food'"
                        v-model="target"
                        mode="single"
                        :label="$t('TargetFood')"
                        :hint="$t('TargetFoodHint')"
                        persistent-hint
                        allow-create
                    ></model-select>
                </v-col>
            </v-row>

            <v-checkbox
                :label="$t('Automate')"
                v-model="automate"
                :hint="$t('MergeAutomateHelp')"
                persistent-hint
            ></v-checkbox>
        </v-card-text>
        <v-card-actions>
            <v-btn
                color="warning"
                @click="mergeFoods()"
                :loading="loading"
                :disabled="!target || sources.length === 0"
            >
                {{ $t('Merge') }}
            </v-btn>

            <v-btn
                color="primary"
                variant="outlined"
                @click="fetchDuplicates"
                :loading="fetchingLoading"
                v-if="useUserPreferenceStore().activeSpace.aiEnabled"
            >
                {{ $t('FoodDeduplicate') }}
            </v-btn>
        </v-card-actions>
    </v-card>

    <!-- AI Duplicate Groups Section -->
    <v-card class="mt-4" v-if="groups.length > 0">
        <v-card-title>
            <v-icon icon="fa-solid fa-clone" class="mr-2"></v-icon>
            {{ $t('DuplicateGroups') }}
        </v-card-title>
        <v-card-text>
            <v-select
                v-model="selectedGroupIndex"
                :items="groupItems"
                :label="$t('SelectGroup')"
                :hint="$t('SelectGroupHint')"
                persistent-hint
                item-title="title"
                item-value="index"
                @update:model-value="selectGroup"
            ></v-select>

            <v-list class="mt-4">
                <v-list-subheader>{{ $t('AllGroups') }}</v-list-subheader>
                <v-list-item v-for="(group, idx) in groups" :key="idx" border>
                    <template #prepend>
                        <v-chip size="small" color="info">{{ group.length }}</v-chip>
                    </template>
                    <v-list-item-title>{{ group.join(', ') }}</v-list-item-title>
                    <template #append>
                        <v-btn size="small" variant="text" @click="selectedGroupIndex = idx; selectGroup(idx)">
                            {{ $t('Select') }}
                        </v-btn>
                    </template>
                </v-list-item>
            </v-list>
        </v-card-text>
    </v-card>
</template>

<script setup lang="ts">
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {computed, ref} from "vue";
import {ErrorMessageType, MessageType, useMessageStore} from "@/stores/MessageStore";
import {useI18n} from "vue-i18n";
import {ApiApi, Automation, Food} from "@/openapi";
import {getGenericModelFromString} from "@/types/Models";
import {getCookie} from "@/utils/cookie";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";

const emit = defineEmits(['change'])

const {t} = useI18n()

const loading = ref(false)
const fetchingLoading = ref(false)
const automate = ref(false)
const sources = ref<Food[]>([])
const target = ref<Food | null>(null)
const groups = ref<string[][]>([])
const selectedGroupIndex = ref<number | null>(null)
const allFoods = ref<Food[]>([])

const foodModel = getGenericModelFromString('Food', t)

const groupItems = computed(() => {
    return groups.value.map((group, idx) => ({
        title: group.join(', '),
        index: idx
    }))
})

/**
 * Fetch all foods from the API, handling pagination
 */
function fetchAllFoods(api: ApiApi): Promise<Food[]> {
    const allFoods: Food[] = []
    const fetchPage = (page: number = 1): Promise<Food[]> => {
        return api.apiFoodList({page, pageSize: 200}).then(r => {
            allFoods.push(...r.results)
            if (r.results.length === 200) {
                return fetchPage(page + 1)
            }
            return allFoods
        })
    }
    return fetchPage()
}

/**
 * Fetch AI-identified duplicate food groups
 */
function fetchDuplicates() {
    fetchingLoading.value = true
    groups.value = []
    selectedGroupIndex.value = null
    allFoods.value = []

    let api = new ApiApi()
    api.apiAiProviderList().then(providerResponse => {
        const defaultProvider = providerResponse.results.find((p: any) => p.id === useUserPreferenceStore().activeSpace.aiDefaultProvider?.id)

        if (!defaultProvider) {
            useMessageStore().addError(ErrorMessageType.CREATE_ERROR, "No AI Provider selected")
            fetchingLoading.value = false
            return
        }

        fetchAllFoods(api).then(fetchedFoods => {
            allFoods.value = fetchedFoods
            const foodNames = fetchedFoods.map((f: Food) => f.name)

            fetch(`/api/ai-food-deduplicate/?provider=${defaultProvider.id!}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ foods: foodNames }),
            }).then(response => response.json()).then(result => {
                groups.value = result
                fetchingLoading.value = false
                if (result.length > 0) {
                    useMessageStore().addMessage(MessageType.INFO, t('FoodDeduplicateFound', {count: result.length}))
                } else {
                    useMessageStore().addMessage(MessageType.INFO, t('FoodDeduplicateNoGroups'))
                }
            }).catch(err => {
                console.error('Error during food deduplication:', err)
                useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
                fetchingLoading.value = false
            })
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
            fetchingLoading.value = false
        })
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        fetchingLoading.value = false
    })
}

/**
 * Select a group and populate sources and target
 */
function selectGroup(index: number) {
    const group = groups.value[index]
    if (!group || group.length === 0) return

    sources.value = []
    target.value = null

    group.forEach((name, idx) => {
        const matchedFood = allFoods.value.find(f => f.name === name)
        if (matchedFood) {
            if (idx === 0) {
                target.value = matchedFood
            } else {
                sources.value.push(matchedFood)
            }
        }
    })
}

/**
 * Merge all source foods into the target food
 */
function mergeFoods() {
    if (target.value == null || sources.value.length === 0) {
        return
    }

    let api = new ApiApi()
    let promises: Promise<any>[] = []
    let mergePromises: Promise<any>[] = []

    loading.value = true

    sources.value.forEach(sourceFood => {
        mergePromises.push(foodModel.merge(sourceFood, target.value).then(() => {
            if (automate.value && target.value != null) {
                let automation = {
                    name: `${t('Merge')} ${sourceFood.name} -> ${target.value!.name}`.substring(0, 128),
                    param1: sourceFood.name,
                    param2: target.value.name,
                    type: 'FOOD_ALIAS'
                } as Automation
                promises.push(api.apiAutomationCreate({automation: automation}).catch(err => {
                    useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
                }))
            }
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        }))
    })

    Promise.allSettled(mergePromises).then(() => {
        Promise.allSettled(promises).then(() => {
            loading.value = false
            sources.value = []
            target.value = null
            automate.value = false
            groups.value = []
            selectedGroupIndex.value = null
            emit('change')
        })
    })
}
</script>

<style scoped>

</style>
