<template>
  <NotFound v-if="isRouteInvalid" />

  <main
    v-else-if="!isYearsLoaded"
    class="max-w-3xl mx-auto px-4 py-8 text-center"
  >
    <p>Загрузка архива...</p>
  </main>

  <main v-else class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
    <ZodiacCarousel v-model="sign" />

    <div class="flex w-full gap-4 items-center">
      <YearSwiper v-model="year" :years="years" class="flex-none" />

      <article
        class="flex-1 bg-white/5 rounded-xl p-6 min-h-[160px] text-center animate-fade-in shadow"
      >
        <p v-if="isLoading">Загрузка прогноза...</p>

        <p v-else-if="errorText">{{ errorText }}</p>

        <p v-else>{{ forecastText }}</p>
      </article>

      <MonthSwiper v-model="month" class="flex-none" />
    </div>

    <DaySlider v-model="dateISO" class="self-center mt-4" />

    <div class="flex justify-between items-center">
      <RouterLink :to="mainLink" class="underline">Главная</RouterLink>

      <RouterLink :to="archiveMonthLink" class="underline">К месяцу</RouterLink>
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
import NotFound from './NotFound.vue'

import {
  clampArchiveDay,
  isKnownSign,
  pad2,
  parseArchiveDayParam,
  parseMonthParam,
  parseYearParam,
  routeParamToString,
} from '../utils/routeValidation'

const route = useRoute()
const router = useRouter()

const today = new Date()
const fallbackYear = today.getUTCFullYear()
const fallbackMonth = today.getUTCMonth() + 1
const fallbackDay = today.getUTCDate()

const years = ref<number[]>([])
const isYearsLoaded = ref(false)

const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

function getRouteSign() {
  return routeParamToString(route.params.sign)
}

function getRouteYear() {
  return parseYearParam(route.params.year) ?? fallbackYear
}

function getRouteMonth() {
  return parseMonthParam(route.params.month) ?? fallbackMonth
}

function getRouteDay() {
  return parseArchiveDayParam(route.params.day) ?? fallbackDay
}

const sign = ref(getRouteSign())
const year = ref(getRouteYear())
const month = ref(getRouteMonth())
const day = ref(getRouteDay())

const isStaticRouteInvalid = computed(() => (
  !isKnownSign(route.params.sign) ||
  parseYearParam(route.params.year) === null ||
  parseMonthParam(route.params.month) === null ||
  parseArchiveDayParam(route.params.day) === null
))

const isYearUnavailable = computed(() => {
  const routeYear = parseYearParam(route.params.year)

  if (routeYear === null) {
    return false
  }

  return (
    isYearsLoaded.value &&
    years.value.length > 0 &&
    !years.value.includes(routeYear)
  )
})

const isRouteInvalid = computed(() => (
  isStaticRouteInvalid.value ||
  isYearUnavailable.value
))

function syncRouteToState() {
  if (!isYearsLoaded.value || isStaticRouteInvalid.value || isYearUnavailable.value) {
    return
  }

  sign.value = getRouteSign()
  year.value = getRouteYear()
  month.value = getRouteMonth()
  day.value = getRouteDay()
}

watch(
  () => [route.params.sign, route.params.year, route.params.month, route.params.day],
  syncRouteToState
)

const pad = pad2

const dateISO = computed<string>({
  get: () => `${year.value}-${pad(month.value)}-${pad(day.value)}`,

  set: (value: string) => {
    const [nextYear, nextMonth, nextDay] = value.split('-').map(Number)

    if (
      Number.isSafeInteger(nextYear) &&
      Number.isSafeInteger(nextMonth) &&
      Number.isSafeInteger(nextDay)
    ) {
      year.value = nextYear
      month.value = nextMonth
      day.value = nextDay
    }
  },
})

async function loadForecast() {
  if (!isYearsLoaded.value || isRouteInvalid.value) {
    return
  }

  isLoading.value = true
  errorText.value = ''

  const y = String(year.value).padStart(4, '0')
  const m = pad(month.value)
  const d = pad(day.value)

  try {
    const res = await fetch(`/api/forecast?sign=${sign.value}&date=${y}-${m}-${d}`)

    if (!res.ok) {
      forecastText.value = ''
      errorText.value = 'Не удалось загрузить прогноз'

      return
    }

    const data = await res.json()

    forecastText.value = data.text ?? 'Прогноз пока пуст'
  } catch (err) {
    forecastText.value = ''
    errorText.value = 'Ошибка загрузки'

    console.error('Failed to load forecast', err)
  } finally {
    isLoading.value = false
  }
}

watch(
  [sign, year, month, day, isYearsLoaded],
  async ([nextSign, nextYear, nextMonth, nextDay]) => {
    if (!isYearsLoaded.value || isRouteInvalid.value) {
      forecastText.value = ''
      errorText.value = ''
      isLoading.value = false

      return
    }

    const clampedDay = clampArchiveDay(nextYear, nextMonth, nextDay)

    if (clampedDay !== nextDay) {
      day.value = clampedDay

      return
    }

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

onMounted(async () => {
  try {
    const res = await fetch('/api/years')
    years.value = await res.json()
  } catch (err) {
    console.error('Failed to load years list', err)
  } finally {
    isYearsLoaded.value = true
    syncRouteToState()
  }
})

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