import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import 'swiper/css'
import App from './App.vue'
import './style.css'

createApp(App).use(router).mount('#app')
