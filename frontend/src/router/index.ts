import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import HoroscopeView from '../views/HoroscopeView.vue'
import ArchiveMonth from '../views/ArchiveMonth.vue'
import ArchiveForecast from '../views/ArchiveForecast.vue'
import NotFound from '../views/NotFound.vue'

function getTodayParts() {
  const now = new Date()
  const day = now.toISOString().slice(0, 10)
  const year = String(now.getUTCFullYear())
  const month = String(now.getUTCMonth() + 1).padStart(2, '0')

  return { day, year, month }
}

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
    redirect: () => {
      const { day } = getTodayParts()

      return `/horoscope/capricorn/${day}`
    },
  },

  {
    path: '/archive/:sign/:year/:month',
    name: 'archive-month',
    component: ArchiveMonth,
    props: true,
  },

  {
    path: '/archive',
    redirect: () => {
      const { year, month } = getTodayParts()

      return `/archive/capricorn/${year}/${month}`
    },
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

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})