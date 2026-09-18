<template>
  <NotFound v-if="routeError" :title="routeError.message" />

  <main
    v-else
    class="relative isolate min-h-screen overflow-hidden bg-[#070b19] px-4 py-8 text-white"
  >
    <div class="pointer-events-none absolute inset-0" aria-hidden="true">
      <div
        class="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(251,191,36,0.10),_transparent_32%),radial-gradient(circle_at_20%_20%,_rgba(56,189,248,0.12),_transparent_30%),linear-gradient(180deg,_#070b19_0%,_#0f172a_48%,_#020617_100%)]"
      />

      <div
        class="absolute left-10 top-16 h-1 w-1 rounded-full bg-white/70 shadow-[120px_40px_0_rgba(255,255,255,0.35),260px_90px_0_rgba(255,255,255,0.45),420px_20px_0_rgba(255,255,255,0.25),760px_80px_0_rgba(255,255,255,0.35),980px_40px_0_rgba(255,255,255,0.25)]"
      />

      <div class="absolute bottom-0 left-0 right-0 h-56 bg-gradient-to-t from-black/35 to-transparent" />
    </div>

    <section
      v-if="!isYearsLoaded"
      class="relative z-10 mx-auto flex min-h-[60vh] max-w-3xl items-center justify-center text-center"
    >
      <div class="rounded-3xl border border-white/10 bg-white/10 px-8 py-6 shadow-2xl backdrop-blur">
        <p class="font-lato text-white/75">
          Загрузка архива...
        </p>
      </div>
    </section>

    <div v-else class="relative z-10 mx-auto flex max-w-6xl flex-col gap-8">
      <ZodiacCarousel v-model="sign" />

      <section
        class="relative overflow-hidden rounded-[2rem] border border-amber-200/25
        bg-slate-950/55 p-6 shadow-2xl shadow-black/30 backdrop-blur md:p-8"
      >
        <div
          class="pointer-events-none absolute inset-0 opacity-80"
          aria-hidden="true"
        >
          <div class="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-amber-300/10 blur-3xl" />
          <div class="absolute left-1/3 top-10 h-40 w-40 rounded-full bg-sky-300/10 blur-3xl" />
          <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-amber-200/50 to-transparent" />
        </div>

        <div class="relative grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p class="mb-3 font-lato text-xs font-bold uppercase tracking-[0.35em] text-amber-300">
              Архив
            </p>

            <h1 class="font-merienda text-4xl leading-tight text-white md:text-5xl">
              Архив гороскопов
            </h1>

            <p class="mt-3 font-merienda text-2xl text-amber-200">
              {{ zodiacName }} · {{ monthTitle }} {{ year }}
            </p>

            <p class="mt-4 max-w-2xl font-lato text-base leading-7 text-white/70">
              Просматривайте дневные прогнозы для {{ zodiacNameGenitive }}.
              Выберите дату в календаре, чтобы открыть архивный прогноз.
            </p>
          </div>

          <div
            class="flex h-28 w-28 items-center justify-center rounded-full border border-amber-200/35
            bg-slate-950/60 text-6xl text-amber-200 shadow-[0_0_40px_rgba(251,191,36,0.18)]"
            aria-hidden="true"
          >
            {{ zodiacGlyph }}
          </div>
        </div>
      </section>

      <section
        class="rounded-[2rem] border border-white/10 bg-white/[0.06]
        p-4 shadow-2xl shadow-black/25 backdrop-blur md:p-6"
      >
        <div class="grid gap-5 lg:grid-cols-[140px_minmax(0,1fr)_160px]">
          <aside
            class="rounded-3xl border border-white/10 bg-slate-950/35 px-4 py-5
            shadow-inner shadow-white/5"
          >
            <p class="mb-4 text-center font-lato text-xs font-bold uppercase tracking-[0.3em] text-amber-300">
              Год
            </p>

            <YearSwiper
              v-model="year"
              :years="years"
              class="mx-auto"
            />
          </aside>

          <section
            class="rounded-3xl border border-amber-200/15 bg-slate-950/35 p-4
            shadow-inner shadow-white/5 md:p-6"
          >
            <div class="mb-6 text-center">
              <p class="font-lato text-xs font-bold uppercase tracking-[0.28em] text-white/40">
                Календарь архива
              </p>

              <h2 class="mt-2 font-merienda text-3xl text-amber-100">
                {{ monthTitle }} {{ year }}
              </h2>
            </div>

            <div class="grid grid-cols-7 gap-2" aria-label="Календарь архива" :aria-busy="isMonthLoading">
              <div
                v-for="d in weekDays"
                :key="d"
                class="pb-2 text-center font-lato text-xs font-bold uppercase tracking-[0.18em]"
                :class="d === 'Сб' || d === 'Вс' ? 'text-amber-300/80' : 'text-white/45'"
              >
                {{ d }}
              </div>

              <template v-for="day in calendarDays" :key="day.key">
                <router-link
                  v-if="day.active"
                  :to="day.to"
                  :aria-current="day.isToday ? 'date' : undefined"
                  class="group relative flex min-h-12 items-center justify-center rounded-2xl border
                  border-white/10 bg-white/[0.05] font-lato text-lg font-semibold
                  transition duration-200 hover:-translate-y-0.5 hover:border-amber-300/55
                  hover:bg-amber-300/15 hover:text-amber-100 hover:shadow-[0_0_24px_rgba(251,191,36,0.18)]"
                  :class="[
                    day.isWeekend ? 'text-amber-100' : 'text-white',
                    day.isToday ? 'border-amber-300/45 bg-amber-300/10' : '',
                  ]"
                >
                  {{ day.number }}

                  <span
                    class="absolute bottom-1 h-1 w-1 rounded-full bg-emerald-300/80
                    opacity-70 transition group-hover:bg-amber-200 group-hover:opacity-100"
                  />
                </router-link>

                <span
                  v-else
                  class="relative flex min-h-12 items-center justify-center rounded-2xl border
                  font-lato text-lg font-semibold select-none"
                  :class="[
                    day.number === null
                      ? 'border-transparent bg-transparent text-transparent'
                      : '',
                    day.isToday
                      ? 'border-amber-300/45 bg-amber-300/10 text-amber-100 shadow-[0_0_18px_rgba(251,191,36,0.12)]'
                      : '',
                    day.number !== null && !day.isToday
                      ? 'border-white/5 bg-white/[0.025] text-white/25'
                      : '',
                  ]"
                >
                  {{ day.number || '' }}

                  <span
                    v-if="day.isToday"
                    class="absolute bottom-1 font-lato text-[9px] font-bold uppercase tracking-[0.12em] text-amber-300/80"
                  >
                    сегодня
                  </span>
                </span>
              </template>
            </div>

            <div
              class="mt-6 rounded-2xl border border-white/10 bg-white/[0.04]
              px-4 py-3 font-lato text-sm leading-6 text-white/65"
            >
              <span class="mr-2 text-amber-300">ⓘ</span>
              <span v-if="isMonthLoading" role="status">Загрузка доступных прогнозов…</span>
              <span v-else-if="monthError" role="alert">{{ monthError }}</span>
              <span v-else>Доступны дни с опубликованным прогнозом для выбранного знака.</span>
            </div>

          </section>

          <aside
            class="rounded-3xl border border-white/10 bg-slate-950/35 px-4 py-5
            shadow-inner shadow-white/5"
          >
            <p class="mb-4 text-center font-lato text-xs font-bold uppercase tracking-[0.3em] text-amber-300">
              Месяц
            </p>

            <MonthSwiper
              v-model="month"
              class="mx-auto"
            />
          </aside>
        </div>
      </section>

      <nav class="grid gap-4 md:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
        <router-link
          :to="mainLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/25
          bg-slate-950/45 px-6 font-lato text-base font-semibold text-amber-100
          shadow-lg shadow-black/20 transition hover:-translate-y-0.5 hover:border-amber-200/50
          hover:bg-white/10"
        >
          ← Главная
        </router-link>

        <router-link
          v-if="todayForecastLink"
          :to="todayForecastLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/55
          bg-amber-300/85 px-6 font-lato text-base font-bold text-slate-950
          shadow-[0_0_28px_rgba(251,191,36,0.25)] transition hover:-translate-y-0.5
          hover:bg-amber-200"
        >
          Открыть прогноз на сегодня →
        </router-link>
      </nav>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import dayjs from 'dayjs'
