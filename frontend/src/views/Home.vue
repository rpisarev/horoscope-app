<template>
  <Starfield />

  <main class="relative min-h-screen text-center text-white">
    <ZodiacWheel :zodiacs="HOME_ZODIACS" @select="goToHoroscope" />
  </main>
</template>

<script setup>
import { useRouter } from 'vue-router'

import Starfield from '../components/Starfield.vue'
import ZodiacWheel from '../components/ZodiacWheel.vue'
import { HOME_ZODIACS, todayIso } from '../constants/zodiac'

const router = useRouter()

function goToHoroscope(zodiac) {
  router.push({
    name: 'horoscope',
    params: {
      sign: zodiac.slug,
      day: todayIso(),
    },
  })
}
</script>