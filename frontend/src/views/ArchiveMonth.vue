<template>
  <NotFound v-if="routeError" :title="text.routeErrors[routeError.code]" />

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
          {{ text.loadingArchive }}
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
              {{ text.archive }}
            </p>

            <h1 class="font-merienda text-4xl leading-tight text-white md:text-5xl">
              {{ text.archiveTitle }}
            </h1>

            <p class="mt-3 font-merienda text-2xl text-amber-200">
              {{ zodiacName }} · {{ monthTitle }} {{ year }}
            </p>

            <p class="mt-4 max-w-2xl font-lato text-base leading-7 text-white/70">
              {{ text.archiveIntro(zodiacNameGenitive) }}
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
              {{ text.year }}
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
                {{ text.calendar }}
              </p>

              <h2 class="mt-2 font-merienda text-3xl text-amber-100">
                {{ monthTitle }} {{ year }}
              </h2>
            </div>

            <div class="grid grid-cols-7 gap-2" :aria-label="text.calendar" :aria-busy="!selectedAvailability">
              <div
                v-for="(d, index) in weekDays"
                :key="d"
                class="pb-2 text-center font-lato text-xs font-bold uppercase tracking-[0.18em]"
                :class="index >= 5 ? 'text-amber-300/80' : 'text-white/45'"
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
                  :aria-current="day.isToday ? 'date' : undefined"
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
                    class="absolute bottom-1 flex justify-center font-lato text-[9px] font-bold uppercase tracking-[0.12em] text-amber-300/80"
                  >
                    <span class="sr-only sm:not-sr-only">{{ text.today }}</span>
                    <span aria-hidden="true" class="h-0.5 w-2 rounded-full bg-amber-300 sm:hidden" />
                  </span>
                </span>
              </template>
            </div>

            <div
              class="mt-6 rounded-2xl border border-white/10 bg-white/[0.04]
              px-4 py-3 font-lato text-sm leading-6 text-white/65"
            >
              <span class="mr-2 text-amber-300">ⓘ</span>
              <span v-if="!selectedAvailability" role="status">{{ text.loadingAvailability }}</span>
              <span v-else-if="selectedAvailability.status === 'error'" role="alert">
                {{ text.availabilityError }}
              </span>
              <span v-else-if="hasPublishedDay" role="status">
                {{ text.selectDate(zodiacNameGenitive) }}
              </span>
              <span v-else role="status">
                {{ text.emptyMonth(monthName, year, zodiacNameGenitive) }}
                {{ years.length > 1 ? text.chooseMonthYear : text.chooseMonth }}
              </span>
            </div>

          </section>

          <aside
            class="rounded-3xl border border-white/10 bg-slate-950/35 px-4 py-5
            shadow-inner shadow-white/5"
          >
            <p class="mb-4 text-center font-lato text-xs font-bold uppercase tracking-[0.3em] text-amber-300">
              {{ text.month }}
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
          ← {{ text.home }}
        </router-link>

        <router-link
          v-if="todayForecastLink"
          :to="todayForecastLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/55
          bg-amber-300/85 px-6 font-lato text-base font-bold text-slate-950
          shadow-[0_0_28px_rgba(251,191,36,0.25)] transition hover:-translate-y-0.5
          hover:bg-amber-200"
        >
          {{ text.openToday }} →
        </router-link>
      </nav>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { getArchiveYears, getArchiveMonthAvailability } from '../api/archive'
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
import { todayIso, getZodiacByKey, zodiacName as localizedName } from '../constants/zodiac'
import { useUiText } from '../utils/uiText'
import { localeQuery } from '../utils/locale'

const route = useRoute()
const router = useRouter()

const years = ref<number[]>([])
const isYearsLoaded = ref(false)
const loadedYearsScope = ref('')
const monthAvailability = ref<
  | { scope: string; status: 'ready'; dates: ReadonlySet<string> }
  | { scope: string; status: 'error' }
>()
const { locale, text } = useUiText()
const forecastType = 'daily'
let monthRequestId = 0
let yearsRequestId = 0

const requestedMonth = computed(() => validateArchiveMonthRoute(route.params))
const monthScope = computed(() => {
  if (!requestedMonth.value.ok) return ''
  const { sign, year, month } = requestedMonth.value.params
  return `${locale.value}/${sign}/${year}/${month}`
})

const requestedSign = computed(() => requestedMonth.value.ok ? requestedMonth.value.params.sign : '')
const yearsScope = computed(() => `${locale.value}/${requestedSign.value}`)

