<template>
  <Starfield/>
  <main class="relative min-h-screen text-center text-white">
    <ZodiacWheel :zodiacs="data" @select="open"/>
    <ZodiacModal :show="!!current" :zodiac="current" @close="current=null">
      <!--  <HoroscopeCard :sign="current.name" /> -->
    </ZodiacModal>
  </main>
</template>
<script setup>
import { ref } from 'vue'
import Starfield from '../components/Starfield.vue'
import ZodiacWheel from '../components/ZodiacWheel.vue'
import ZodiacModal from '../components/ZodiacModal.vue'
import data from '../data/zodiac'
const current = ref(null)
function open(z){ current.value = z }
</script>