import 'dayjs/locale/ru'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'
import NotFound from './NotFound.vue'
import {
  pad2,
  parseMonthParam,
  parseYearParam,
  routeParamToString,
  validateArchiveMonthRoute,
} from '../utils/routeValidation'
import { todayIso } from '../constants/zodiac'

const route = useRoute()
const router = useRouter()

const years = ref<number[]>([])
const isYearsLoaded = ref(false)
const loadedYearsSign = ref('')
const availableDates = ref(new Set<string>())
const availabilityScope = ref('')
const isMonthLoading = ref(false)
const monthError = ref('')
const locale = 'ru'
const forecastType = 'daily'
let monthRequestId = 0
let yearsRequestId = 0

const zodiacMeta: Record<string, {
  name: string
  genitive: string
  glyph: string
}> = {
  aries: {
    name: 'Овен',
    genitive: 'Овна',
    glyph: '♈',
  },
  taurus: {
    name: 'Телец',
    genitive: 'Тельца',
    glyph: '♉',
  },
  gemini: {
    name: 'Близнецы',
    genitive: 'Близнецов',
    glyph: '♊',
  },
  cancer: {
    name: 'Рак',
    genitive: 'Рака',
    glyph: '♋',
  },
  leo: {
    name: 'Лев',
    genitive: 'Льва',
    glyph: '♌',
  },
  virgo: {
    name: 'Дева',
    genitive: 'Девы',
    glyph: '♍',
  },
  libra: {
    name: 'Весы',
    genitive: 'Весов',
    glyph: '♎',
  },
  scorpio: {
    name: 'Скорпион',
    genitive: 'Скорпиона',
    glyph: '♏',
  },
  ophiuchus: {
    name: 'Змееносец',
    genitive: 'Змееносца',
    glyph: '⛎',
  },
  sagittarius: {
    name: 'Стрелец',
    genitive: 'Стрельца',
    glyph: '♐',
  },
  capricorn: {
    name: 'Козерог',
    genitive: 'Козерога',
    glyph: '♑',
  },
  aquarius: {
    name: 'Водолей',
    genitive: 'Водолея',
    glyph: '♒',
  },
  pisces: {
    name: 'Рыбы',
    genitive: 'Рыб',
    glyph: '♓',
  },
}

