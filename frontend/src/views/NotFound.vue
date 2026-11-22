<template>
  <main class="lost-page">
    <CosmicGate404>
      <section class="message">
        <p class="error-code"><span aria-hidden="true">✦</span> 404</p>
        <h1 class="font-merienda">{{ title ?? text.notFoundTitle }}</h1>
        <p v-if="description !== ''" class="description font-lato">{{ description ?? text.notFoundDescription }}</p>
        <RouterLink :to="{ name: 'home', query: localeQuery(locale) }" class="home-link">
          {{ text.backHome }}
        </RouterLink>
      </section>
    </CosmicGate404>
  </main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import CosmicGate404 from '../components/CosmicGate404.vue'
import { useUiText } from '../utils/uiText'
import { localeQuery } from '../utils/locale'

const { locale, text } = useUiText()
defineProps<{ title?: string; description?: string }>()
</script>

<style scoped>
.lost-page {
  display: grid;
  place-items: center;
  min-height: calc(100svh - 3rem);
  padding: .5rem clamp(.625rem, 2vw, 2rem) 2rem;
  background: #070b19;
  color: #eef4f6;
}
.message { max-width: 44rem; margin: .25rem auto 0; }
.error-code {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: .65rem;
  color: #ddc597;
  font: 600 .75rem/1.5 ui-monospace, monospace;
  letter-spacing: .23em;
}
.error-code::before, .error-code::after {
  content: '';
  width: 2.4rem;
  height: 1px;
  background: #a28d665e;
}
.message h1 {
  margin: .65rem auto .5rem;
  font-size: clamp(1.55rem, 3.1vw, 2.55rem);
  line-height: 1.22;
  text-wrap: balance;
}
.description { margin: 0 auto; color: #bbc6d6; line-height: 1.55; text-wrap: balance; }
.home-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  margin-top: 1.15rem;
  padding: .625rem 1.5rem;
  border-radius: 999px;
  background: #f2d399;
  color: #191b25;
  font-weight: 650;
}
.home-link:hover { background: #ffe5b5; }
.home-link:focus-visible { outline: 2px solid #fff0ce; outline-offset: 4px; }
@media (max-height: 450px) and (min-width: 500px) and (orientation: landscape) {
  .lost-page { padding: .5rem .75rem .875rem; }
  .message { margin: 0; }
  .description { font-size: .9rem; }
  .home-link { margin-top: .7rem; }
}
</style>
