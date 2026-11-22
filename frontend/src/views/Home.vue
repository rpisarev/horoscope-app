<template>
  <Starfield />

  <main class="home relative text-center text-white">
    <header class="home-intro px-4" lang="ru">
      <h1 class="font-serif text-2xl font-semibold sm:text-3xl">Гороскоп на сегодня</h1>
      <p class="mt-1 text-slate-200">Выберите свой знак.</p>
    </header>
    <ZodiacWheel class="home-wheel" :zodiacs="HOME_ZODIACS" @select="goToHoroscope" />
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

<style scoped>
.home {
  display: grid;
  height: 100svh;
  min-height: min-content;
  overflow: clip;
  grid-template-rows: minmax(min-content, 1fr) auto minmax(0, 1fr);
  justify-items: center;
}

/* Keep the full orbit available to the signs, their focus rings and tooltips. */
.home-wheel {
  position: relative;
  grid-row: 2;
  width: min(100vw, 100svh, 600px);
  aspect-ratio: 1;
}

.home-intro {
  grid-row: 1;
  align-self: end;
  padding-block: 0.25rem;
  text-wrap: balance;
}

/* On larger screens the tooltip opens above the hovered sign. */
@media (min-width: 768px) and (min-height: 768px) {
  .home {
    grid-template-rows: minmax(0, 1fr) auto minmax(min-content, 1fr);
  }

  .home-intro {
    grid-row: 3;
    align-self: start;
  }
}

@media (max-height: 767px) and (min-width: 480px) and (min-aspect-ratio: 4/3) {
  .home {
    grid-template: auto / minmax(0, 16rem) auto;
    align-items: center;
    justify-content: center;
  }

  .home-intro, .home-wheel {
    grid-row: 1;
  }

  .home-intro {
    align-self: center;
    padding-inline: 0.5rem;
  }
}
</style>
