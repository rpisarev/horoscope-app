<template>
  <section class="relative min-h-screen overflow-hidden text-slate-100">
    <!-- Page background -->
    <div class="pointer-events-none absolute inset-0 -z-30 bg-slate-950" />

    <div
      class="pointer-events-none absolute inset-0 -z-20 bg-[radial-gradient(circle_at_18%_18%,rgba(37,99,235,0.18),transparent_30%),radial-gradient(circle_at_82%_20%,rgba(251,191,36,0.12),transparent_28%),radial-gradient(circle_at_50%_58%,rgba(15,23,42,0.88),rgba(2,6,23,0.98))]"
    />

    <div
      class="pointer-events-none absolute inset-0 -z-10 opacity-60"
      style="
        background-image:
          radial-gradient(circle at 8% 18%, rgba(255,255,255,0.7) 0 1px, transparent 1.5px),
          radial-gradient(circle at 22% 35%, rgba(255,255,255,0.45) 0 1px, transparent 1.5px),
          radial-gradient(circle at 74% 16%, rgba(255,255,255,0.65) 0 1px, transparent 1.5px),
          radial-gradient(circle at 86% 42%, rgba(255,255,255,0.45) 0 1px, transparent 1.5px),
          radial-gradient(circle at 14% 72%, rgba(255,255,255,0.55) 0 1px, transparent 1.5px),
          radial-gradient(circle at 64% 80%, rgba(255,255,255,0.5) 0 1px, transparent 1.5px),
          radial-gradient(circle at 92% 82%, rgba(255,255,255,0.38) 0 1px, transparent 1.5px);
      "
    />

    <main class="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <!-- Zodiac slider -->
      <ZodiacCarousel v-model="sign" />

      <!-- Hero -->
      <section
        class="relative isolate overflow-hidden rounded-[28px] border border-amber-200/20 bg-slate-950/65 px-6 py-7 shadow-[0_20px_70px_rgba(0,0,0,0.36)] backdrop-blur-xl sm:px-8 lg:min-h-[14rem] lg:px-10"
        :data-current-sign="currentSignKey"
        :data-current-illustration="currentMeta.illustration"
        :data-current-constellation="currentMeta.constellation"
      >
        <div
          class="absolute inset-0 -z-30 bg-[linear-gradient(90deg,rgba(2,6,23,0.96)_0%,rgba(15,23,42,0.88)_42%,rgba(15,23,42,0.72)_66%,rgba(2,6,23,0.94)_100%)]"
        />

        <div
          class="absolute inset-0 -z-20 bg-[radial-gradient(circle_at_78%_42%,rgba(251,191,36,0.16),transparent_25%),radial-gradient(circle_at_24%_48%,rgba(59,130,246,0.10),transparent_35%)]"
        />

        <!-- Desktop-only constellation: Image B style, left decorative layer -->
        <Transition name="fade-soft" mode="out-in">
          <img
            v-if="currentMeta.constellation"
            :key="`hero-constellation-${currentSignKey}`"
            :src="currentMeta.constellation"
            alt=""
            aria-hidden="true"
            draggable="false"
            class="pointer-events-none absolute -left-20 top-1/2 z-0 hidden h-[28rem] w-[28rem] -translate-y-1/2 object-contain opacity-[0.34] mix-blend-screen brightness-[1.28] contrast-[1.12] lg:block"
          />
        </Transition>

        <!-- Small decorative stars on the left, desktop-safe but not image asset -->
        <div
          class="pointer-events-none absolute left-0 top-0 z-0 hidden h-full w-1/2 opacity-45 lg:block"
          style="
            background-image:
              radial-gradient(circle at 10% 18%, rgba(255,255,255,0.8) 0 1px, transparent 1.5px),
              radial-gradient(circle at 24% 27%, rgba(255,255,255,0.55) 0 1px, transparent 1.5px),
              radial-gradient(circle at 8% 55%, rgba(255,255,255,0.55) 0 1px, transparent 1.5px),
              radial-gradient(circle at 38% 72%, rgba(251,191,36,0.45) 0 1px, transparent 1.5px),
              radial-gradient(circle at 52% 44%, rgba(255,255,255,0.36) 0 1px, transparent 1.5px);
          "
        />

        <div class="relative z-10 flex items-center justify-between gap-8">
          <div class="max-w-2xl">
            <p class="mb-3 text-[0.68rem] font-semibold uppercase tracking-[0.42em] text-amber-300">
              Архивный прогноз
            </p>

            <h1 class="font-serif text-4xl leading-tight text-slate-50 sm:text-5xl">
              {{ currentMeta.name }}
              <span class="text-amber-200">·</span>
              {{ humanSelectedDate }}
            </h1>

            <p class="mt-4 max-w-xl text-sm leading-7 text-slate-300">
              Гороскоп из архива на выбранную дату. Меняйте знак, год, месяц или день,
              чтобы посмотреть другой прогноз.
            </p>
          </div>

          <!-- Desktop-only zodiac illustration: right side -->
          <div
            class="relative hidden h-44 w-44 shrink-0 overflow-visible lg:block lg:h-56 lg:w-56"
            aria-hidden="true"
          >
            <div class="absolute inset-5 rounded-full bg-amber-300/12 blur-3xl" />

            <Transition name="fade-soft" mode="out-in">
              <img
                v-if="currentMeta.illustration"
                :key="`hero-illustration-${currentSignKey}`"
                :src="currentMeta.illustration"
                :alt="currentMeta.name"
                draggable="false"
                class="relative z-20 h-full w-full object-contain drop-shadow-[0_0_34px_rgba(251,191,36,0.24)]"
              />

              <!-- Fallback only if illustration is missing -->
              <div
                v-else
                :key="`fallback-${currentSignKey}`"
                class="relative z-20 flex h-full w-full items-center justify-center"
              >
                <div
                  class="flex h-28 w-28 items-center justify-center rounded-full border border-amber-200/35 bg-slate-950/80 text-6xl text-amber-300 shadow-[0_0_32px_rgba(251,191,36,0.20)]"
                >
                  {{ currentMeta.glyph }}
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </section>

      <!-- Controls -->
      <section class="rounded-[28px] border border-slate-700/50 bg-slate-900/55 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur-xl sm:p-5">
        <div class="grid gap-4 md:grid-cols-[96px_minmax(0,1fr)_96px] md:items-stretch">
          <div class="rounded-2xl border border-slate-700/70 bg-slate-950/35 p-3">
            <p class="mb-2 text-center text-[0.62rem] font-semibold uppercase tracking-[0.32em] text-amber-300">
              Год
            </p>

            <YearSwiper v-model="year" :years="years" />
          </div>

          <div class="flex min-h-[220px] flex-col justify-between rounded-2xl border border-slate-700/70 bg-slate-950/35 p-5">
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-[0.62rem] font-semibold uppercase tracking-[0.32em] text-slate-500">
                  День
                </p>

                <h2 class="mt-1 font-serif text-2xl text-slate-50">
                  {{ humanSelectedDate }}
                </h2>
              </div>

              <span class="rounded-full border border-amber-200/20 bg-amber-200/10 px-3 py-1 text-xs text-amber-100">
                {{ dateISO }}
              </span>
            </div>

            <div class="mt-6 rounded-2xl border border-slate-700/70 bg-slate-800/50 px-4 py-5">
              <DaySlider v-model="dateISO" />
            </div>
          </div>

          <div class="rounded-2xl border border-slate-700/70 bg-slate-950/35 p-3">
            <p class="mb-2 text-center text-[0.62rem] font-semibold uppercase tracking-[0.32em] text-amber-300">
              Месяц
            </p>

            <MonthSwiper v-model="month" />
          </div>
        </div>
      </section>

      <!-- Forecast -->
      <article class="relative isolate overflow-hidden rounded-[28px] border border-amber-200/20 bg-slate-950/65 p-6 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur-xl sm:p-8">
        <div
          class="absolute inset-0 -z-20 bg-[radial-gradient(circle_at_92%_10%,rgba(59,130,246,0.08),transparent_25%),linear-gradient(180deg,rgba(15,23,42,0.88),rgba(2,6,23,0.96))]"
        />

        <div class="absolute left-6 top-6 h-12 w-px bg-gradient-to-b from-amber-300/80 to-transparent" />

        <div class="pl-5">
          <p class="mb-3 text-[0.68rem] font-semibold uppercase tracking-[0.38em] text-amber-300">
            Прогноз
          </p>

          <h2 class="font-serif text-2xl text-slate-50">
            {{ currentMeta.name }} на {{ humanSelectedDate }}
          </h2>

          <div class="mt-5 space-y-4 text-base leading-8 text-slate-200">
            <p v-if="isLoading" class="text-slate-400">
              — прогноз загружается —
            </p>

            <p v-else-if="forecastError" class="text-amber-200">
              {{ forecastError }}
            </p>

            <template v-else-if="forecastParagraphs.length">
              <p v-for="(paragraph, index) in forecastParagraphs" :key="index">
                {{ paragraph }}
              </p>
            </template>

            <p v-else class="text-slate-400">
              — прогноз пока пуст —
            </p>
          </div>
        </div>
      </article>

      <!-- Navigation -->
      <nav class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <RouterLink
          to="/"
          class="flex min-h-12 items-center justify-center rounded-2xl border border-slate-600/60 bg-slate-950/40 px-5 text-sm font-semibold text-amber-100 transition hover:border-amber-200/50 hover:bg-amber-200/10"
        >
          ← Главная
        </RouterLink>

        <RouterLink
          :to="archiveMonthLink"
          class="flex min-h-12 items-center justify-center rounded-2xl border border-amber-200/45 bg-gradient-to-r from-amber-500/80 to-amber-200/80 px-5 text-sm font-bold text-slate-950 shadow-[0_0_34px_rgba(251,191,36,0.18)] transition hover:brightness-110"
        >
          ← К месяцу
        </RouterLink>
      </nav>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'
