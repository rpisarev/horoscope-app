<template>
  <Starfield/>

  <main class="relative min-h-screen text-center text-white">
    <ZodiacWheel :zodiacs="HOME_ZODIACS" @select="open"/>
    <ZodiacModal :show="!!current" :zodiac="current" @close="current=null">
    </ZodiacModal>
  </main>
</template>

<script setup>
import { ref } from 'vue'

import Starfield from '../components/Starfield.vue'
import ZodiacWheel from '../components/ZodiacWheel.vue'
import { HOME_ZODIACS } from '../constants/zodiac'

const current = ref(null)

function open(z) {
  current.value = z
}
</script>