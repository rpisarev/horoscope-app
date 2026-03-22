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
import { ref, watch, nextTick } from 'vue';
import { Swiper, SwiperSlide } from 'swiper/vue';
import type { Swiper as SwiperInstance } from 'swiper';
import { ChevronUp, ChevronDown } from 'lucide-vue-next';
import 'swiper/css';

const months = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'
];

const props = defineProps({
  modelValue: { type: Number, required: true }, // 1‑12
});
const emit = defineEmits(['update:modelValue']);

const swiperRef = ref<SwiperInstance | null>(null)

const initialIndex = props.modelValue - 1

const setSwiper = (s: SwiperInstance) => {
  swiperRef.value = s
  syncToModel()
}

function onSlide(swiper: SwiperInstance) {
  emit('update:modelValue', swiper.realIndex + 1)
}

function syncToModel () {
  nextTick(() => {
    if (!swiperRef.value) return
        swiperRef.value.slideToLoop(props.modelValue - 1, 0)
  })
}

watch(() => props.modelValue, syncToModel)

function slideClass(i) {
  return (i+1) === props.modelValue ? 'font-bold text-amber-500' : 'text-gray-500 dark:text-white/70';
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
