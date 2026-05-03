<template>
  <main class="min-h-screen flex items-center justify-center px-4 text-white bg-[#070b19]">
    <section
      class="max-w-md text-center rounded-3xl border border-white/15
      bg-white/10 px-8 py-10 shadow-2xl backdrop-blur"
    >
      <div class="mb-4 text-6xl text-amber-300">
        ✦
      </div>

      <p class="mb-3 text-xs uppercase tracking-[0.35em] text-amber-300/80">
        404
      </p>

      <h1 class="font-merienda text-3xl mb-3">
        {{ title }}
      </h1>

      <p v-if="description" class="font-lato text-white/75 mb-8">
        {{ description }}
      </p>

      <RouterLink
        :to="{ name: 'home' }"
        class="inline-flex items-center justify-center rounded-full
        bg-amber-300 px-6 py-3 font-semibold text-slate-950
        transition hover:bg-amber-200"
      >
        На главную
      </RouterLink>
    </section>
  </main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'

withDefaults(
  defineProps<{
    title?: string
    description?: string
  }>(),
  {
    title: 'Страница потерялась среди звёзд',
    description: 'Такого гороскопа не существует или ссылка устарела.',
  }
)
</script>