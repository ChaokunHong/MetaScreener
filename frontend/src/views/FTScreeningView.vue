<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Full-Text Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Select criteria → upload PDFs → run FT screening → review decisions</p>

    <!-- Step Indicator -->
    <div class="steps" style="margin-bottom: 2rem;">
      <template v-for="(s, i) in steps" :key="i">
        <div class="step" :class="{ active: currentStep === i + 1, done: currentStep > i + 1 }">
          <div class="step-circle">
            <i v-if="currentStep > i + 1" class="fas fa-check" style="font-size: 0.65rem;"></i>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span class="step-label">{{ s }}</span>
        </div>
        <div v-if="i < steps.length - 1" class="step-line" :class="{ done: currentStep > i + 1 }"></div>
      </template>
    </div>

    <!-- STEP 1: Select Criteria -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-list-check"></i> Select Criteria</div>
      <CriteriaSelector v-model="selectedCriteriaId" @select="onCriteriaSelected" />
      <div v-if="selectedCriteriaName" class="alert alert-success" style="margin-top: 0.75rem;">
        <i class="fas fa-check-circle"></i>
        Using: <strong>{{ selectedCriteriaName }}</strong>
      </div>
    </div>

    <!-- STEP 2: Upload PDFs -->
    <div v-if="currentStep >= 2" class="glass-card">
      <div class="section-title"><i class="fas fa-file-pdf"></i> Upload PDFs</div>
      <div
        class="upload-zone"
        :class="{ dragover: dragging }"
        @click="fileInput?.click()"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onFileDrop"
        style="margin-bottom: 1rem;"
      >
        <input ref="fileInput" type="file" accept=".pdf" multiple @change="onFileChange" />
        <i class="fas fa-file-pdf zone-icon"></i>
        <div class="zone-title">{{ pdfFiles.length ? `${pdfFiles.length} PDF(s) selected` : 'Drop PDFs here or click to browse' }}</div>
        <div class="zone-hint">PDF files of papers that passed TI/AB screening</div>
      </div>

      <div v-if="uploadInfo" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        Uploaded <strong>{{ uploadInfo.pdf_count }}</strong> PDFs
      </div>

      <button class="btn btn-primary" :disabled="!pdfFiles.length || uploading" @click="doUpload">
        <i v-if="uploading" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-upload"></i>
        {{ uploading ? 'Uploading…' : 'Upload PDFs' }}
      </button>
    </div>

    <!-- STEP 3: Run -->
    <div v-if="currentStep >= 3" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Full-Text Screening</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Ready to screen <strong>{{ uploadInfo?.pdf_count }}</strong> PDFs
        using criteria "<strong>{{ selectedCriteriaName }}</strong>".
      </p>

      <div v-if="running" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">{{ runStatus }}</span>
          <span class="text-muted">{{ completedCount }} / {{ totalCount }}</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
        </div>
      </div>

      <div v-if="runError" class="alert alert-danger">{{ runError }}</div>

      <button class="btn btn-primary" :disabled="running" @click="doRun">
        <i v-if="running" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-play"></i>
        {{ running ? 'Screening…' : 'Start FT Screening' }}
      </button>
    </div>

    <!-- STEP 4: Results -->
    <div v-if="currentStep >= 4 && results.length" class="glass-card">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
        <div class="section-title" style="margin-bottom: 0;"><i class="fas fa-list-alt"></i> Results</div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" @click="exportJSON"><i class="fas fa-download"></i> JSON</button>
          <button class="btn btn-secondary btn-sm" @click="exportCSV"><i class="fas fa-download"></i> CSV</button>
          <button class="btn btn-secondary btn-sm" @click="resetAll"><i class="fas fa-redo"></i> Reset</button>
        </div>
      </div>

      <div class="metric-grid" style="margin-bottom: 1.5rem;">
        <div class="metric-card">
          <div class="metric-value">{{ results.length }}</div>
          <div class="metric-label">Total</div>
        </div>
        <div class="metric-card" style="border-color: rgba(16,185,129,0.4);">
          <div class="metric-value text-success">{{ includedCount }}</div>
          <div class="metric-label">Include</div>
        </div>
        <div class="metric-card" style="border-color: rgba(239,68,68,0.4);">
          <div class="metric-value text-danger">{{ excludedCount }}</div>
          <div class="metric-label">Exclude</div>
        </div>
        <div class="metric-card" style="border-color: rgba(245,158,11,0.4);">
          <div class="metric-value text-warning">{{ reviewCount }}</div>
          <div class="metric-label">Review</div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>File</th>
              <th>Decision</th>
              <th>Tier</th>
              <th>Score</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in results" :key="i">
              <td class="text-muted">{{ i + 1 }}</td>
              <td style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ r.title || '(no title)' }}</td>
              <td><span :class="decisionClass(r.decision)">{{ r.decision }}</span></td>
              <td><span class="badge badge-unclear">T{{ r.tier ?? '?' }}</span></td>
              <td>{{ fmt(r.score) }}</td>
              <td>{{ fmt(r.confidence) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiGet, apiPost, apiUpload, decisionBadgeClass, fmtScore } from '@/api'
import CriteriaSelector from '@/components/CriteriaSelector.vue'

const steps = ['Criteria', 'Upload PDFs', 'Run', 'Results']
const currentStep = ref(1)
const sessionId = ref<string | null>(null)

// Step 1 - Select Criteria
const selectedCriteriaId = ref<string | null>(null)
const selectedCriteriaName = ref('')
const selectedCriteriaData = ref<Record<string, unknown> | null>(null)

async function onCriteriaSelected(item: { id: string; name: string }) {
  selectedCriteriaId.value = item.id
  selectedCriteriaName.value = item.name
  try {
    const full = await apiGet<{ data: Record<string, unknown> }>(`/history/criteria/${item.id}`)
    selectedCriteriaData.value = full.data
    currentStep.value = 2
  } catch (e: unknown) {
    alert(`Failed to load criteria: ${(e as Error).message}`)
  }
}

// Step 2 - Upload PDFs
const fileInput = ref<HTMLInputElement | null>(null)
const pdfFiles = ref<File[]>([])
const dragging = ref(false)
const uploading = ref(false)
const uploadInfo = ref<{ session_id: string; pdf_count: number } | null>(null)

function onFileChange(e: Event) {
  pdfFiles.value = Array.from((e.target as HTMLInputElement).files || [])
}

function onFileDrop(e: DragEvent) {
  dragging.value = false
  pdfFiles.value = Array.from(e.dataTransfer?.files || []).filter(f => f.name.endsWith('.pdf'))
}

async function doUpload() {
  if (!pdfFiles.value.length) return
  uploading.value = true
  try {
    const fd = new FormData()
    pdfFiles.value.forEach(f => fd.append('files', f))
    const data = await apiUpload<{ session_id: string; pdf_count: number; filenames: string[] }>('/screening/ft/upload-pdfs', fd)
    sessionId.value = data.session_id
    uploadInfo.value = data
    currentStep.value = 3
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploading.value = false
  }
}

// Step 3 - Run
const running = ref(false)
const runStatus = ref('')
const completedCount = ref(0)
const totalCount = ref(0)
const progressPct = ref(0)
const runError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

async function doRun() {
  if (!sessionId.value || !selectedCriteriaData.value) return
  running.value = true
  runError.value = ''
  completedCount.value = 0
  progressPct.value = 5
  runStatus.value = 'Setting criteria…'

  try {
    await apiPost(`/screening/ft/criteria/${sessionId.value}`, selectedCriteriaData.value)
    runStatus.value = 'Starting FT screening…'
    await apiPost(`/screening/ft/run/${sessionId.value}`, { session_id: sessionId.value, seed: 42 })
    runStatus.value = 'Screening in progress…'
    startPolling()
  } catch (e: unknown) {
    runError.value = `Failed: ${(e as Error).message}`
    running.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const data = await apiGet<{
        status: string; total: number; completed: number;
        results: Array<{ title?: string; decision: string }>; error?: string
      }>(`/screening/ft/results/${sessionId.value}`)

      totalCount.value = data.total || 0
      completedCount.value = data.completed || 0
      progressPct.value = totalCount.value > 0
        ? Math.round((completedCount.value / totalCount.value) * 100)
        : 10
      runStatus.value = `Screening… ${completedCount.value} / ${totalCount.value}`

      if (data.status === 'error') {
        clearInterval(pollTimer!)
        runError.value = data.error || 'Unknown error'
        running.value = false
        return
      }

      if (data.status === 'completed' || (data.completed >= data.total && data.total > 0)) {
        clearInterval(pollTimer!)
        results.value = data.results || []
        running.value = false
        currentStep.value = 4
      }
    } catch {
      // transient error, keep polling
    }
  }, 3000)
}