const requestedMonth = computed(() => validateArchiveMonthRoute(route.params))
const monthScope = computed(() => {
  if (!requestedMonth.value.ok) return ''
  const { sign, year, month } = requestedMonth.value.params
  return `${sign}/${year}/${month}`
})

const routeValidation = computed(() => validateArchiveMonthRoute(
  route.params,
  years.value,
  isYearsLoaded.value && loadedYearsSign.value === routeParamToString(route.params.sign)
))

const routeError = computed(() => (
  routeValidation.value.ok ? null : routeValidation.value
))

function getRouteSign() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.sign
  }

  return routeParamToString(route.params.sign)
}

function getRouteYear() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.year
  }

  return parseYearParam(route.params.year) ?? NaN // Invalid routes render NotFound.
}

function getRouteMonth() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.month
  }

  return parseMonthParam(route.params.month) ?? NaN
}

const sign = ref(getRouteSign())
const year = ref(getRouteYear())
const month = ref(getRouteMonth())

const currentZodiacMeta = computed(() => zodiacMeta[sign.value])

const zodiacName = computed(() => currentZodiacMeta.value?.name ?? sign.value)

const zodiacNameGenitive = computed(() => currentZodiacMeta.value?.genitive ?? zodiacName.value)

const zodiacGlyph = computed(() => currentZodiacMeta.value?.glyph ?? '✦')

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function syncRouteToState() {
  if (routeError.value || !routeValidation.value.ok) {
    return
  }

  sign.value = routeValidation.value.params.sign
  year.value = routeValidation.value.params.year
  month.value = routeValidation.value.params.month
}

watch(
  () => [route.params.sign, route.params.year, route.params.month],
  syncRouteToState
)

