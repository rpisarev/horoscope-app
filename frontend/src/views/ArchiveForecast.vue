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
          <div class="absolute left-1/4 top-12 h-44 w-44 rounded-full bg-sky-300/10 blur-3xl" />
          <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-amber-200/50 to-transparent" />
        </div>

        <div class="relative grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p class="mb-3 font-lato text-xs font-bold uppercase tracking-[0.35em] text-amber-300">
              Архивный прогноз
            </p>

            <h1 class="font-merienda text-4xl leading-tight text-white md:text-5xl">
              {{ zodiacName }} · {{ formattedDate }}
            </h1>

            <p class="mt-4 max-w-2xl font-lato text-base leading-7 text-white/70">
              Гороскоп из архива на выбранную дату. Меняйте год, месяц или день,
              чтобы посмотреть другой прогноз.
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
        p-4 shadow-2xl shadow-black/25 backdrop-blur md:p-5"
      >
        <div class="grid gap-4 lg:grid-cols-[120px_120px_minmax(0,1fr)] lg:items-start">
          <aside
            class="self-start rounded-3xl border border-white/10 bg-slate-950/35 px-3 py-4
            shadow-inner shadow-white/5"
          >
            <p class="mb-3 text-center font-lato text-[11px] font-bold uppercase tracking-[0.28em] text-amber-300">
              Год
            </p>

            <YearSwiper
              v-model="year"
              :years="years"
              class="archive-compact-picker mx-auto"
            />
          </aside>

          <aside
            class="self-start rounded-3xl border border-white/10 bg-slate-950/35 px-3 py-4
            shadow-inner shadow-white/5"
          >
            <p class="mb-3 text-center font-lato text-[11px] font-bold uppercase tracking-[0.28em] text-amber-300">
              Месяц
            </p>

            <MonthSwiper
              v-model="month"
              class="archive-compact-picker mx-auto"
            />
          </aside>

          <section
            class="self-stretch flex min-h-[15.5rem] flex-col rounded-3xl border border-amber-200/15
            bg-slate-950/35 p-5 shadow-inner shadow-white/5 md:min-h-[16.5rem]"
          >
            <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="font-lato text-[11px] font-bold uppercase tracking-[0.28em] text-white/40">
                  День
                </p>

                <p class="mt-1 font-merienda text-2xl text-amber-100">
                  {{ formattedDate }}
                </p>
              </div>

              <div
                class="rounded-full border border-amber-300/25 bg-amber-300/10
                px-4 py-2 font-lato text-sm text-amber-100"
              >
                {{ dateISO }}
              </div>
            </div>

            <div
              class="mt-auto flex min-h-[7.5rem] items-center rounded-2xl border border-white/10
              bg-white/[0.04] px-4 py-6"
            >
              <DaySlider v-model="dateISO" />
            </div>
          </section>
        </div>
      </section>

      <article
        class="relative overflow-hidden rounded-[2rem] border border-amber-200/25
        bg-slate-950/60 p-6 shadow-2xl shadow-black/30 backdrop-blur md:p-8"
      >
        <div
          class="pointer-events-none absolute inset-0"
          aria-hidden="true"
        >
          <div class="absolute -left-16 top-12 h-48 w-48 rounded-full bg-amber-300/10 blur-3xl" />
          <div class="absolute bottom-0 right-0 h-px w-full bg-gradient-to-r from-transparent via-amber-200/40 to-transparent" />
        </div>

        <div class="relative">
          <div class="mb-6 border-l border-amber-300/45 pl-5">
            <p class="font-lato text-xs font-bold uppercase tracking-[0.32em] text-amber-300">
              Прогноз
            </p>

            <h2 class="mt-2 font-merienda text-3xl text-white">
              {{ zodiacName }} на {{ formattedDate }}
            </h2>
          </div>

          <div
            v-if="isLoading"
            class="rounded-3xl border border-white/10 bg-white/[0.04] px-5 py-8 text-center font-lato text-white/70"
          >
            Загрузка прогноза...
          </div>

          <div
            v-else-if="errorText"
            class="rounded-3xl border border-red-300/20 bg-red-300/10 px-5 py-8 text-center font-lato text-red-100"
          >
            {{ errorText }}
          </div>

          <div
            v-else-if="!forecastText"
            class="rounded-3xl border border-white/10 bg-white/[0.04] px-5 py-8 text-center font-lato text-white/60"
          >
            Прогноз пока пуст
          </div>

          <div
            v-else
            class="space-y-5 font-lato text-lg leading-8 text-white/82"
          >
            <p
              v-for="paragraph in forecastParagraphs"
              :key="paragraph"
              class="whitespace-pre-line"
            >
              {{ paragraph }}
            </p>
          </div>
        </div>
      </article>

      <nav class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,280px)]">
        <RouterLink
          :to="archiveMonthLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/25
          bg-slate-950/45 px-6 font-lato text-base font-semibold text-amber-100
          shadow-lg shadow-black/20 transition hover:-translate-y-0.5 hover:border-amber-200/50
          hover:bg-white/10"
        >
          ← К месяцу
        </RouterLink>

        <RouterLink
          :to="mainLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/55
          bg-amber-300/85 px-6 font-lato text-base font-bold text-slate-950
          shadow-[0_0_28px_rgba(251,191,36,0.25)] transition hover:-translate-y-0.5
          hover:bg-amber-200"
        >
          На главную
        </RouterLink>
      </nav>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import dayjs from 'dayjs'
