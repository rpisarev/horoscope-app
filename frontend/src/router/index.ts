import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import HoroscopeView from '../views/HoroscopeView.vue'
import ArchiveMonth from '../views/ArchiveMonth.vue'
import ArchiveForecast from '../views/ArchiveForecast.vue'
import NotFound from '../views/NotFound.vue'

import { refreshBusinessDate } from '../utils/businessDate'

const routes = [
  {
    path: '/',
    name: 'home',
    component: Home,
  },

  {
    path: '/horoscope/:sign/:day',
    name: 'horoscope',
    component: HoroscopeView,
    props: true,
  },

  {
    path: '/horoscope',
    component: HoroscopeView, // Redirected after the authoritative date is loaded.
  },

  {
    path: '/archive/:sign/:year/:month',
    name: 'archive-month',
    component: ArchiveMonth,
    props: true,
  },

  {
    path: '/archive',
    component: ArchiveMonth, // Redirected after the authoritative date is loaded.
  },

  {
    path: '/archive/:sign/:year/:month/:day',
    name: 'archive-forecast',
    component: ArchiveForecast,
    props: true,
  },

  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: NotFound,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async to => {
  const matchedPath = to.matched[to.matched.length - 1]?.path
  const usesToday = matchedPath === '/horoscope' || matchedPath === '/archive'
  if (!usesToday) return

  try {
    const { business_date: day } = await refreshBusinessDate()
    const suffix = { query: to.query, hash: to.hash }
    if (matchedPath === '/horoscope') return { path: `/horoscope/capricorn/${day}`, ...suffix }
    if (matchedPath === '/archive') return { path: `/archive/capricorn/${day.slice(0, 4)}/${day.slice(5, 7)}`, ...suffix }
  } catch {
    // Only convenience redirects need today's date. Keep the previous route on failure.
    return false
  }
})

export default router
