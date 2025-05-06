<script setup>
import { ref, onMounted } from 'vue'
import { useForecastStore } from '../store'
import ForecastCard from '../components/ForecastCard.vue'
import SignSelector from '../components/SignSelector.vue'

const store = useForecastStore()
const sign = ref('aries')
const selectedDate = ref(new Date().toISOString().slice(0,10))
const forecast = ref(null)

async function load() {
  forecast.value = await store.fetchForecast(sign.value, selectedDate.value)
}

onMounted(load)
</script>

<template>
  <div class="p-4 max-w-xl mx-auto">
    <h1 class="text-2xl font-semibold mb-4">Архів прогнозів</h1>
    <div class="flex gap-2">
      <SignSelector v-model="sign" @change="load" />
      <input type="date" v-model="selectedDate" @change="load" class="border p-1 rounded" />
    </div>
    <ForecastCard :forecast="forecast" class="mt-4" />
  </div>
</template>
