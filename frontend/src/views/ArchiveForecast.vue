<template>
  <NotFound v-if="!validation.ok" :title="text.routeErrors[validation.code]" />
  <p v-else role="status" class="p-6 text-center text-slate-300">{{ text.loading }}</p>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NotFound from './NotFound.vue'
import { pad2, validateArchiveForecastRoute } from '../utils/routeValidation'

import { useUiText } from '../utils/uiText'
import { localeQuery } from '../utils/locale'

const { locale, text } = useUiText()
const route = useRoute()
const router = useRouter()
const validation = computed(() => validateArchiveForecastRoute(route.params))

// Compatibility only: explicit invalid parameters stay on the contextual 404.
watch(() => route.fullPath, () => {
  if (!validation.value.ok) return
  const { sign, year, month, day } = validation.value.params
  void router.replace({
    name: 'horoscope',
    params: { sign, day: `${String(year).padStart(4, '0')}-${pad2(month)}-${pad2(day)}` },
    query: { ...route.query, ...localeQuery(locale.value) },
    hash: route.hash,
  })
}, { immediate: true })
</script>
