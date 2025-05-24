import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import Home from '../views/Home.vue'
import Today from '../pages/Today.vue'
import Tomorrow from '../pages/Tomorrow.vue'
import Archive from '../pages/Archive.vue'
import HoroscopeView from '../views/HoroscopeView.vue'

const routes = [
  { path: '/', name: 'home', component: Home },
  { path: '/today', component: Today },
  { path: '/tomorrow', component: Tomorrow },
  { path: '/archive', component: Archive },
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
]

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

