<template>
  <transition name="card">
    <div v-if="show"
         class="absolute -translate-x-1/2 -translate-y-full
                w-80 max-w-[92vw] px-6 py-4 rounded-xl
                border border-white/25 bg-white/10 backdrop-blur-sm
                text-white shadow-lg z-50">
      <h3 class="font-merienda text-2xl text-center mb-1">{{ sign }}</h3>
      <p  class="font-lato text-base text-center mb-4">{{ range }}</p>
      <p  class="font-lato text-sm leading-relaxed mb-6">{{ forecast }}</p>
      <a :href="moreUrl"
         class="block mx-auto w-max border border-white/30 rounded-full
                px-4 py-1 text-sm font-lato tracking-wide hover:bg-white/10">
        More →
      </a>
    </div>
  </transition>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  sign: string
  range: string
  forecast: string
  moreUrl: string
}>()
</script>

<style scoped>
.card-enter-active,.card-leave-active{transition:.25s ease}
.card-enter-from,.card-leave-to{opacity:0;transform:scale(.8)}
</style>
