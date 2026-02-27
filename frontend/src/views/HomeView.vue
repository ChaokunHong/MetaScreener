<template>
  <div>
    <!-- Hero -->
    <div class="hero-card">
      <img src="/logo.svg" alt="MetaScreener" class="hero-logo" />
      <p class="hero-sub">
        AI-assisted systematic review using a Hierarchical Consensus Network of 4 open-source LLMs.
        Complete reproducibility. No proprietary models.
      </p>
      <router-link to="/screening" class="btn btn-primary btn-hero">
        <i class="fas fa-arrow-right"></i> Start Screening
      </router-link>
    </div>

    <!-- Feature Cards -->
    <div class="feature-grid">
      <router-link
        v-for="f in features"
        :key="f.path"
        :to="f.path"
        class="feature-card"
      >
        <div class="feature-icon-wrap">
          <i :class="f.icon"></i>
        </div>
        <div class="feature-title">{{ f.title }}</div>
        <div class="feature-desc">{{ f.desc }}</div>
      </router-link>
    </div>

    <!-- System Info -->
    <div class="glass-card">
      <div class="section-title">System Information</div>
      <div class="sysinfo-grid">
        <div v-for="info in systemInfo" :key="info.label" class="sysinfo-item">
          <div class="sysinfo-label">{{ info.label }}</div>
          <div class="sysinfo-value">{{ info.value }}</div>
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

const systemInfo = ref([
  { label: 'Version', value: '—' },
  { label: 'LLMs', value: '4 open-source models' },
  { label: 'Architecture', value: 'Hierarchical Consensus Network' },
  { label: 'Compliance', value: 'TRIPOD-LLM' },
])

onMounted(async () => {
  try {
    const health = await apiGet<{ version: string }>('/health')
    if (systemInfo.value[0]) systemInfo.value[0].value = `v${health.version}`
  } catch {
    // server not running yet
  }
})
</script>
