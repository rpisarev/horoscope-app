<template>
  <main class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
    <!-- top carousel -->
    <ZodiacCarousel v-model="sign" />

    <div class="flex w-full gap-4 items-center">
      <!-- left year swiper -->
      <YearSwiper v-model="year" :years="years" class="flex-none" />

     <!-- forecast in centre -->
      <article
        class="flex-1 bg-white/5 rounded-xl p-6 min-h-[160px] text-center animate-fade-in shadow">
        {{ forecastText || '— прогноз завантажується —' }}
      </article>

      <!-- right month swiper -->
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
import YearSwiper     from '../components/YearSwiper.vue'
import MonthSwiper    from '../components/MonthSwiper.vue'
import DaySlider      from '../components/DaySlider.vue'

const route  = useRoute()
const router = useRouter()

/* reactive state ************************************************************/
const sign  = ref(route.params.sign  as string ?? 'aries')
const year  = ref(Number(route.params.year)  || new Date().getFullYear())
const month = ref(Number(route.params.month) || new Date().getMonth() + 1) // 1-12
const day   = ref(Number(route.params.day)   || new Date().getDate())


const years = ref<number[]>([])
onMounted(async () => {
  try {
    const res = await fetch('/api/years')
    years.value = await res.json()
    if (years.value.length && !years.value.includes(year.value)) {
      year.value = years.value[0]
    }
  } catch (err) {
    console.error('Failed to load years list', err)
  }
})


const forecastText = ref('')

async function loadForecast () {
  const y = year.value.toString().padStart(4, '0')
  const m = month.value.toString().padStart(2, '0')
  const d = day.value.toString().padStart(2, '0')
  try {
    const res = await fetch(`/api/forecast?sign=${sign.value}&date=${y}-${m}-${d}`)
    forecastText.value = res.ok ? await res.text() : 'Не вдалося завантажити прогноз'
  } catch {
    forecastText.value = 'Помилка завантаження'
  }
}

function updateRoute () {
  router.replace({
    name: 'archive-forecast',
    params: {
      sign:  sign.value,
      year:  year.value.toString(),
      month: month.value.toString(),
      day:   day.value.toString(),
    },
  })
}

const pad = (n: number) => n.toString().padStart(2, '0')

const dateISO = computed<string>({
  get: () => `${year.value}-${pad(month.value)}-${pad(day.value)}`,   // '2025-07-14'
  set: (v: string) => {
    const [y, m, d] = v.split('-').map(Number)
    if (!Number.isNaN(y) && !Number.isNaN(m) && !Number.isNaN(d)) {
      year.value  = y
      month.value = m
      day.value   = d
    }
  },
})

watch([sign, year, month, day], () => {
  updateRoute()
  loadForecast()
}, { immediate: true })

const mainLink         = computed(() => '/')
const archiveMonthLink = computed(() =>
  `/archive/${sign.value}/${year.value}/${month.value}`)
</script>

<style scoped>
</style>

