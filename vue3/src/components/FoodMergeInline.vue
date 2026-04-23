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
        </v-card-actions>
    </v-card>
</template>

<script setup lang="ts">
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {ref} from "vue";
import {ErrorMessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore";
import {useI18n} from "vue-i18n";
import {ApiApi, Automation, Food} from "@/openapi";
import {getGenericModelFromString} from "@/types/Models";

const emit = defineEmits(['change'])

const {t} = useI18n()

const loading = ref(false)
const automate = ref(false)
const sources = ref<Food[]>([])
const target = ref<Food | null>(null)

const foodModel = getGenericModelFromString('Food', t)

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

    // Merge each source food into the target
    sources.value.forEach(sourceFood => {
        mergePromises.push(foodModel.merge(sourceFood, target.value).then(() => {
            if (automate.value && target.value != null) {
                // Create automation rule for future merges
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
            emit('change')
        })
    })
}
</script>

<style scoped>

</style>
