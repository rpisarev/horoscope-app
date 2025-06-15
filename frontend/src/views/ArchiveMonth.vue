<template>
  <main class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
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
              :to="day.href"
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
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import dayjs from 'dayjs'

import DaySlider from '../components/DaySlider.vue'
import YearSwiper from '../components/YearSwiper.vue'
import MonthSwiper from '../components/MonthSwiper.vue'

const route = useRoute()
const router = useRouter()
const isForecastDisabled = ref(true)

const sign = ref(route.params.sign as string)

const year  = ref(Number(route.params.year)  || dayjs().year())
const month = ref(Number(route.params.month) || dayjs().month() + 1)


watch([sign, year, month], ([s, y, m]) => {
  router.replace({
    name: 'ArchiveMonth',
    params: {
      sign: s,
      year: y,
      month: String(m).padStart(2, '0'),
    },
  })
})

const forecastText = 'Some static forecast no API calls yet'

const archiveLink = computed(() => `/archive/${sign.value}/${day.value.slice(0,4)}/${day.value.slice(5,7)}`)
const mainLink = computed(() => '/')
const monthName = computed(() => {
  const dt = new Date(year.value, month.value - 1, 1)
  return new Intl.DateTimeFormat('ru', { month: 'long' }).format(dt)
})

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

const weekDays = ['Пн','Вт','Ср','Чт','Пт','Сб','Нд']

const calendarDays = computed(() => {
  const firstDay = dayjs(`${year.value}-${String(month.value).padStart(2, '0')}-01`)
  const daysInMonth = firstDay.daysInMonth()
  const today = dayjs()
  const items: { key:string, number:number, active:boolean, href:string }[] = []

  // add empty slots before the first weekday so the grid aligns
  const startIdx = (firstDay.day() + 6) % 7 // convert Sunday-based (0) to Monday-based (0)
  for (let i = 0; i < startIdx; i++) {
    items.push({ key:`p${i}`, number:0, active:false, href:'' })
  }

  // add real days
  for (let d = 1; d <= daysInMonth; d++) {
    const date = dayjs(`${year.value}-${String(month.value).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
    const future = date.isAfter(today, 'day')
    const sameDay = date.isSame(today, 'day')
    const active = !future && !sameDay // allow past days only

    items.push({
      key:`d${d}`,
      number:d,
      active,
      href:`/archive/${sign.value}/${year.value}/${month.value}/${String(d).padStart(2, '0')}`
    })
  }

  return items
})

</script>
