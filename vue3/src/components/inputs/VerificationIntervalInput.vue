<template>
  <div>
    <div class="text-body-2 mb-1">{{ label ?? $t("VerificationInterval") }}</div>
    <v-slider
      v-model="sliderIndex"
      :min="0"
      :max="stops.length - 1"
      :step="1"
      :ticks="tickLabels"
      show-ticks="always"
      tick-size="4"
      hide-details
      thumb-label="always"
      class="mt-8 px-2"
    >
      <template #thumb-label="{ modelValue }">
        {{ stops[modelValue]?.label }}
      </template>
    </v-slider>
    <div class="text-caption text-medium-emphasis mt-1">{{ hintText }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"

const { t } = useI18n()

const props = defineProps<{
  // verification interval in days. 0 means "never goes stale", null/undefined means "use the space default" (when allowInherit).
  modelValue: number | null | undefined
  label?: string
  // when true, an additional "Default" stop is shown that maps to null (inherit the space default)
  allowInherit?: boolean
  // space default in days, shown in the "Default" stop hint
  defaultDays?: number | null
}>()

const emit = defineEmits<{ (e: "update:modelValue", value: number | null): void }>()

// roughly exponential ramp of day presets
const DAY_PRESETS = [1, 3, 7, 14, 30, 60, 90, 180, 365]

/**
 * format a day count into a compact human-readable label (1d / 1w / 1mo / 1y)
 */
function humanizeDays(days: number): string {
  if (days % 365 === 0) return `${days / 365}y`
  if (days % 30 === 0) return `${days / 30}mo`
  if (days % 7 === 0) return `${days / 7}w`
  return `${days}d`
}

// ordered list of selectable stops; `value === null` represents inherit-the-default
const stops = computed<{ value: number | null; label: string }[]>(() => {
  const list: { value: number | null; label: string }[] = []
  if (props.allowInherit) {
    list.push({ value: null, label: t("Default") })
  }
  DAY_PRESETS.forEach((d) => list.push({ value: d, label: humanizeDays(d) }))
  // "Never" represents an infinite interval, so it sits at the high end of the scale
  list.push({ value: 0, label: t("Never") })
  return list
})

const tickLabels = computed(() => Object.fromEntries(stops.value.map((s, i) => [i, s.label])))

const sliderIndex = computed({
  get() {
    // null/undefined maps to the inherit stop (when present) otherwise to "Never"
    if (props.modelValue == null) {
      return props.allowInherit ? 0 : stops.value.findIndex((s) => s.value === 0)
    }
    const exact = stops.value.findIndex((s) => s.value === props.modelValue)
    if (exact !== -1) return exact
    // snap a custom (api-set) value to the nearest preset for display
    let nearest = 0
    let bestDiff = Infinity
    stops.value.forEach((s, i) => {
      if (s.value == null) return
      const diff = Math.abs(s.value - (props.modelValue as number))
      if (diff < bestDiff) {
        bestDiff = diff
        nearest = i
      }
    })
    return nearest
  },
  set(index: number) {
    emit("update:modelValue", stops.value[index]?.value ?? null)
  },
})

const hintText = computed(() => {
  const value = stops.value[sliderIndex.value]?.value ?? null
  if (value === null) {
    const d = props.defaultDays
    if (d == null || d === 0) return t("VerificationNeverStaleHelp")
    return t("VerificationDefaultHelp", { interval: humanizeDays(d) })
  }
  if (value === 0) return t("VerificationNeverStaleHelp")
  return t("VerificationStaleAfterHelp", { interval: humanizeDays(value) })
})
</script>
