import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Today from '../pages/Today.vue'
import Tomorrow from '../pages/Tomorrow.vue'
import Archive from '../pages/Archive.vue'

const routes = [
  { path: '/', name: 'home', component: Home },
  { path: '/today', component: Today },
  { path: '/tomorrow', component: Tomorrow },
  { path: '/archive', component: Archive },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})

