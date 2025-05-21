<template>
  <transition name="tip">
    <div v-if="show"
         class="absolute -translate-x-1/2 -translate-y-full
                px-3 py-1.5 w-44 rounded-xl
                border border-white/20 bg-white/10 backdrop-blur-sm
                text-white shadow-lg select-none z-50">
      <h3 class="font-merienda text-lg text-center leading-none">{{ sign }}</h3>
      <p  class="font-lato text-sm text-center tracking-wide">{{ range }}</p>
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
.tip-enter-active,.tip-leave-active{transition:.2s ease}
.tip-enter-from,.tip-leave-to{opacity:0;transform:scale(.8)}
</style>
