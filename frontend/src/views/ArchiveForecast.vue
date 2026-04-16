<template>
  <main class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
    <ZodiacCarousel v-model="sign" />

    <div class="flex w-full gap-4 items-center">
      <YearSwiper v-model="year" :years="years" class="flex-none" />

      <article
        class="flex-1 bg-white/5 rounded-xl p-6 min-h-[160px] text-center animate-fade-in shadow"
      >
        <p v-if="isLoading">Прогноз завантажується...</p>
        <p v-else-if="errorText">{{ errorText }}</p>
        <p v-else>{{ forecastText }}</p>
      </article>

      <MonthSwiper v-model="month" class="flex-none" />
    </div>

    <DaySlider v-model="dateISO" class="self-center mt-4" />

    <div class="flex justify-between items-center">
      <RouterLink :to="mainLink" class="underline">Головна</RouterLink>
      <RouterLink :to="archiveMonthLink" class="underline">До місяця</RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'
import DaySlider from '../components/DaySlider.vue'

const route = useRoute()
const router = useRouter()

function getTodayParts() {
  const now = new Date()
  return {
    sign: 'capricorn',
    year: now.getUTCFullYear(),
    month: now.getUTCMonth() + 1,
    day: now.getUTCDate(),
  }
}

function getRouteSign() {
  return String(route.params.sign || getTodayParts().sign)
}

function getRouteYear() {
  return Number(route.params.year) || getTodayParts().year
}

function getRouteMonth() {
  return Number(route.params.month) || getTodayParts().month
}

function getRouteDay() {
  return Number(route.params.day) || getTodayParts().day
}

const sign = ref(getRouteSign())
const year = ref(getRouteYear())
const month = ref(getRouteMonth())
const day = ref(getRouteDay())

const years = ref<number[]>([])
const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

onMounted(async () => {
  try {
    const res = await fetch('/api/years')
    years.value = await res.json()

    if (years.value.length && !years.value.includes(year.value)) {
      year.value = years.value[years.value.length - 1]
    }
  } catch (err) {
    console.error('Failed to load years list', err)
  }
})

watch(
  () => [route.params.sign, route.params.year, route.params.month, route.params.day],
  () => {
    sign.value = getRouteSign()
    year.value = getRouteYear()
    month.value = getRouteMonth()
    day.value = getRouteDay()
  }
)

const pad = (n: number) => String(n).padStart(2, '0')

const dateISO = computed<string>({
  get: () => `${year.value}-${pad(month.value)}-${pad(day.value)}`,
  set: (v: string) => {
    const [y, m, d] = v.split('-').map(Number)

    if (!Number.isNaN(y) && !Number.isNaN(m) && !Number.isNaN(d)) {
      year.value = y
      month.value = m
      day.value = d
    }
  },
})

async function loadForecast() {
  isLoading.value = true
  errorText.value = ''

  const y = String(year.value).padStart(4, '0')
  const m = pad(month.value)
  const d = pad(day.value)

  try {
    const res = await fetch(`/api/forecast?sign=${sign.value}&date=${y}-${m}-${d}`)

    if (!res.ok) {
      forecastText.value = ''
      errorText.value = 'Не вдалося завантажити прогноз'
      return
    }

    const data = await res.json()
    forecastText.value = data.text ?? 'Порожній прогноз'
  } catch (err) {
    forecastText.value = ''
    errorText.value = 'Помилка завантаження'
    console.error('Failed to load forecast', err)
  } finally {
    isLoading.value = false
  }
}

watch(
  [sign, year, month, day],
  async ([nextSign, nextYear, nextMonth, nextDay]) => {
    const routeSign = String(route.params.sign || '')
    const routeYear = String(route.params.year || '')
    const routeMonth = String(route.params.month || '')
    const routeDay = String(route.params.day || '')

    const nextYearStr = String(nextYear)
    const nextMonthStr = pad(nextMonth)
    const nextDayStr = pad(nextDay)

    if (
      routeSign !== nextSign ||
      routeYear !== nextYearStr ||
      routeMonth !== nextMonthStr ||
      routeDay !== nextDayStr
    ) {
      await router.replace({
        name: 'archive-forecast',
        params: {
          sign: nextSign,
          year: nextYearStr,
          month: nextMonthStr,
          day: nextDayStr,
        },
      })
    }

    await loadForecast()
  },
  { immediate: true }
)

const mainLink = computed(() => ({
  name: 'home',
}))

const archiveMonthLink = computed(() => ({
  name: 'archive-month',
  params: {
    sign: sign.value,
    year: String(year.value),
    month: pad(month.value),
  },
}))
</script>

<style scoped>
</style>