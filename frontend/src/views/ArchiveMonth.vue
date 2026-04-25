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

    <div class="flex flex-col md:flex-row w-full max-w-5xl gap-4">
      <YearSwiper
        v-model="year"
        :years="years"
        class="flex-none order-1 md:order-none"
      />

      <div class="flex-1 flex flex-col items-center order-3 md:order-none">
        <h2 class="text-2xl mb-4 capitalize">
          {{ monthName }} {{ year }}
        </h2>

        <div class="grid grid-cols-7 gap-1 w-full max-w-md">
          <div v-for="d in weekDays" :key="d" class="text-center font-bold">
            {{ d }}
          </div>

          <template v-for="day in calendarDays" :key="day.key">
            <router-link
              v-if="day.active"
              :to="day.to"
              class="p-2 rounded text-center hover:bg-amber-400/40 transition-colors"
            >
              {{ day.number }}
            </router-link>

            <span
              v-else
              class="p-2 rounded text-center text-gray-500 select-none"
            >
              {{ day.number || '' }}
            </span>
          </template>
        </div>
      </div>

      <MonthSwiper
        v-model="month"
        class="flex-none mb-4 md:mb-0 order-2 md:order-none"
      />
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import dayjs from 'dayjs'

import 'dayjs/locale/ru'

import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'
import NotFound from './NotFound.vue'

import {
  isKnownSign,
  parseMonthParam,
  parseYearParam,
  pad2,
  routeParamToString,
} from '../utils/routeValidation'

const route = useRoute()
const router = useRouter()

const fallbackYear = dayjs().year()
const fallbackMonth = dayjs().month() + 1

const years = ref<number[]>([])
const isYearsLoaded = ref(false)

function getRouteSign() {
  return routeParamToString(route.params.sign)
}

function getRouteYear() {
  return parseYearParam(route.params.year) ?? fallbackYear
}

function getRouteMonth() {
  return parseMonthParam(route.params.month) ?? fallbackMonth
}

const sign = ref(getRouteSign())
const year = ref(getRouteYear())
const month = ref(getRouteMonth())

const isStaticRouteInvalid = computed(() => (
  !isKnownSign(route.params.sign) ||
  parseYearParam(route.params.year) === null ||
  parseMonthParam(route.params.month) === null
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
  if (isStaticRouteInvalid.value || isYearUnavailable.value) {
    return
  }

  sign.value = getRouteSign()
  year.value = getRouteYear()
  month.value = getRouteMonth()
}

watch(
  () => [route.params.sign, route.params.year, route.params.month],
  syncRouteToState
)

watch(
  [sign, year, month, isYearsLoaded],
  ([s, y, m]) => {
    if (!isYearsLoaded.value || isRouteInvalid.value) {
      return
    }

    const nextSign = String(s)
    const nextYear = String(y)
    const nextMonth = pad2(Number(m))

    if (
      route.params.sign === nextSign &&
      route.params.year === nextYear &&
      route.params.month === nextMonth
    ) {
      return
    }

    router.replace({
      name: 'archive-month',
      params: {
        sign: nextSign,
        year: nextYear,
        month: nextMonth,
      },
    })
  },
  { immediate: true }
)

const monthName = computed(() =>
  dayjs(`${year.value}-${pad2(month.value)}-01`)
    .locale('ru')
    .format('MMMM')
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

const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const calendarDays = computed(() => {
  const firstDay = dayjs(`${year.value}-${pad2(month.value)}-01`)
  const daysInMonth = firstDay.daysInMonth()
  const today = dayjs()

  const items: {
    key: string
    number: number
    active: boolean
    to: RouteLocationRaw
  }[] = []

  const startIdx = (firstDay.day() + 6) % 7

  for (let i = 0; i < startIdx; i++) {
    items.push({ key: `p${i}`, number: 0, active: false, to: '' })
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const date = dayjs(`${year.value}-${pad2(month.value)}-${pad2(d)}`)
    const future = date.isAfter(today, 'day')
    const sameDay = date.isSame(today, 'day')
    const active = !future && !sameDay

    items.push({
      key: `d${d}`,
      number: d,
      active,
      to: {
        name: 'archive-forecast',
        params: {
          sign: sign.value,
          year: date.format('YYYY'),
          month: date.format('MM'),
          day: date.format('DD'),
        },
      },
    })
  }

  return items
})
</script>