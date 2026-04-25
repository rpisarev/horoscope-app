<template>
  <transition name="tip">
    <div
      v-if="show"
      class="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-full
             w-56 px-4 py-3 rounded-2xl
             border border-white/25 bg-white/15 backdrop-blur-md
             text-white shadow-xl select-none z-50
             cursor-pointer"
    >
      <h3 class="font-merienda text-xl text-center leading-none mb-1">
        {{ sign }}
      </h3>

      <p class="font-lato text-sm text-center tracking-wide">
        {{ range }}
      </p>

      <p class="font-lato text-xs text-center tracking-wide mt-2 text-white/75">
        Click to open horoscope
      </p>
    </div>
  </transition>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  sign: string
  range: string
}>()
</script>

<style scoped>
.tip-enter-active,
.tip-leave-active {
  transition: .2s ease;
}

.tip-enter-from,
.tip-leave-to {
  opacity: 0;
  transform: scale(.8) translateY(-0.5rem);
}
</style>