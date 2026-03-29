<template>
  <main class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
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

const route = useRoute()
const router = useRouter()

function getTodayIso() {
  return new Date().toISOString().slice(0, 10)
}

function getRouteSign() {
  return String(route.params.sign || 'capricorn')
}

function getRouteDay() {
  return String(route.params.day || getTodayIso())
}

const sign = ref(getRouteSign())
const day = ref(getRouteDay())

const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

watch(
  () => [route.params.sign, route.params.day],
  () => {
    sign.value = getRouteSign()
    day.value = getRouteDay()
  }
)

async function loadForecast() {
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

const archiveLink = computed(
  () => `/archive/${sign.value}/${day.value.slice(0, 4)}/${day.value.slice(5, 7)}`
)

const mainLink = computed(() => '/')
</script>