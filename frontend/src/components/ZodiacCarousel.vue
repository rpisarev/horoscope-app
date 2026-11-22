<template>
  <div class="relative select-none">
    <button type="button" class="sign-arrow left-0" @click="prev" :aria-label="text.previousSign">
      <ChevronLeft class="w-6 h-6" />
    </button>

    <Swiper
      :breakpoints="breakpoints"
      :centered-slides="true"
      :loop="true"
      :initial-slide="initialIndex"
      :onSwiper="capture"
      @slideChange="onSlide"
    >
      <SwiperSlide v-for="(z,i) in zodiacs" :key="z.key">
        <div :class="['flex flex-col items-center gap-0.5 transition-opacity', i===active? 'opacity-100':'opacity-50']">
          <span class="text-3xl">{{ z.glyph }}</span>
          <span class="text-sm">{{ zodiacName(z, locale) }}</span>
          <small class="text-xs text-gray-400">{{ formatRange(z.start, z.end, locale) }}</small>
        </div>
      </SwiperSlide>
    </Swiper>

    <button type="button" class="sign-arrow right-0" @click="next" :aria-label="text.nextSign">
      <ChevronRight class="w-6 h-6" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Swiper as SwiperType } from 'swiper'
import { Swiper, SwiperSlide } from 'swiper/vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { ZODIACS, findIndexByKey, formatRange, zodiacName } from '../constants/zodiac'
import { useUiText } from '../utils/uiText'

const { locale, text } = useUiText()

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e:'update:modelValue', v:string):void }>()

const swiperRef = ref<SwiperType|null>(null)
const zodiacs = ZODIACS
const initialIndex = findIndexByKey(props.modelValue)
const active = ref(initialIndex)

const breakpoints = {
  0:   { slidesPerView: 1 },
  768: { slidesPerView: 1   },
}

function onSlide(sw: SwiperType){
  const index = sw.realIndex
  if (!Number.isInteger(index) || index < 0 || index >= zodiacs.length) return
  active.value = index
  emit('update:modelValue', zodiacs[active.value].key)
}

const prev = () => swiperRef.value?.slidePrev()
const next = () => swiperRef.value?.slideNext()

function capture (sw: SwiperType) {
  swiperRef.value = sw
}

watch(
  () => props.modelValue,
  (val) => {
    const idx = findIndexByKey(val)
    if (swiperRef.value && idx !== active.value) {
      swiperRef.value.slideToLoop(idx)
      active.value = idx
    }
  }
)
</script>

<style scoped>
.sign-arrow {
  @apply absolute top-1/2 z-10 flex size-11 -translate-y-1/2 items-center justify-center rounded;
  @apply focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-200;
}
</style>

