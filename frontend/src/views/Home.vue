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
import { HOME_ZODIACS } from '../constants/zodiac'
import { refreshBusinessDate } from '../utils/businessDate'

const router = useRouter()

async function goToHoroscope(zodiac) {
  try {
    const { business_date } = await refreshBusinessDate()
    await router.push({
      name: 'horoscope',
      params: { sign: zodiac.slug, day: business_date },
    })
  } catch {
    // App displays the metadata error and retry action.
  }
}
</script>