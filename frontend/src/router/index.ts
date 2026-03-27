import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import CriteriaView from '@/views/CriteriaView.vue'
import ScreeningLandingView from '@/views/ScreeningLandingView.vue'
import TAScreeningView from '@/views/TAScreeningView.vue'
import FTScreeningView from '@/views/FTScreeningView.vue'
import EvaluationView from '@/views/EvaluationView.vue'
import ExtractionView from '@/views/ExtractionView.vue'
import ExtractionV2View from '@/views/ExtractionV2View.vue'
import QualityView from '@/views/QualityView.vue'
import HistoryView from '@/views/HistoryView.vue'
import SettingsView from '@/views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/criteria', component: CriteriaView },
    { path: '/screening', component: ScreeningLandingView },
    { path: '/screening/ta', component: TAScreeningView },
    { path: '/screening/ft', component: FTScreeningView },
    { path: '/evaluation', component: EvaluationView },
    { path: '/extraction', component: ExtractionView },
    { path: '/extraction-v2', component: ExtractionV2View },
    { path: '/quality', component: QualityView },
    { path: '/history', component: HistoryView },
    { path: '/settings', component: SettingsView },
  ],
})

export default router