import 'dayjs/locale/ru'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'
import DaySlider from '../components/DaySlider.vue'
import NotFound from './NotFound.vue'
import {
  clampArchiveDay,
  pad2,
  parseArchiveDayParam,
  parseMonthParam,
  parseYearParam,
  routeParamToString,
  validateArchiveForecastRoute,
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

const routeValidation = computed(() => validateArchiveForecastRoute(
  route.params,
  years.value,
  isYearsLoaded.value
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

  return parseYearParam(route.params.year) ?? fallbackYear
}

function getRouteMonth() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.month
  }

  return parseMonthParam(route.params.month) ?? fallbackMonth
}

function getRouteDay() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.day
  }

  return parseArchiveDayParam(route.params.day) ?? fallbackDay
}

const sign = ref(getRouteSign())
const year = ref(getRouteYear())
const month = ref(getRouteMonth())
const day = ref(getRouteDay())

const currentZodiacMeta = computed(() => zodiacMeta[sign.value])

const zodiacName = computed(() => currentZodiacMeta.value?.name ?? sign.value)

const zodiacGlyph = computed(() => currentZodiacMeta.value?.glyph ?? '✦')

const pad = pad2

const formattedDate = computed(() =>
  dayjs(`${year.value}-${pad(month.value)}-${pad(day.value)}`)
    .locale('ru')
    .format('D MMMM YYYY')
)

const forecastParagraphs = computed(() =>
  forecastText.value
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
)

function syncRouteToState() {
  if (!isYearsLoaded.value || routeError.value || !routeValidation.value.ok) {
    return
  }

  sign.value = routeValidation.value.params.sign
  year.value = routeValidation.value.params.year
  month.value = routeValidation.value.params.month
  day.value = routeValidation.value.params.day
}

watch(
  () => [route.params.sign, route.params.year, route.params.month, route.params.day],
  syncRouteToState
)

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
  if (!isYearsLoaded.value || routeError.value || !routeValidation.value.ok) {
    forecastText.value = ''
    errorText.value = ''
    isLoading.value = false
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
    if (!isYearsLoaded.value || routeError.value) {
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

    const nextSignStr = String(nextSign)
    const nextYearStr = String(nextYear)
    const nextMonthStr = pad(nextMonth)
    const nextDayStr = pad(nextDay)

    if (
      routeSign !== nextSignStr ||
      routeYear !== nextYearStr ||
      routeMonth !== nextMonthStr ||
      routeDay !== nextDayStr
    ) {
      await router.replace({
        name: 'archive-forecast',
        params: {
          sign: nextSignStr,
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
.archive-compact-picker {
  align-self: start;
}

.archive-compact-picker :deep(.swiper) {
  height: 9.5rem !important;
}

@media (min-width: 768px) {
  .archive-compact-picker :deep(.swiper) {
    height: 10.5rem !important;
  }
}
</style>