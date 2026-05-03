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

    <div class="relative z-10 mx-auto flex max-w-6xl flex-col gap-8">
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
              Ежедневный прогноз
            </p>

            <h1 class="font-merienda text-4xl leading-tight text-white md:text-5xl">
              {{ zodiacName }} · {{ formattedDate }}
            </h1>

            <p class="mt-4 max-w-2xl font-lato text-base leading-7 text-white/70">
              Выберите знак и день, чтобы прочитать персональный гороскоп.
              Для прошлых дат можно перейти в архив месяца.
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
        <div
          class="rounded-3xl border border-amber-200/15 bg-slate-950/35
          p-5 shadow-inner shadow-white/5"
        >
          <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p class="font-lato text-[11px] font-bold uppercase tracking-[0.28em] text-white/40">
                День
              </p>

              <p class="mt-1 font-merienda text-2xl text-amber-100">
                {{ dayCaption }}
              </p>
            </div>

            <div
              class="rounded-full border border-amber-300/25 bg-amber-300/10
              px-4 py-2 font-lato text-sm text-amber-100"
            >
              {{ day }}
            </div>
          </div>

          <div
            class="flex min-h-[7.5rem] items-center rounded-2xl border border-white/10
            bg-white/[0.04] px-4 py-6"
          >
            <DaySlider v-model="day" />
          </div>
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
            class="space-y-5 font-lato text-lg leading-8 text-white/80"
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

      <nav class="grid gap-4 md:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
        <RouterLink
          :to="mainLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/25
          bg-slate-950/45 px-6 font-lato text-base font-semibold text-amber-100
          shadow-lg shadow-black/20 transition hover:-translate-y-0.5 hover:border-amber-200/50
          hover:bg-white/10"
        >
          ← Главная
        </RouterLink>

        <RouterLink
          :to="archiveLink"
          class="inline-flex min-h-14 items-center justify-center rounded-2xl border border-amber-200/55
          bg-amber-300/85 px-6 font-lato text-base font-bold text-slate-950
          shadow-[0_0_28px_rgba(251,191,36,0.25)] transition hover:-translate-y-0.5
          hover:bg-amber-200"
        >
          Открыть архив месяца →
        </RouterLink>
      </nav>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import dayjs from 'dayjs'
import 'dayjs/locale/ru'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import DaySlider from '../components/DaySlider.vue'
import NotFound from './NotFound.vue'
import {
  routeParamToString,
  validateHoroscopeRoute,
} from '../utils/routeValidation'
import {
  getZodiacByKey,
  todayIso,
  isoAddDays,
} from '../constants/zodiac'

const route = useRoute()
const router = useRouter()

const routeValidation = computed(() => validateHoroscopeRoute(route.params))

const routeError = computed(() => (
  routeValidation.value.ok ? null : routeValidation.value
))

function getRouteSign() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.sign
  }

  return routeParamToString(route.params.sign) || 'capricorn'
}

function getRouteDay() {
  if (routeValidation.value.ok) {
    return routeValidation.value.params.day
  }

  return routeParamToString(route.params.day) || todayIso()
}

const sign = ref(getRouteSign())
const day = ref(getRouteDay())
const forecastText = ref('')
const isLoading = ref(false)
const errorText = ref('')

const zodiac = computed(() => getZodiacByKey(sign.value))

const zodiacName = computed(() => zodiac.value?.nameRu ?? sign.value)

const zodiacGlyph = computed(() => zodiac.value?.glyph ?? '✦')

const formattedDate = computed(() =>
  dayjs(day.value)
    .locale('ru')
    .format('D MMMM YYYY')
)

const dayCaption = computed(() => {
  const today = todayIso()

  if (day.value === today) {
    return `Сегодня — ${formattedDate.value}`
  }

  if (day.value === isoAddDays(today, -1)) {
    return `Вчера — ${formattedDate.value}`
  }

  if (day.value === isoAddDays(today, 1)) {
    return `Завтра — ${formattedDate.value}`
  }

  return formattedDate.value
})

const forecastParagraphs = computed(() =>
  forecastText.value
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
)

watch(
  () => [route.params.sign, route.params.day],
  () => {
    if (routeError.value) {
      forecastText.value = ''
      errorText.value = ''
      isLoading.value = false
      return
    }

    sign.value = getRouteSign()
    day.value = getRouteDay()
  }
)

async function loadForecast() {
  if (routeError.value || !routeValidation.value.ok) {
    forecastText.value = ''
    errorText.value = ''
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorText.value = ''

  const { sign: routeSign, day: routeDay } = routeValidation.value.params

  try {
    const res = await fetch(`/api/forecast?sign=${routeSign}&date=${routeDay}`)

    if (!res.ok) {
      errorText.value = 'Не удалось загрузить прогноз'
      forecastText.value = ''
      return
    }

    const data = await res.json()
    forecastText.value = data.text ?? 'Порожний прогноз'
  } catch (err) {
    errorText.value = 'Ошибка загрузки'
    forecastText.value = ''

    console.error('Failed to load forecast', err)
  } finally {
    isLoading.value = false
  }
}

watch(
  [sign, day],
  async ([nextSign, nextDay]) => {
    if (routeError.value) {
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