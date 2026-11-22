<template>
  <header class="language-bar">
    <label for="language-select" class="sr-only">{{ text.language }}</label>
    <select id="language-select" :value="locale" @change="changeLanguage">
      <option lang="en" value="en">English</option>
      <option lang="uk" value="uk">Українська</option>
      <option lang="ru" value="ru">Русский</option>
    </select>
  </header>
  <div v-if="businessDateError" role="alert" class="business-status relative bg-slate-950 p-6 text-center text-amber-200">
    {{ text.businessDateError }}
    <button class="ml-3 underline" @click="retry">{{ text.retry }}</button>
  </div>
  <p v-else-if="!businessContext" role="status" class="business-status relative bg-slate-950 p-6 text-center text-slate-300">
    {{ text.loading }}
  </p>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watchEffect } from 'vue'
import { businessContext, businessDateError, refreshBusinessDate } from './utils/businessDate'
import { useUiText } from './utils/uiText'
import type { Locale } from './utils/locale'

const { locale, text, switchLocale } = useUiText()

function changeLanguage(event: Event) {
  const select = event.target as HTMLSelectElement
  const next = select.value as Locale
  select.value = locale.value
  void switchLocale(next)
}

watchEffect(() => {
  document.documentElement.lang = locale.value
  document.title = text.value.title
  document.querySelector<HTMLMetaElement>('meta[name="description"]')?.setAttribute('content', text.value.description)
})

function refresh() {
  if (businessContext.value && document.visibilityState === 'visible') {
    void refreshBusinessDate().catch(() => {}) // Error is shown above; keep the last server value.
  }
}

function retry() {
  window.location.reload()
}

let refreshTimer: number
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

<style>
.language-bar {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 3rem;
  padding-inline: .75rem;
  background-color: #070b19;
}

#language-select {
  min-height: 2.75rem;
  border: 1px solid #64748b;
  border-radius: .5rem;
  padding: .25rem .5rem;
  color: #fef3c7;
  color-scheme: dark;
  background: #0f172a;
  font-size: .875rem;
}

#language-select:focus-visible {
  outline: 2px solid #fde68a;
  outline-offset: 2px;
}

#app:has(.home) { --home-height: calc(100svh - 3rem); }

/* The empty corner beside the orbit can accommodate the control at these sizes. */
@media (min-width: 768px) and (min-height: 768px),
       (max-height: 767px) and (min-width: 480px) and (min-aspect-ratio: 4/3) {
  #app:has(.home):not(:has(.business-status)) { --home-height: 100svh; }
  #app:has(.home):not(:has(.business-status)) > .language-bar {
    position: absolute;
    top: 0;
    left: 0;
    background: transparent;
  }
}
</style>
