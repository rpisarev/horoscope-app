<template>
  <NotFound
    v-if="routeError"
    :title="routeError.message"
    description="Проверьте знак зодиака или дату в адресе страницы."
  />

  <section v-else class="relative min-h-screen overflow-hidden text-slate-100">
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
        :data-current-illustration="currentAssets.illustration"
        :data-current-constellation="currentAssets.constellation"
      >
        <div
          class="absolute inset-0 -z-30 bg-[linear-gradient(90deg,rgba(2,6,23,0.96)_0%,rgba(15,23,42,0.88)_42%,rgba(15,23,42,0.72)_66%,rgba(2,6,23,0.94)_100%)]"
        />
        <div
          class="absolute inset-0 -z-20 bg-[radial-gradient(circle_at_78%_42%,rgba(251,191,36,0.16),transparent_25%),radial-gradient(circle_at_24%_48%,rgba(59,130,246,0.10),transparent_35%)]"
        />

        <!-- Desktop-only constellation: left decorative layer -->
        <Transition name="fade-soft" mode="out-in">
          <img
            v-if="currentAssets.constellation"
            :key="`hero-constellation-${currentSignKey}`"
            :src="currentAssets.constellation"
            alt=""
            aria-hidden="true"
            draggable="false"
            class="pointer-events-none absolute -left-20 top-1/2 z-0 hidden h-[28rem] w-[28rem] -translate-y-1/2 object-contain opacity-[0.34] mix-blend-screen brightness-[1.28] contrast-[1.12] lg:block"
          />
        </Transition>

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
              Ежедневный прогноз
            </p>

            <h1 class="font-serif text-4xl leading-tight text-slate-50 sm:text-5xl">
              {{ currentZodiac.nameRu }}
              <span class="text-amber-200">·</span>
              {{ humanSelectedDate }}
            </h1>

            <p class="mt-4 max-w-xl text-sm leading-7 text-slate-300">
              Выберите знак и день, чтобы прочитать персональный гороскоп.
              Для прошлых дат можно перейти в архив месяца.
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
                v-if="currentAssets.illustration"
                :key="`hero-illustration-${currentSignKey}`"
                :src="currentAssets.illustration"
                :alt="currentZodiac.nameRu"
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
                  {{ currentZodiac.glyph }}
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </section>

      <!-- Day controls -->
      <section class="rounded-[28px] border border-slate-700/50 bg-slate-900/55 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur-xl sm:p-5">
        <div class="rounded-2xl border border-slate-700/70 bg-slate-950/35 p-5">
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
              {{ day }}
            </span>
          </div>

          <div class="mt-6 rounded-2xl border border-slate-700/70 bg-slate-800/50 px-4 py-5">
            <DaySlider v-model="day" />
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
            {{ currentZodiac.nameRu }} на {{ humanSelectedDate }}
          </h2>

          <div class="mt-5 space-y-4 text-base leading-8 text-slate-200">
            <p v-if="isLoading" class="text-slate-400">
              — прогноз загружается —
            </p>

            <p v-else-if="errorText" class="text-amber-200">
              {{ errorText }}
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
          :to="mainLink"
          class="flex min-h-12 items-center justify-center rounded-2xl border border-slate-600/60 bg-slate-950/40 px-5 text-sm font-semibold text-amber-100 transition hover:border-amber-200/50 hover:bg-amber-200/10"
        >
          ← Главная
        </RouterLink>

        <RouterLink
          :to="archiveLink"
          class="flex min-h-12 items-center justify-center rounded-2xl border border-amber-200/45 bg-gradient-to-r from-amber-500/80 to-amber-200/80 px-5 text-sm font-bold text-slate-950 shadow-[0_0_34px_rgba(251,191,36,0.18)] transition hover:brightness-110"
        >
          Открыть архив месяца →
        </RouterLink>
      </nav>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import DaySlider from '../components/DaySlider.vue'
import NotFound from './NotFound.vue'
import {
  getZodiacByKey,
  prettifyDate,
  ZODIACS,
} from '../constants/zodiac'
import {
  routeParamToString,
  validateHoroscopeRoute,
} from '../utils/routeValidation'

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

type ZodiacAssets = {
  illustration: string
  constellation: string
}

