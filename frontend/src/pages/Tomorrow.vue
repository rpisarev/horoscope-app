<script setup>
import { ref, onMounted } from 'vue'
import { useForecastStore } from '../store'
import ForecastCard from '../components/ForecastCard.vue'
import SignSelector from '../components/SignSelector.vue'

const store = useForecastStore()
const sign = ref('aries')
const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0,10)
const forecast = ref(null)

async function load() {
  forecast.value = await store.fetchForecast(sign.value, tomorrow)
}

onMounted(load)
</script>

<template>
  <div class="p-4 max-w-xl mx-auto">
    <h1 class="text-2xl font-semibold mb-4">Прогноз на завтра</h1>
    <SignSelector v-model="sign" @change="load" />
    <ForecastCard :forecast="forecast" />
  </div>
</template>