const routeValidation = computed(() => validateArchiveMonthRoute(
  route.params,
  years.value,
  isYearsLoaded.value && loadedYearsScope.value === yearsScope.value
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

const selectedAvailability = computed(() => (
  monthAvailability.value?.scope === `${locale.value}/${sign.value}/${year.value}/${month.value}`
    ? monthAvailability.value
    : undefined
))

const currentZodiac = computed(() => getZodiacByKey(sign.value))
const zodiacName = computed(() => currentZodiac.value ? localizedName(currentZodiac.value, locale.value) : '')
const zodiacNameGenitive = computed(() => currentZodiac.value ? localizedName(currentZodiac.value, locale.value, true) : '')
const zodiacGlyph = computed(() => currentZodiac.value?.glyph ?? '✦')

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
    const nextYear = String(y).padStart(4, '0')
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
      query: { ...route.query, ...localeQuery(locale.value) },
      hash: route.hash,
      params: {
        sign: nextSign,
        year: nextYear,
        month: nextMonth,
      },
    })
  },
  { immediate: true }
)

const yearMonthIso = computed(() => `${String(year.value).padStart(4, '0')}-${pad2(month.value)}`)
const firstOfMonth = computed(() => new Date(`${yearMonthIso.value}-01T00:00:00Z`))
const monthName = computed(() => firstOfMonth.value.toLocaleDateString(locale.value, { month: 'long', timeZone: 'UTC' }))

const monthTitle = computed(() => capitalize(monthName.value))

const mainLink = computed(() => ({
  name: 'home',
  query: localeQuery(locale.value),
}))

const todayForecastLink = computed(() => {
  const today = todayIso()
  return today ? {
    name: 'horoscope',
    query: localeQuery(locale.value),
    params: { sign: sign.value, day: today },
  } : null
})

watch(
  [requestedSign, locale],
  async ([selectedSign, language]) => {
    const scope = yearsScope.value
    const localRequestId = ++yearsRequestId
    years.value = []
    isYearsLoaded.value = false
    loadedYearsScope.value = ''
    if (!selectedSign) {
      isYearsLoaded.value = true
      return
    }

    try {
      const loadedYears = await getArchiveYears({ sign: selectedSign, locale: language, type: forecastType })
      if (localRequestId !== yearsRequestId || scope !== yearsScope.value) return
      years.value = loadedYears
    } catch (error) {
      if (localRequestId === yearsRequestId && scope === yearsScope.value) console.error('Failed to load years list', error)
    } finally {
      if (localRequestId === yearsRequestId && scope === yearsScope.value) {
        loadedYearsScope.value = scope
        isYearsLoaded.value = true
        syncRouteToState()
      }
    }
  },
  { immediate: true }
)

watch(monthScope, async scope => {
  const localRequestId = ++monthRequestId
  monthAvailability.value = undefined
  if (!requestedMonth.value.ok) return

  const { sign: selectedSign, year: selectedYear, month: selectedMonth } = requestedMonth.value.params
  try {
    const dates = await getArchiveMonthAvailability({
      year: selectedYear, month: selectedMonth, sign: selectedSign,
      locale: locale.value, type: forecastType,
    })
    if (localRequestId !== monthRequestId || scope !== monthScope.value) return
    monthAvailability.value = { scope, status: 'ready', dates }
  } catch {
    if (localRequestId === monthRequestId && scope === monthScope.value) {
      monthAvailability.value = { scope, status: 'error' }
    }
  }
}, { immediate: true })

onUnmounted(() => {
  ++monthRequestId
  ++yearsRequestId
})

const weekDays = computed(() => {
  const formatter = new Intl.DateTimeFormat(locale.value, { weekday: 'short', timeZone: 'UTC' })
  // The archive lays out a Monday-first week in all three languages.
  return Array.from({ length: 7 }, (_, i) => formatter.format(new Date(Date.UTC(2024, 0, i + 1))))
})

const calendarDays = computed(() => {
  const firstWeekday = firstOfMonth.value.getUTCDay()
  const lastOfMonth = new Date(firstOfMonth.value)
  lastOfMonth.setUTCMonth(lastOfMonth.getUTCMonth() + 1, 0)
  const daysInMonth = lastOfMonth.getUTCDate()
  const today = todayIso()

  const items: {
    key: string
    number: number | null
    active: boolean
    isToday: boolean
    isWeekend: boolean
    to: RouteLocationRaw | string
  }[] = []

  const startIdx = (firstWeekday + 6) % 7

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
    const calendarDate = `${yearMonthIso.value}-${pad2(d)}`
    const isToday = calendarDate === today
    const active = selectedAvailability.value?.status === 'ready'
      && selectedAvailability.value.dates.has(calendarDate)
    const weekDay = (firstWeekday + d - 1) % 7
    const isWeekend = weekDay === 0 || weekDay === 6

    items.push({
      key: `d${d}`,
      number: d,
      active,
      isToday,
      isWeekend,
      to: {
        name: 'horoscope',
        query: localeQuery(locale.value),
        params: { sign: sign.value, day: calendarDate },
      },
    })
  }

  return items
})

const hasPublishedDay = computed(() => calendarDays.value.some(day => day.active))
</script>
