<template>
  <main class="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
    <ZodiacCarousel v-model="sign" />
    <DaySlider v-model="day" />

    <article class="bg-white/5 rounded-xl p-6 min-h-[160px] animate-fade-in shadow">
      {{ forecastText }}
    </article>
    <div class="flex justify-between items-center">
      <RouterLink :to="mainLink" class="underline">Главная</RouterLink>
      <RouterLink :to="archiveLink" class="underline">Архив</RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ZodiacCarousel from '../components/ZodiacCarousel.vue'
import DaySlider from '../components/DaySlider.vue'

const route = useRoute()
const router = useRouter()
const isForecastDisabled = ref(true)

const sign = ref(route.params.sign as string)
const day = ref(route.params.day as string)

watch([sign, day], ([s,d]) => {
  router.replace({ name:'horoscope', params:{ sign:s, day:d }})
})

const forecastText = 'Some static forecast no API calls yet'

const archiveLink = computed(() => `/archive/${sign.value}/${day.value.slice(0,4)}/${day.value.slice(5,7)}`)
const mainLink = computed(() => '/')
</script>
