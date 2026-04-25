<template>
  <div class="fixed inset-0 flex items-center justify-center pointer-events-none">
    <div
      ref="wheel"
      class="relative w-[100px] h-[100px] animate-spin-slow pointer-events-auto"
      style="transform-origin:50% 50%"
    >
      <div
        v-for="(z, i) in zodiacs"
        :key="z.slug || z.name"
        :style="circleStyle(i)"
        class="absolute"
      >
        <div
          class="group relative flex flex-col items-center justify-center
                 w-24 h-24 rounded-full bg-amber-400/90 text-black
                 cursor-pointer animate-spin-inner-reverse
                 focus:outline-none focus:ring-2 focus:ring-amber-200"
          role="button"
          tabindex="0"
          @mouseenter="enter(i)"
          @mouseleave="leave"
          @click="select(z)"
          @keydown.enter.prevent="select(z)"
          @keydown.space.prevent="select(z)"
        >
          <span class="text-3xl">{{ z.glyph }}</span>
          <small class="-mt-1">{{ z.name }}</small>

          <ZodiacTooltip
            :show="active === i"
            :sign="z.name"
            :range="z.range"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

import ZodiacTooltip from './ZodiacTooltip.vue'

const props = defineProps({
  zodiacs: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['select'])

const wheel = ref(null)
const active = ref(null)

function circleStyle(i) {
  const a = i * 360 / props.zodiacs.length

  return {
    transform: `rotate(${a}deg) translateY(-240px) rotate(-${a}deg)`,
  }
}

function setInner(playState) {
  wheel.value
    ?.querySelectorAll('.animate-spin-inner, .animate-spin-inner-reverse')
    .forEach(el => {
      el.style.animationPlayState = playState
    })
}

function pause() {
  if (!wheel.value) return

  wheel.value.style.animationPlayState = 'paused'
  setInner('paused')
}

function resume() {
  if (!wheel.value) return

  wheel.value.style.animationPlayState = 'running'
  setInner('running')
}

function enter(idx) {
  active.value = idx
  pause()
}

function leave() {
  active.value = null
  resume()
}

function select(zodiac) {
  emit('select', zodiac)
}
</script>