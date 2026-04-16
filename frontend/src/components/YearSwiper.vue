<template>
  <div class="relative flex flex-col items-center">
    <!-- up arrow -->
    <button
      @click="slidePrev"
      class="text-xl text-gray-400 hover:text-amber-500 focus:outline-none"
    >
      <ChevronUp class="w-6 h-6" />
    </button>

    <swiper
      v-if="years.length"
      direction="vertical"
      :loop="false"
      :slides-per-view="1"
      :initial-slide="initialIndex"
      class="h-96 w-16"
      @slideChange="onSlide"
      @swiper="setSwiper"
    >
      <swiper-slide
        v-for="y in years"
        :key="y"
        class="flex items-center justify-center text-lg"
        :class="y === modelValue ? 'font-bold text-amber-500' : 'text-gray-500'"
      >
        {{ y }}
      </swiper-slide>
    </swiper>

    <!-- down arrow -->
    <button
      @click="slideNext"
      class="text-xl text-gray-400 hover:text-amber-500 focus:outline-none"
    >
      <ChevronDown class="w-6 h-6" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ChevronUp, ChevronDown } from 'lucide-vue-next'
import { Swiper, SwiperSlide } from 'swiper/vue'
import type { Swiper as SwiperInstance } from 'swiper'
import 'swiper/css'

const props = defineProps<{
  modelValue: number
  years: number[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

const swiperRef = ref<SwiperInstance | null>(null)
const isSyncing = ref(false)

const initialIndex = computed(() => {
  const idx = props.years.indexOf(props.modelValue)
  return idx >= 0 ? idx : 0
})

function releaseSyncFlag() {
  setTimeout(() => {
    isSyncing.value = false
  }, 0)
}

function syncToModel() {
  nextTick(() => {
    const swiper = swiperRef.value
    if (!swiper) return

    const idx = props.years.indexOf(props.modelValue)
    if (idx < 0) return
    if (swiper.activeIndex === idx) return

    isSyncing.value = true
    swiper.slideTo(idx, 0)
    releaseSyncFlag()
  })
}

function setSwiper(swiper: SwiperInstance) {
  swiperRef.value = swiper
  syncToModel()
}

function onSlide(swiper: SwiperInstance) {
  const idx = swiper.activeIndex
  const value = props.years[idx]

  if (isSyncing.value) {
    isSyncing.value = false
    return
  }

  if (typeof value === 'number' && value !== props.modelValue) {
    emit('update:modelValue', value)
  }
}

watch(() => props.modelValue, syncToModel)
watch(() => props.years, syncToModel, { deep: true })

const slidePrev = () => swiperRef.value?.slidePrev()
const slideNext = () => swiperRef.value?.slideNext()
</script>

<style scoped>
.swiper-slide {
  display: flex;
  justify-content: center;
  align-items: center;
}
</style>