import DaySlider from '../components/DaySlider.vue'

/* Illustrations */
import ariesIllustration from '../assets/zodiac/illustrations/aries.png'
import taurusIllustration from '../assets/zodiac/illustrations/taurus.png'
import geminiIllustration from '../assets/zodiac/illustrations/gemini.png'
import cancerIllustration from '../assets/zodiac/illustrations/cancer.png'
import leoIllustration from '../assets/zodiac/illustrations/leo.png'
import virgoIllustration from '../assets/zodiac/illustrations/virgo.png'
import libraIllustration from '../assets/zodiac/illustrations/libra.png'
import scorpioIllustration from '../assets/zodiac/illustrations/scorpio.png'
import sagittariusIllustration from '../assets/zodiac/illustrations/sagittarius.png'
import capricornIllustration from '../assets/zodiac/illustrations/capricorn.png'
import aquariusIllustration from '../assets/zodiac/illustrations/aquarius.png'
import piscesIllustration from '../assets/zodiac/illustrations/pisces.png'
import ophiuchusIllustration from '../assets/zodiac/illustrations/ophiuchus.png'

/* Constellations */
import ariesConstellation from '../assets/zodiac/constellations/aries.png'
import taurusConstellation from '../assets/zodiac/constellations/taurus.png'
import geminiConstellation from '../assets/zodiac/constellations/gemini.png'
import cancerConstellation from '../assets/zodiac/constellations/cancer.png'
import leoConstellation from '../assets/zodiac/constellations/leo.png'
import virgoConstellation from '../assets/zodiac/constellations/virgo.png'
import libraConstellation from '../assets/zodiac/constellations/libra.png'
import scorpioConstellation from '../assets/zodiac/constellations/scorpio.png'
import sagittariusConstellation from '../assets/zodiac/constellations/sagittarius.png'
import capricornConstellation from '../assets/zodiac/constellations/capricorn.png'
import aquariusConstellation from '../assets/zodiac/constellations/aquarius.png'
import piscesConstellation from '../assets/zodiac/constellations/pisces.png'
import ophiuchusConstellation from '../assets/zodiac/constellations/ophiuchus.png'

