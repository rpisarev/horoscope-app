<template>
  <div class="relative select-none">
    <!-- desktop arrows -->
    <button class="hidden md:flex absolute left-0 z-10 h-7 items-start pt-1 px-1" @click="prev" aria-label="Prev sign">
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
          <span class="text-sm">{{ z.nameRu }}</span>
         <small class="text-xs text-gray-400">{{ formatRange(z.start,z.end) }}</small>
        </div>
      </SwiperSlide>
    </Swiper>

    <button class="hidden md:flex absolute right-0 top-0 z-10 h-7 items-start pt-1 px-1" @click="next" aria-label="Next sign">
      <ChevronRight class="w-6 h-6" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Swiper as SwiperType } from 'swiper'
import { Swiper, SwiperSlide } from 'swiper/vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { ZODIACS, findIndexByKey, formatRange } from '../constants/zodiac'


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

function onSlide(sw: any){
  active.value = sw.realIndex
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

