import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import ScreeningView from '@/views/ScreeningView.vue'
import EvaluationView from '@/views/EvaluationView.vue'
import ExtractionView from '@/views/ExtractionView.vue'
import QualityView from '@/views/QualityView.vue'
import SettingsView from '@/views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/screening', component: ScreeningView },
    { path: '/evaluation', component: EvaluationView },
    { path: '/extraction', component: ExtractionView },
    { path: '/quality', component: QualityView },
    { path: '/settings', component: SettingsView },
  ],
})

export default router
