<template>
  <div>
    <!-- Hero -->
    <div class="glass-card" style="text-align: center; padding: 3rem 2rem; margin-bottom: 2rem;">
      <img src="/logo.svg" alt="MetaScreener" style="height: 64px; margin-bottom: 1.5rem;" />
      <h1 class="page-title" style="margin-bottom: 0.75rem;">MetaScreener 2.0</h1>
      <p style="color: var(--text-secondary); font-size: 1.05rem; max-width: 540px; margin: 0 auto 2rem;">
        AI-assisted systematic review using a Hierarchical Consensus Network of 4 open-source LLMs.
        Complete reproducibility. No proprietary models.
      </p>
      <router-link to="/screening" class="btn btn-primary" style="font-size: 1rem; padding: 0.75rem 2rem;">
        <i class="fas fa-search"></i> Start Screening
      </router-link>
    </div>

    <!-- Feature Cards -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 2rem;">
      <router-link
        v-for="f in features"
        :key="f.path"
        :to="f.path"
        class="feature-card"
        style="text-decoration: none;"
      >
        <div class="glass-section" style="height: 100%; margin-bottom: 0; transition: transform 0.2s ease; cursor: pointer;"
             @mouseover="(e) => (e.currentTarget as HTMLElement).style.transform = 'translateY(-4px)'"
             @mouseleave="(e) => (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'">
          <div style="font-size: 1.5rem; margin-bottom: 0.75rem; color: var(--primary-purple);"><i :class="f.icon"></i></div>
          <div class="section-title" style="margin-bottom: 0.4rem;">{{ f.title }}</div>
          <div class="text-muted">{{ f.desc }}</div>
        </div>
      </router-link>
    </div>

    <!-- System Info -->
    <div class="glass-card">
      <div class="section-title">System Information</div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem;">
        <div v-for="info in systemInfo" :key="info.label" class="glass-section" style="margin-bottom: 0;">
          <div class="text-muted" style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">{{ info.label }}</div>
          <div style="font-weight: 600; color: var(--text-primary); margin-top: 0.25rem;">{{ info.value }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiGet } from '@/api'

const features = [
  { path: '/screening',  icon: 'fas fa-search',         title: 'Literature Screening', desc: 'Upload RIS/BibTeX/CSV, set PICO criteria, run HCN screening with 4 LLMs.' },
  { path: '/evaluation', icon: 'fas fa-chart-bar',       title: 'Evaluation',           desc: 'Upload gold labels and measure sensitivity, specificity, WSS@95, AUROC.' },
  { path: '/extraction', icon: 'fas fa-table',           title: 'Data Extraction',      desc: 'Define a YAML extraction form and extract structured data from PDFs.' },
  { path: '/quality',    icon: 'fas fa-clipboard-check', title: 'Quality Assessment',   desc: 'Assess risk of bias using RoB 2, ROBINS-I, or QUADAS-2 tools.' },
]

const version = ref('—')
const systemInfo = ref([
  { label: 'Version', value: '—' },
  { label: 'LLMs', value: '4 open-source models' },
  { label: 'Architecture', value: 'Hierarchical Consensus Network' },
  { label: 'Compliance', value: 'TRIPOD-LLM' },
])

onMounted(async () => {
  try {
    const health = await apiGet<{ version: string }>('/health')
    version.value = health.version
    if (systemInfo.value[0]) systemInfo.value[0].value = `v${health.version}`
  } catch {
    // server not running yet
  }
})
</script>
