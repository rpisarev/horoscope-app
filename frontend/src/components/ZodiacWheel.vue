<template>
  <div class="zodiac-wheel fixed inset-0 flex items-center justify-center pointer-events-none">
    <div
      ref="wheel"
      class="wheel-orbit relative animate-spin-slow pointer-events-auto"
      style="transform-origin:50% 50%"
    >
      <div
        v-for="(z, i) in zodiacs"
        :key="z.slug || z.name"
        :style="circleStyle(i)"
        class="absolute"
      >
        <div
          class="wheel-sign group relative flex flex-col items-center justify-center
                 rounded-full bg-amber-400/90 text-black
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
          <span class="wheel-glyph">{{ z.glyph }}</span>
          <small class="wheel-name -mt-1">{{ z.name }}</small>

          <ZodiacTooltip
            class="wheel-tooltip-orbit"
            :show="active === i"
            :sign="z.name"
            :range="z.range"
          />
        </div>
      </div>
    </div>

    <ZodiacTooltip
      class="wheel-tooltip-center"
      :show="active !== null"
      :sign="zodiacs[active]?.name || ''"
      :range="zodiacs[active]?.range || ''"
    />
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
    transform: `rotate(${a}deg) translateY(calc(-1 * var(--wheel-radius))) rotate(-${a}deg)`,
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

<style scoped>
.zodiac-wheel {
  --wheel-node-size: clamp(3.5rem, 16vmin, 6rem);
  /* Reserve 12px for the focus ring at every point in the rotation. */
  --wheel-radius: min(240px,
    calc(50vw - var(--wheel-node-size) / 2 - 12px),
    calc(50svh - var(--wheel-node-size) / 2 - 12px));
}

.wheel-orbit,
.wheel-sign {
  width: var(--wheel-node-size);
  height: var(--wheel-node-size);
}

.wheel-glyph {
  font-size: clamp(1.25rem, 5vmin, 1.875rem);
  line-height: 1.2;
}

.wheel-name {
  font-size: clamp(.625rem, 2.2vmin, .8rem);
}

.wheel-tooltip-center {
  display: none;
}

@media (max-width: 767px), (max-height: 767px) {
  .wheel-tooltip-orbit {
    display: none;
  }

  .wheel-tooltip-center {
    display: block;
    left: 50%;
    top: 50%;
    width: min(14rem, 45vmin);
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .wheel-tooltip-center :deep(h3) {
    font-size: 1rem;
  }

  .wheel-tooltip-center :deep(p) {
    font-size: .75rem;
    line-height: 1rem;
  }
}
</style>
