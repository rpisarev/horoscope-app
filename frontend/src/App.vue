<template>
  <div v-if="businessDateError" role="alert" class="p-6 text-center text-amber-200">
    {{ businessDateError }}
    <button class="ml-3 underline" @click="retry">Повторить</button>
  </div>
  <p v-else-if="!businessContext" role="status" class="p-6 text-center text-slate-300">
    Загрузка…
  </p>
  <router-view />
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { businessContext, businessDateError, refreshBusinessDate } from './utils/businessDate'

function refresh() {
  if (businessContext.value && document.visibilityState === 'visible') {
    void refreshBusinessDate().catch(() => {}) // Error is shown above; keep the last server value.
  }
}

function retry() {
  window.location.reload()
}

let refreshTimer
onMounted(() => {
  if (!businessContext.value && !businessDateError.value) {
    void refreshBusinessDate().catch(() => {})
  }
  // Keep long-lived pages current, including when a sleeping tab becomes visible.
  refreshTimer = window.setInterval(refresh, 60_000)
  document.addEventListener('visibilitychange', refresh)
})
onUnmounted(() => {
  window.clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', refresh)
})
</script>