// Step 4 - Results
const results = ref<Array<{
  title?: string; decision: string; tier?: number; score?: number; confidence?: number
}>>([])

const includedCount = computed(() => results.value.filter(r => r.decision === 'INCLUDE').length)
const excludedCount = computed(() => results.value.filter(r => r.decision === 'EXCLUDE').length)
const reviewCount = computed(() => results.value.filter(r => r.decision === 'HUMAN_REVIEW').length)

function decisionClass(d: string) { return decisionBadgeClass(d) }
function fmt(v: unknown) { return fmtScore(v) }

function exportJSON() {
  const blob = new Blob([JSON.stringify(results.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'ft_screening_results.json'; a.click()
  URL.revokeObjectURL(url)
}

function exportCSV() {
  const headers = ['#', 'File', 'Decision', 'Tier', 'Score', 'Confidence']
  const rows = results.value.map((r, i) => [
    i + 1, `"${(r.title || '').replace(/"/g, '""')}"`, r.decision, r.tier ?? '', r.score ?? '', r.confidence ?? ''
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'ft_screening_results.csv'; a.click()
  URL.revokeObjectURL(url)
}

function resetAll() {
  if (pollTimer) clearInterval(pollTimer)
  sessionId.value = null
  selectedCriteriaId.value = null
  selectedCriteriaName.value = ''
  selectedCriteriaData.value = null
  pdfFiles.value = []
  uploadInfo.value = null
  results.value = []
  running.value = false
  runError.value = ''
  currentStep.value = 1
}
</script>
