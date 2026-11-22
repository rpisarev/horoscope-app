<template>
  <div class="flex items-center justify-center gap-1 sm:gap-3">
    <button class="flex size-11 shrink-0 items-center justify-center rounded focus-visible:outline-amber-200 disabled:opacity-20" :disabled="isMin" @click="prev" :aria-label="text.previousDay">
      <ChevronLeft class="w-5 h-5" />
    </button>

    <span class="min-w-0 text-center font-medium">{{ label }}</span>

    <button class="flex size-11 shrink-0 items-center justify-center rounded focus-visible:outline-amber-200 disabled:opacity-20" :disabled="isMax" @click="next" :aria-label="text.nextDay">
      <ChevronRight class="w-5 h-5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { prettifyDate, isoAddDays, maxForwardDate } from '../constants/zodiac'

import { useUiText } from '../utils/uiText'

const { locale, text } = useUiText()

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e:'update:modelValue', v:string):void }>()

const label = computed(() => prettifyDate(props.modelValue, locale.value))
const isMax = computed(() => {
  const limit = maxForwardDate()
  return !limit || props.modelValue >= limit
})
const isMin = computed(() => props.modelValue <= '1970-01-01') // safe floor

function prev(){ if(!isMin.value) emit('update:modelValue', isoAddDays(props.modelValue,-1)) }
function next(){ if(!isMax.value) emit('update:modelValue', isoAddDays(props.modelValue, 1)) }
</script>
