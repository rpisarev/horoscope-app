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
      direction="vertical"
      :loop="false"
      :slides-per-view="1"
      :initial-slide="initialIndex"
      class="h-96 w-24"
      @slideChange="onSlide"
      @swiper="setSwiper"
    >
      <swiper-slide
        v-for="(m, i) in months"
        :key="i"
        class="flex items-center justify-center text-base capitalize"
        :class="slideClass(i)"
      >
        {{ m }}
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
import { Swiper, SwiperSlide } from 'swiper/vue'
import type { Swiper as SwiperInstance } from 'swiper'
import { ChevronUp, ChevronDown } from 'lucide-vue-next'
import 'swiper/css'

const months = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

const props = defineProps<{
  modelValue: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

const swiperRef = ref<SwiperInstance | null>(null)
const isSyncing = ref(false)

const initialIndex = computed(() => {
  const idx = props.modelValue - 1
  return idx >= 0 && idx < months.length ? idx : 0
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

    const idx = props.modelValue - 1
    if (idx < 0 || idx >= months.length) return
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
  const value = swiper.activeIndex + 1

  if (isSyncing.value) {
    isSyncing.value = false
    return
  }

  if (value !== props.modelValue) {
    emit('update:modelValue', value)
  }
}

watch(() => props.modelValue, syncToModel)

function slideClass(i: number) {
  return i + 1 === props.modelValue
    ? 'font-bold text-amber-500'
    : 'text-gray-500 dark:text-white/70'
}

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