watch(
  [sign, year, month, isYearsLoaded],
  ([s, y, m]) => {
    if (!isYearsLoaded.value || routeError.value) {
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

const monthTitle = computed(() => capitalize(monthName.value))

const mainLink = computed(() => ({
  name: 'home',
}))

const todayForecastLink = computed(() => {
  const today = todayIso()
  return today ? {
    name: 'horoscope',
    params: { sign: sign.value, day: today },
  } : null
})

watch(
  () => requestedMonth.value.ok ? requestedMonth.value.params.sign : '',
  async selectedSign => {
    const localRequestId = ++yearsRequestId
    years.value = []
    isYearsLoaded.value = false
    loadedYearsSign.value = ''
    if (!selectedSign) {
      isYearsLoaded.value = true
      return
    }

    try {
      const query = new URLSearchParams({ sign: selectedSign, locale, type: forecastType })
      const response = await fetch(`/api/years?${query}`)
      if (!response.ok) throw new Error(`years status ${response.status}`)
      const payload = await response.json()
      if (localRequestId !== yearsRequestId) return
      years.value = Array.isArray(payload) ? payload.map(Number).filter(Number.isInteger) : []
    } catch (error) {
      if (localRequestId === yearsRequestId) console.error('Failed to load years list', error)
    } finally {
      if (localRequestId === yearsRequestId) {
        loadedYearsSign.value = selectedSign
        isYearsLoaded.value = true
        syncRouteToState()
      }
    }
  },
  { immediate: true }
)

watch(monthScope, async scope => {
  const localRequestId = ++monthRequestId
  availableDates.value = new Set()
  availabilityScope.value = ''
  monthError.value = ''
  isMonthLoading.value = false
  if (!requestedMonth.value.ok) return

  const { sign: selectedSign, year: selectedYear, month: selectedMonth } = requestedMonth.value.params
  isMonthLoading.value = true
  try {
    const query = new URLSearchParams({
      year: String(selectedYear), month: String(selectedMonth), sign: selectedSign,
      locale, type: forecastType,
    })
    const response = await fetch(`/api/archive/month?${query}`)
    if (!response.ok) throw new Error(`archive month status ${response.status}`)
    const payload = await response.json()
    if (!Array.isArray(payload?.days)) throw new Error('Invalid archive month response')
    if (localRequestId !== monthRequestId || scope !== monthScope.value) return
    availableDates.value = new Set(payload.days
      .filter((day: { date?: string; has_forecast?: boolean }) => typeof day?.date === 'string' && day.has_forecast === true)
      .map((day: { date: string }) => day.date))
    availabilityScope.value = scope
  } catch {
    if (localRequestId === monthRequestId && scope === monthScope.value) {
      monthError.value = 'Не удалось загрузить доступные прогнозы. Попробуйте ещё раз позже.'
    }
  } finally {
    if (localRequestId === monthRequestId && scope === monthScope.value) isMonthLoading.value = false
  }
}, { immediate: true })

onUnmounted(() => {
  ++monthRequestId
  ++yearsRequestId
})

const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const calendarDays = computed(() => {
  const firstDay = dayjs(`${year.value}-${pad2(month.value)}-01`)
  const daysInMonth = firstDay.daysInMonth()
  const today = todayIso()

  const items: {
    key: string
    number: number | null
    active: boolean
    isToday: boolean
    isWeekend: boolean
    to: RouteLocationRaw | string
  }[] = []

  const startIdx = (firstDay.day() + 6) % 7

  for (let i = 0; i < startIdx; i++) {
    items.push({
      key: `p${i}`,
      number: null,
      active: false,
      isToday: false,
      isWeekend: false,
      to: '',
    })
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const date = dayjs(`${year.value}-${pad2(month.value)}-${pad2(d)}`)
    const calendarDate = `${year.value}-${pad2(month.value)}-${pad2(d)}`
    const isToday = calendarDate === today
    const active = availabilityScope.value === `${sign.value}/${year.value}/${month.value}`
      && availableDates.value.has(calendarDate)
    const weekDay = date.day()
    const isWeekend = weekDay === 0 || weekDay === 6

    items.push({
      key: `d${d}`,
      number: d,
      active,
      isToday,
      isWeekend,
      to: {
        name: 'horoscope',
        params: { sign: sign.value, day: calendarDate },
      },
    })
  }

  return items
})
</script>