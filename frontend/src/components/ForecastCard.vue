<script setup>
defineProps({
  forecast: Object
})
</script>

<template>
  <div v-if="forecast" class="bg-white shadow rounded p-4">
    <p>{{ forecast.text }}</p>
    <small class="text-gray-500">Generated for {{ forecast.day }}</small>
  </div>
  <p v-else>Loading...</p>
</template>