const ZODIAC_ASSETS: Record<ZodiacKey, ZodiacAssets> = {
  aries: {
    illustration: ariesIllustration,
    constellation: ariesConstellation,
  },
  taurus: {
    illustration: taurusIllustration,
    constellation: taurusConstellation,
  },
  gemini: {
    illustration: geminiIllustration,
    constellation: geminiConstellation,
  },
  cancer: {
    illustration: cancerIllustration,
    constellation: cancerConstellation,
  },
  leo: {
    illustration: leoIllustration,
    constellation: leoConstellation,
  },
  virgo: {
    illustration: virgoIllustration,
    constellation: virgoConstellation,
  },
  libra: {
    illustration: libraIllustration,
    constellation: libraConstellation,
  },
  scorpio: {
    illustration: scorpioIllustration,
    constellation: scorpioConstellation,
  },
  sagittarius: {
    illustration: sagittariusIllustration,
    constellation: sagittariusConstellation,
  },
  capricorn: {
    illustration: capricornIllustration,
    constellation: capricornConstellation,
  },
  aquarius: {
    illustration: aquariusIllustration,
    constellation: aquariusConstellation,
  },
  pisces: {
    illustration: piscesIllustration,
    constellation: piscesConstellation,
  },
  ophiuchus: {
    illustration: ophiuchusIllustration,
    constellation: ophiuchusConstellation,
  },
}

const FALLBACK_SIGN: ZodiacKey = 'capricorn'
const FALLBACK_DAY = new Date().toISOString().slice(0, 10)

const route = useRoute()
const router = useRouter()

const initialRouteValidation = validateHoroscopeRoute(route.params)

const routeValidation = computed(() => validateHoroscopeRoute(route.params))
const routeError = computed(() => {
  return routeValidation.value.ok ? null : routeValidation.value
})

const sign = ref(initialRouteValidation.ok ? initialRouteValidation.params.sign : FALLBACK_SIGN)
const day = ref(initialRouteValidation.ok ? initialRouteValidation.params.day : FALLBACK_DAY)

const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

let requestId = 0

function isZodiacKey(value: string): value is ZodiacKey {
  return value in ZODIAC_ASSETS
}

function normalizeSign(value: string): ZodiacKey {
  return isZodiacKey(value) ? value : FALLBACK_SIGN
}

function resetForecastState() {
  forecastText.value = ''
  errorText.value = ''
  isLoading.value = false
}

const currentSignKey = computed<ZodiacKey>(() => {
  return normalizeSign(sign.value)
})

const currentZodiac = computed(() => {
  return getZodiacByKey(currentSignKey.value) ?? ZODIACS[0]
})

const currentAssets = computed(() => {
  return ZODIAC_ASSETS[currentSignKey.value]
})

const humanSelectedDate = computed(() => {
  return prettifyDate(day.value)
})

const forecastParagraphs = computed(() => {
  return forecastText.value
    .split(/\n{2,}|\r?\n/)
    .map(paragraph => paragraph.trim())
    .filter(Boolean)
})

const archiveLink = computed(() => ({
  name: 'archive-month',
  params: {
    sign: currentSignKey.value,
    year: day.value.slice(0, 4),
    month: day.value.slice(5, 7),
  },
}))

const mainLink = computed(() => ({
  name: 'home',
}))

function syncFromRoute() {
  const validation = validateHoroscopeRoute(route.params)

  if (!validation.ok) {
    resetForecastState()
    return
  }

  sign.value = validation.params.sign
  day.value = validation.params.day
}

async function replaceRouteIfNeeded() {
  const validation = validateHoroscopeRoute({
    sign: sign.value,
    day: day.value,
  })

  if (!validation.ok) {
    return
  }

  const currentSign = routeParamToString(route.params.sign)
  const currentDay = routeParamToString(route.params.day)

  if (currentSign === validation.params.sign && currentDay === validation.params.day) {
    return
  }

  await router.replace({
    name: 'horoscope',
    params: {
      sign: validation.params.sign,
      day: validation.params.day,
    },
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
  if (routeError.value) {
    resetForecastState()
    return
  }

  const validation = validateHoroscopeRoute({
    sign: sign.value,
    day: day.value,
  })

  if (!validation.ok) {
    resetForecastState()
    return
  }

  const localRequestId = ++requestId

  isLoading.value = true
  errorText.value = ''

  try {
    const query = new URLSearchParams({
      sign: validation.params.sign,
      date: validation.params.day,
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

    console.error('Failed to load forecast', error)

    forecastText.value = ''
    errorText.value = 'Не удалось загрузить прогноз'
  } finally {
    if (localRequestId === requestId) {
      isLoading.value = false
    }
  }
}

watch(
  () => [route.params.sign, route.params.day],
  () => {
    syncFromRoute()
  }
)

watch(
  [sign, day],
  async () => {
    if (routeError.value) {
      resetForecastState()
      return
    }

    const validation = validateHoroscopeRoute({
      sign: sign.value,
      day: day.value,
    })

    if (!validation.ok) {
      resetForecastState()
      return
    }

    await replaceRouteIfNeeded()
    await loadForecast()
  },
  { immediate: true }
)
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