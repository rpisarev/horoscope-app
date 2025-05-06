import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useForecastStore = defineStore('forecast', () => {
  const forecasts = ref({})

  async function fetchForecast(sign, date) {
    const key = `${sign}-${date}`
    if (forecasts.value[key]) return forecasts.value[key]
    const res = await fetch(`/api/forecast?sign=${sign}&date=${date}`)
    const data = await res.json()
    forecasts.value[key] = data
    return data
  }

  return { forecasts, fetchForecast }
})
