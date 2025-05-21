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
          class="group relative flex flex-col items-center justify-center
                 w-24 h-24 rounded-full bg-amber-400/90 text-black
                 cursor-pointer animate-spin-inner-reverse"
          @mouseenter="enter(i)"
          @mouseleave="leave"
          @click="toggle(i, z)"
        >
          <span class="text-3xl">{{ z.glyph }}</span>
          <small class="-mt-1">{{ z.name }}</small>
	  <ZodiacTooltip
            :show="active===i && !expanded"
            :sign="z.name"
            :range="z.range"
          />

          <!-- Card (№2) -->
          <ZodiacCard
            :show="active===i && expanded"
            :sign="z.name"
            :range="z.range"
            :forecast="z.forecast ?? 'A favourable day for bold moves.'"
            :more-url="`/horoscope/${z.slug || z.name.toLowerCase()}/${today}`"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ZodiacTooltip from './ZodiacTooltip.vue'
import ZodiacCard    from './ZodiacCard.vue'
const props = defineProps({ 
  zodiacs: Array
})
const emit   = defineEmits(['select'])
const wheel   = ref(null)
const active   = ref(null)   // index of sign
const expanded = ref(false)  // true → card (№2)
const today    = new Date().toISOString().slice(0,10)

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
function enter (idx) {
  active.value = idx
  pause()
}
function leave () {
  if (!expanded.value) { resume(); active.value = null }
}
function toggle (idx, z) {
  if (active.value === idx && expanded.value) {
    expanded.value = false
    resume()
  } else {
    active.value = idx
    expanded.value = true
    pause()
  }
  emit('select', z)
}
</script>
