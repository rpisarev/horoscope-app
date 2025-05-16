<template>
  <div
    class="fixed inset-0 flex items-center justify-center pointer-events-none"
  >
    <div
      ref="wheel"
      class="relative w-[100px] h-[100px] animate-spin-slow
             pointer-events-auto"
      style="transform-origin:50% 50%"
    >
      <div 
        v-for="(z,i) in zodiacs"
        :key="z.name"
        :style="circleStyle(i)"
        class="absolute"
      >
        <div
          class="group flex flex-col items-center justify-center
                 w-24 h-24 rounded-full bg-amber-400/90 text-black
                 cursor-pointer animate-spin-inner-reverse"
          @mouseenter="pause(z)"
          @mouseleave="resume"
          @click="$emit('select', z)"
        >
          <span class="text-3xl">{{ z.glyph }}</span>
          <small class="-mt-1">{{ z.name }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const props = defineProps({ 
  zodiacs: Array
})
const wheel   = ref(null)

function circleStyle(i) {
  const a = i * 360 / props.zodiacs.length
  return { transform:`rotate(${a}deg) translateY(-240px) rotate(-${a}deg)` }
}
function setInner(playState) {
  wheel.value
    ?.querySelectorAll('.animate-spin-inner, .animate-spin-inner-reverse')
    .forEach(el => { el.style.animationPlayState = playState })
}
function pause ()  {
  wheel.value.style.animationPlayState='paused'
  setInner('paused')
}
function resume () {
  wheel.value.style.animationPlayState='running'
  setInner('running')
}
</script>