type ZodiacKey =
  | 'aries'
  | 'taurus'
  | 'gemini'
  | 'cancer'
  | 'leo'
  | 'virgo'
  | 'libra'
  | 'scorpio'
  | 'sagittarius'
  | 'capricorn'
  | 'aquarius'
  | 'pisces'
  | 'ophiuchus'

type ZodiacMeta = {
  name: string
  glyph: string
  illustration: string
  constellation: string
}

const ZODIAC_META: Record<ZodiacKey, ZodiacMeta> = {
  aries: {
    name: 'Овен',
    glyph: '♈',
    illustration: ariesIllustration,
    constellation: ariesConstellation,
  },
  taurus: {
    name: 'Телец',
    glyph: '♉',
    illustration: taurusIllustration,
    constellation: taurusConstellation,
  },
  gemini: {
    name: 'Близнецы',
    glyph: '♊',
    illustration: geminiIllustration,
    constellation: geminiConstellation,
  },
  cancer: {
    name: 'Рак',
    glyph: '♋',
    illustration: cancerIllustration,
    constellation: cancerConstellation,
  },
  leo: {
    name: 'Лев',
    glyph: '♌',
    illustration: leoIllustration,
    constellation: leoConstellation,
  },
  virgo: {
    name: 'Дева',
    glyph: '♍',
    illustration: virgoIllustration,
    constellation: virgoConstellation,
  },
  libra: {
    name: 'Весы',
    glyph: '♎',
    illustration: libraIllustration,
    constellation: libraConstellation,
  },
  scorpio: {
    name: 'Скорпион',
    glyph: '♏',
    illustration: scorpioIllustration,
    constellation: scorpioConstellation,
  },
  sagittarius: {
    name: 'Стрелец',
    glyph: '♐',
    illustration: sagittariusIllustration,
    constellation: sagittariusConstellation,
  },
  capricorn: {
    name: 'Козерог',
    glyph: '♑',
    illustration: capricornIllustration,
    constellation: capricornConstellation,
  },
  aquarius: {
    name: 'Водолей',
    glyph: '♒',
    illustration: aquariusIllustration,
    constellation: aquariusConstellation,
  },
  pisces: {
    name: 'Рыбы',
    glyph: '♓',
    illustration: piscesIllustration,
    constellation: piscesConstellation,
  },
  ophiuchus: {
    name: 'Змееносец',
    glyph: '⛎',
    illustration: ophiuchusIllustration,
    constellation: ophiuchusConstellation,
  },
}

