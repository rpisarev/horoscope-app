import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import HoroscopeView from '../views/HoroscopeView.vue'
import ArchiveMonth from '../views/ArchiveMonth.vue'
import ArchiveForecast from '../views/ArchiveForecast.vue'
import NotFound from '../views/NotFound.vue'

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
    path: '/archive/:sign/:year/:month',
    name: 'archive-month',
    component: ArchiveMonth,
    props: true,
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