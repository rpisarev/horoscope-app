<template>
  <div class="flex items-center justify-center gap-3">
    <button class="p-2 disabled:opacity-20" :disabled="isMin" @click="prev" aria-label="Prev day">
      <ChevronLeft class="w-5 h-5" />
    </button>

    <span class="font-medium whitespace-nowrap">{{ label }}</span>

    <button class="p-2 disabled:opacity-20" :disabled="isMax" @click="next" aria-label="Next day">
      <ChevronRight class="w-5 h-5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { prettifyDate, isoAddDays, maxForwardDate } from '../constants/zodiac'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e:'update:modelValue', v:string):void }>()

const label = computed(() => prettifyDate(props.modelValue))
const isMax = computed(() => props.modelValue >= maxForwardDate)
const isMin = computed(() => props.modelValue <= '1970-01-01') // safe floor

function prev(){ if(!isMin.value) emit('update:modelValue', isoAddDays(props.modelValue,-1)) }
function next(){ if(!isMax.value) emit('update:modelValue', isoAddDays(props.modelValue, 1)) }
</script>
