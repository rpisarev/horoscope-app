import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import Home from '../views/Home.vue'
import Archive from '../pages/Archive.vue'
import HoroscopeView from '../views/HoroscopeView.vue'
import ArchiveMonth from '../views/ArchiveMonth.vue'

const routes = [
  { path: '/', name: 'home', component: Home },
  {
    name: 'horoscope',
    path: '/horoscope/:sign/:day',
    component: HoroscopeView,
    props: true,
  },
  {
    path: '/horoscope',
    redirect: () => {
      const today = new Date().toISOString().slice(0, 10)
      return `/horoscope/capricorn/${today}`
    },
  },
  {
    name: 'ArchiveMonth',
    path: '/archive/:sign/:year/:month',
    component: ArchiveMonth,
    props: true
  },
  {
    path: '/archive',
    redirect: () => {
      const today = new Date().toISOString().slice(0, 10)
      return '/archive/gemini/2025/${today}'
    },
  },
  {
    path: '/archiveforecast/:sign/:date',
    name: 'ArchiveForecast',
    component: () => import('../views/ArchiveForecast.vue'),
    props: true,
  }
]

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

