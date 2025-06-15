<template>
  <div class="relative flex flex-col items-center">
    <!-- up arrow -->
    <button
      @click="slidePrev"
      class="text-xl text-gray-400 hover:text-amber-500 focus:outline-none"
    >
     <ChevronUp class="w-6 h-6"/>
    </button>

    <swiper
      v-if="years.length"
      direction="vertical"
      :loop="false"
      :slides-per-view="1"
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
    <ChevronDown class="w-6 h-6"/>
    </button>
  </div>
 </template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { ChevronUp, ChevronDown } from 'lucide-vue-next'
import { Swiper, SwiperSlide } from 'swiper/vue';
import type { Swiper as SwiperInstance } from 'swiper';
import 'swiper/css';

const props = defineProps({
  modelValue: { type: Number, required: true },
  years: { type: Array, required: true },
});
const emit = defineEmits(['update:modelValue']);

const swiperRef      = ref<SwiperInstance | null>(null);
const initialIndex   = props.years.indexOf(props.modelValue);

const setSwiper = (s: SwiperInstance) => {
  swiperRef.value = s;
  syncToModel();
};

const slidePrev = () => swiperRef.value?.slidePrev();
const slideNext = () => swiperRef.value?.slideNext();

function onSlide(swiper: SwiperInstance) {
  const y = props.years[swiper.realIndex];
  emit('update:modelValue', y);
}

function syncToModel() {
  nextTick(() => {
    if (!swiperRef.value) return;
    const idx = props.years.indexOf(props.modelValue);
    if (idx !== -1) swiperRef.value.slideToLoop(idx, 0);
  });
}

watch(() => props.modelValue, syncToModel);
</script>

<style scoped>
.swiper-slide {
  display: flex;
  justify-content: center;
  align-items: center;
}
</style>