const FALLBACK_SIGN: ZodiacKey = 'capricorn'

const route = useRoute()
const router = useRouter()

const now = new Date()

const sign = ref<string>(normalizeSign(route.params.sign))
const year = ref(parseNumberParam(route.params.year, now.getFullYear()))
const month = ref(parseNumberParam(route.params.month, now.getMonth() + 1))
const day = ref(parseNumberParam(route.params.day, now.getDate()))

const years = ref<number[]>([])
const forecastText = ref('')
const forecastError = ref('')
const isLoading = ref(false)

let requestId = 0

function toRouteString(value: unknown) {
  if (Array.isArray(value)) return String(value[0] ?? '')
  return String(value ?? '')
}

function isZodiacKey(value: string): value is ZodiacKey {
  return value in ZODIAC_META
}

function normalizeSign(value: unknown): ZodiacKey {
  const raw = toRouteString(value)
  return isZodiacKey(raw) ? raw : FALLBACK_SIGN
}

function parseNumberParam(value: unknown, fallback: number) {
  const parsed = Number(toRouteString(value))
  return Number.isFinite(parsed) ? parsed : fallback
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function daysInMonth(targetYear: number, targetMonth: number) {
  return new Date(targetYear, targetMonth, 0).getDate()
}

function formatRuDate(targetYear: number, targetMonth: number, targetDay: number) {
  const months = [
    'января',
    'февраля',
    'марта',
    'апреля',
    'мая',
    'июня',
    'июля',
    'августа',
    'сентября',
    'октября',
    'ноября',
    'декабря',
  ]

  return `${targetDay} ${months[targetMonth - 1]} ${targetYear} г.`
}

const currentSignKey = computed<ZodiacKey>(() => normalizeSign(sign.value))

const currentMeta = computed<ZodiacMeta>(() => {
  return ZODIAC_META[currentSignKey.value]
})

const dateISO = computed<string>({
  get: () => `${year.value}-${pad(month.value)}-${pad(day.value)}`,
  set: (value: string) => {
    const [nextYear, nextMonth, nextDay] = value.split('-').map(Number)

    if (
      Number.isFinite(nextYear) &&
      Number.isFinite(nextMonth) &&
      Number.isFinite(nextDay)
    ) {
      year.value = nextYear
      month.value = nextMonth
      day.value = nextDay
    }
  },
})

const humanSelectedDate = computed(() => {
  return formatRuDate(year.value, month.value, day.value)
})

const forecastParagraphs = computed(() => {
  return forecastText.value
    .split(/\n{2,}|\r?\n/)
    .map(paragraph => paragraph.trim())
    .filter(Boolean)
})

const archiveMonthLink = computed(() => ({
  name: 'archive-month',
  params: {
    sign: currentSignKey.value,
    year: String(year.value),
    month: pad(month.value),
  },
}))

function normalizeState() {
  let changed = false

  const normalizedSign = normalizeSign(sign.value)

  if (sign.value !== normalizedSign) {
    sign.value = normalizedSign
    changed = true
  }

  if (!Number.isFinite(year.value) || year.value < 1) {
    year.value = now.getFullYear()
    changed = true
  }

  if (!Number.isFinite(month.value) || month.value < 1) {
    month.value = 1
    changed = true
  }

  if (month.value > 12) {
    month.value = 12
    changed = true
  }

  const maxDay = daysInMonth(year.value, month.value)

  if (!Number.isFinite(day.value) || day.value < 1) {
    day.value = 1
    changed = true
  }

  if (day.value > maxDay) {
    day.value = maxDay
    changed = true
  }

  return changed
}

function getCurrentRouteParams() {
  return {
    sign: toRouteString(route.params.sign),
    year: toRouteString(route.params.year),
    month: toRouteString(route.params.month),
    day: toRouteString(route.params.day),
  }
}

async function replaceRouteIfNeeded() {
  const next = {
    sign: currentSignKey.value,
    year: String(year.value),
    month: pad(month.value),
    day: pad(day.value),
  }

  const current = getCurrentRouteParams()

  if (
    current.sign === next.sign &&
    current.year === next.year &&
    current.month === next.month &&
    current.day === next.day
  ) {
    return
  }

  await router.replace({
    name: 'archive-forecast',
    params: next,
  })
}

async function readForecastResponse(response: Response) {
  const contentType = response.headers.get('content-type') ?? ''

  if (contentType.includes('application/json')) {
    const payload = await response.json()

    if (typeof payload === 'string') return payload
    if (typeof payload?.text === 'string') return payload.text
    if (typeof payload?.forecast === 'string') return payload.forecast

    return ''
  }

  return response.text()
}

async function loadForecast() {
  const localRequestId = ++requestId

  isLoading.value = true
  forecastError.value = ''

  try {
    const query = new URLSearchParams({
      sign: currentSignKey.value,
      date: dateISO.value,
    })

    const response = await fetch(`/api/forecast?${query.toString()}`)

    if (!response.ok) {
      throw new Error(`forecast status ${response.status}`)
    }

    const text = await readForecastResponse(response)

    if (localRequestId !== requestId) return

    forecastText.value = text || ''
  } catch (error) {
    if (localRequestId !== requestId) return

    console.error('Failed to load archive forecast:', error)
    forecastText.value = ''
    forecastError.value = 'Не удалось загрузить прогноз'
  } finally {
    if (localRequestId === requestId) {
      isLoading.value = false
    }
  }
}

async function loadYears() {
  try {
    const response = await fetch('/api/years')

    if (!response.ok) {
      throw new Error(`years status ${response.status}`)
    }

    const payload = await response.json()

    years.value = Array.isArray(payload)
      ? payload.map(Number).filter(Number.isFinite)
      : []
  } catch (error) {
    console.error('Failed to load years:', error)
    years.value = []
  }
}

function syncFromRoute() {
  const nextSign = normalizeSign(route.params.sign)
  const nextYear = parseNumberParam(route.params.year, year.value)
  const nextMonth = parseNumberParam(route.params.month, month.value)
  const nextDay = parseNumberParam(route.params.day, day.value)

  if (sign.value !== nextSign) sign.value = nextSign
  if (year.value !== nextYear) year.value = nextYear
  if (month.value !== nextMonth) month.value = nextMonth
  if (day.value !== nextDay) day.value = nextDay
}

watch(
  () => route.fullPath,
  () => {
    syncFromRoute()
  }
)

watch(
  [sign, year, month, day],
  async () => {
    if (normalizeState()) return

    await replaceRouteIfNeeded()
    await loadForecast()
  },
  { immediate: true }
)

onMounted(() => {
  void loadYears()
})
</script>

<style scoped>
.fade-soft-enter-active,
.fade-soft-leave-active {
  transition:
    opacity 240ms ease,
    transform 240ms ease,
    filter 240ms ease;
}

.fade-soft-enter-from,
.fade-soft-leave-to {
  opacity: 0;
  transform: scale(0.975);
  filter: blur(5px);
}
</style>