<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Evaluation</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Upload gold-standard labels to measure HCN screening performance</p>

    <!-- Upload Section -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-tags"></i> Upload Gold Labels</div>

      <div class="form-group">
        <label class="form-label">Gold labels file (RIS / CSV)</label>
        <div
          class="upload-zone"
          @click="labelInput?.click()"
          @dragover.prevent="draggingLabel = true"
          @dragleave="draggingLabel = false"
          @drop.prevent="onLabelDrop"
          :class="{ dragover: draggingLabel }"
          style="margin-bottom: 0.5rem;"
        >
          <input ref="labelInput" type="file" accept=".ris,.csv" @change="onLabelChange" />
          <i class="fas fa-tags zone-icon"></i>
          <div class="zone-title">{{ labelFile ? labelFile.name : 'Drop labels file here or click to browse' }}</div>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Screening Session ID</label>
        <input v-model="screeningSessionId" type="text" class="form-control" placeholder="Paste session ID from Screening page" />
        <div class="text-muted" style="margin-top: 0.25rem; font-size: 0.8rem;">
          Run a screening first to get a session ID, then paste it here.
        </div>
      </div>

      <div v-if="labelInfo" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        Loaded <strong>{{ labelInfo.gold_label_count }}</strong> gold labels (session: {{ labelInfo.session_id }})
      </div>
      <div v-if="evalError" class="alert alert-danger">{{ evalError }}</div>

      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
        <button class="btn btn-secondary" :disabled="!labelFile || uploadingLabels" @click="doUploadLabels">
          <i v-if="uploadingLabels" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-upload"></i>
          {{ uploadingLabels ? 'Uploading…' : 'Upload Labels' }}
        </button>
        <button class="btn btn-primary" :disabled="!evalSessionId || !screeningSessionId || running" @click="doRunEval">
          <i v-if="running" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-play"></i>
          {{ running ? 'Evaluating…' : 'Run Evaluation' }}
        </button>
      </div>
    </div>

    <!-- Results -->
    <template v-if="metrics">
      <!-- Metric Cards -->
      <div class="glass-card">
        <div class="section-title" style="margin-bottom: 1rem;"><i class="fas fa-chart-line"></i> Performance Metrics</div>
        <div class="metric-grid">
          <div class="metric-card" v-for="m in metricCards" :key="m.label">
            <div class="metric-value" :style="{ color: m.color || 'var(--text-primary)' }">{{ m.value }}</div>
            <div class="metric-label">{{ m.label }}</div>
          </div>
        </div>

        <!-- Lancet format output -->
        <div class="glass-section">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <div class="section-title" style="margin-bottom: 0;"><i class="fas fa-file-medical-alt"></i> Lancet Format Output</div>
            <button class="btn btn-secondary btn-sm" @click="copyLancet"><i class="fas fa-copy"></i> Copy</button>
          </div>
          <pre style="font-size: 0.8rem; color: var(--text-primary); white-space: pre-wrap; margin: 0;">{{ lancetText }}</pre>
        </div>
      </div>

      <!-- Charts -->
      <div class="glass-card" v-if="rocData">
        <div class="section-title" style="margin-bottom: 1rem;"><i class="fas fa-chart-area"></i> ROC Curve</div>
        <canvas ref="rocCanvas" height="300"></canvas>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { apiUpload, apiPost, apiGet } from '@/api'
import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)

// Upload labels
const labelInput = ref<HTMLInputElement | null>(null)
const labelFile = ref<File | null>(null)
const draggingLabel = ref(false)
const uploadingLabels = ref(false)
const labelInfo = ref<{ session_id: string; gold_label_count: number } | null>(null)
const evalSessionId = ref<string | null>(null)

function onLabelChange(e: Event) {
  labelFile.value = (e.target as HTMLInputElement).files?.[0] || null
}
function onLabelDrop(e: DragEvent) {
  draggingLabel.value = false
  labelFile.value = e.dataTransfer?.files[0] || null
}

