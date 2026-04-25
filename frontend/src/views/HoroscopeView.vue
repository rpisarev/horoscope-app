<template>
  <NotFound v-if="isRouteInvalid" />

  <main v-else class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
    <ZodiacCarousel v-model="sign" />

    <DaySlider v-model="day" />

    <article class="bg-white/5 rounded-xl p-6 min-h-[160px] animate-fade-in shadow">
      <p v-if="isLoading">Завантаження прогнозу...</p>

      <p v-else-if="errorText">{{ errorText }}</p>

      <p v-else>{{ forecastText }}</p>
    </article>

    <div class="flex justify-between items-center">
      <RouterLink :to="mainLink" class="underline">Главная</RouterLink>

      <RouterLink :to="archiveLink" class="underline">Архив</RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import DaySlider from '../components/DaySlider.vue'
import NotFound from './NotFound.vue'

import {
  isKnownSign,
  isRealIsoDate,
  routeParamToString,
} from '../utils/routeValidation'

const route = useRoute()
const router = useRouter()

function getRouteSign() {
  return routeParamToString(route.params.sign)
}

function getRouteDay() {
  return routeParamToString(route.params.day)
}

const isRouteInvalid = computed(() => (
  !isKnownSign(route.params.sign) ||
  !isRealIsoDate(route.params.day)
))

const sign = ref(getRouteSign())
const day = ref(getRouteDay())

const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

watch(
  () => [route.params.sign, route.params.day],
  () => {
    if (isRouteInvalid.value) {
      return
    }

    sign.value = getRouteSign()
    day.value = getRouteDay()
  }
)

async function loadForecast() {
  if (isRouteInvalid.value) {
    return
  }

  isLoading.value = true
  errorText.value = ''

  try {
    const res = await fetch(`/api/forecast?sign=${sign.value}&date=${day.value}`)

    if (!res.ok) {
      errorText.value = 'Не вдалося завантажити прогноз'
      forecastText.value = ''

      return
    }

    const data = await res.json()
    forecastText.value = data.text ?? 'Порожній прогноз'
  } catch (err) {
    errorText.value = 'Помилка завантаження'
    forecastText.value = ''

    console.error('Failed to load forecast', err)
  } finally {
    isLoading.value = false
  }
}

watch(
  [sign, day],
  async ([nextSign, nextDay]) => {
    if (isRouteInvalid.value) {
      forecastText.value = ''
      errorText.value = ''
      isLoading.value = false

      return
    }

    if (
      route.params.sign !== nextSign ||
      route.params.day !== nextDay
    ) {
      await router.replace({
        name: 'horoscope',
        params: {
          sign: nextSign,
          day: nextDay,
        },
      })
    }

    await loadForecast()
  },
  { immediate: true }
)

const archiveLink = computed(() => ({
  name: 'archive-month',
  params: {
    sign: sign.value,
    year: day.value.slice(0, 4),
    month: day.value.slice(5, 7),
  },
}))

const mainLink = computed(() => ({
  name: 'home',
}))
</script>