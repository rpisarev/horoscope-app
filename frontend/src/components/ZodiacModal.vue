<template>
<transition enter-from-class="opacity-0" leave-to-class="opacity-0">
  <div v-if="show" class="fixed inset-0 bg-black/60 flex items-center justify-center z-20">
    <div class="bg-white rounded-xl p-6 w-80 relative">
      <button class="absolute top-2 right-2 text-xl" @click="$emit('close')">✕</button>
      <h2 class="text-2xl font-semibold mb-2">{{ zodiac.name }}</h2>
      <p class="mb-4">{{ zodiac.range }}</p>
      <slot/>
    </div>
  </div>
</transition>
</template>
<script setup>
import { ref } from 'vue'
defineProps({ show:Boolean, zodiac:Object })
defineEmits(['close'])
</script>