async function doUploadLabels() {
  if (!labelFile.value) return
  uploadingLabels.value = true
  try {
    const fd = new FormData()
    fd.append('file', labelFile.value)
    const data = await apiUpload<{ session_id: string; gold_label_count: number }>('/evaluation/upload-labels', fd)
    labelInfo.value = data
    evalSessionId.value = data.session_id
  } catch (e: unknown) {
    evalError.value = `Upload failed: ${(e as Error).message}`
  } finally {
    uploadingLabels.value = false
  }
}

// Run evaluation
const screeningSessionId = ref('')
const running = ref(false)
const evalError = ref('')

interface EvalMetrics {
  sensitivity?: number
  specificity?: number
  f1?: number
  wss_at_95?: number
  auroc?: number
  ece?: number
  brier_score?: number
  kappa?: number
  roc_curve?: { fpr: number[]; tpr: number[] }
}

const metrics = ref<EvalMetrics | null>(null)
const rocData = ref<{ fpr: number[]; tpr: number[] } | null>(null)
const rocCanvas = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

async function doRunEval() {
  if (!evalSessionId.value || !screeningSessionId.value) return
  running.value = true
  evalError.value = ''
  try {
    await apiPost(`/evaluation/run/${evalSessionId.value}`, {
      screening_session_id: screeningSessionId.value,
      seed: 42,
    })
    const data = await apiGet<EvalMetrics>(`/evaluation/results/${evalSessionId.value}`)
    metrics.value = data
    if (data.roc_curve) {
      rocData.value = data.roc_curve
      nextTick(() => renderRoc())
    }
  } catch (e: unknown) {
    evalError.value = `Evaluation failed: ${(e as Error).message}`
  } finally {
    running.value = false
  }
}

function fmt(v: number | undefined, decimals = 3): string {
  if (v === undefined || v === null) return '—'
  return v.toFixed(decimals)
}

const metricCards = computed(() => [
  { label: 'Sensitivity', value: fmt(metrics.value?.sensitivity), color: '#10b981' },
  { label: 'Specificity', value: fmt(metrics.value?.specificity) },
  { label: 'F1 Score', value: fmt(metrics.value?.f1) },
  { label: 'WSS@95', value: fmt(metrics.value?.wss_at_95) },
  { label: 'AUROC', value: fmt(metrics.value?.auroc) },
  { label: 'ECE', value: fmt(metrics.value?.ece) },
  { label: 'Brier Score', value: fmt(metrics.value?.brier_score) },
  { label: 'κ (Kappa)', value: fmt(metrics.value?.kappa) },
])

const lancetText = computed(() => {
  if (!metrics.value) return ''
  const m = metrics.value
  const fmt3 = (v?: number) => v !== undefined ? v.toFixed(3).replace('.', '·') : '—'
  return [
    `Sensitivity ${fmt3(m.sensitivity)} · Specificity ${fmt3(m.specificity)}`,
    `F1 ${fmt3(m.f1)} · WSS@95 ${fmt3(m.wss_at_95)}`,
    `AUROC ${fmt3(m.auroc)} · ECE ${fmt3(m.ece)} · Brier ${fmt3(m.brier_score)}`,
    `κ ${fmt3(m.kappa)}`,
  ].join('\n')
})

function copyLancet() {
  navigator.clipboard.writeText(lancetText.value)
}

function renderRoc() {
  if (!rocCanvas.value || !rocData.value) return
  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(rocCanvas.value, {
    type: 'line',
    data: {
      labels: rocData.value.fpr,
      datasets: [{
        label: 'ROC Curve',
        data: rocData.value.tpr,
        borderColor: '#8b5cf6',
        backgroundColor: 'rgba(139,92,246,0.1)',
        fill: true,
        pointRadius: 0,
        tension: 0.3,
      }, {
        label: 'Random',
        data: rocData.value.fpr,
        borderColor: 'rgba(107,114,128,0.4)',
        borderDash: [4, 4],
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'bottom' } },
      scales: {
        x: { title: { display: true, text: 'False Positive Rate' } },
        y: { title: { display: true, text: 'True Positive Rate' }, min: 0, max: 1 },
      },
    },
  })
}
</script>
