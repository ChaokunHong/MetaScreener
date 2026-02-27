<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Literature Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Upload search results → set criteria → run HCN → review decisions</p>

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

    <!-- STEP 1: Upload -->
    <div v-if="currentStep >= 1" class="glass-card">
      <div class="section-title"><i class="fas fa-upload"></i> Upload Search Results</div>
      <div
        class="upload-zone"
        :class="{ dragover: dragging }"
        @click="fileInput?.click()"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onFileDrop"
        style="margin-bottom: 1rem;"
      >
        <input ref="fileInput" type="file" accept=".ris,.bib,.csv,.xlsx,.xml" @change="onFileChange" />
        <i class="fas fa-file-alt zone-icon"></i>
        <div class="zone-title">{{ selectedFile ? selectedFile.name : 'Drop file here or click to browse' }}</div>
        <div class="zone-hint">RIS, BibTeX, CSV, Excel, PubMed XML</div>
      </div>

      <div v-if="uploadInfo" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        Loaded <strong>{{ uploadInfo.record_count }}</strong> records
      </div>

      <button class="btn btn-primary" :disabled="!selectedFile || uploading" @click="doUpload">
        <i v-if="uploading" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-upload"></i>
        {{ uploading ? 'Uploading…' : 'Upload File' }}
      </button>
    </div>

    <!-- STEP 2: Criteria -->
    <div v-if="currentStep >= 2" class="glass-card">
      <div class="section-title"><i class="fas fa-filter"></i> Set Inclusion/Exclusion Criteria</div>

      <!-- Tabs -->
      <div class="tabs">
        <button
          v-for="tab in criteriaTabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: criteriaTab === tab.id }"
          @click="criteriaTab = tab.id"
        >{{ tab.label }}</button>
      </div>

      <!-- Topic mode -->
      <div v-if="criteriaTab === 'topic'">
        <div class="form-group">
          <label class="form-label">Research Topic / PICO Question</label>
          <textarea
            v-model="topicText"
            class="form-control"
            rows="3"
            placeholder="e.g. Antimicrobial resistance in hospital-acquired infections in adult ICU patients treated with carbapenems"
          ></textarea>
        </div>
      </div>

      <!-- YAML upload mode -->
      <div v-if="criteriaTab === 'yaml'">
        <div class="form-group">
          <label class="form-label">Upload YAML criteria file</label>
          <input ref="yamlInput" type="file" accept=".yaml,.yml" class="form-control" style="padding: 0.5rem;" @change="onYamlChange" />
        </div>
        <div class="form-group">
          <label class="form-label">YAML Content</label>
          <textarea v-model="yamlText" class="form-control" rows="6" placeholder="Or paste YAML here…"></textarea>
        </div>
      </div>

      <!-- Manual JSON mode -->
      <div v-if="criteriaTab === 'json'">
        <div class="form-group">
          <label class="form-label">Criteria JSON</label>
          <textarea v-model="jsonText" class="form-control" rows="8" placeholder='{"include": [...], "exclude": [...]}'></textarea>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="settingCriteria" @click="doSetCriteria">
        <i v-if="settingCriteria" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-check"></i>
        {{ settingCriteria ? 'Applying…' : 'Apply Criteria' }}
      </button>
    </div>

    <!-- STEP 3: Run -->
    <div v-if="currentStep >= 3" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Screening</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Ready to screen <strong>{{ uploadInfo?.record_count }}</strong> records using 4 open-source LLMs (seed=42, temperature=0.0).
      </p>

      <!-- Progress -->
      <div v-if="running" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">{{ runStatus }}</span>
          <span class="text-muted">{{ completedCount }} / {{ totalCount }}</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
        </div>
        <div class="progress-log" ref="logEl" style="margin-top: 0.75rem;">{{ logText }}</div>
      </div>

      <div v-if="runError" class="alert alert-danger">{{ runError }}</div>

      <button class="btn btn-primary" :disabled="running" @click="doRun">
        <i v-if="running" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-play"></i>
        {{ running ? 'Screening…' : 'Start Screening' }}
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

      <!-- Summary -->
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

      <!-- Table -->
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
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
import { ref, computed, nextTick } from 'vue'
import { apiUpload, apiPost, apiGet, decisionBadgeClass, fmtScore } from '@/api'

const steps = ['Upload', 'Criteria', 'Run', 'Results']
const currentStep = ref(1)
const sessionId = ref<string | null>(null)

// Step 1 - Upload
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadInfo = ref<{ session_id: string; record_count: number } | null>(null)

function onFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) selectedFile.value = f
}

function onFileDrop(e: DragEvent) {
  dragging.value = false
  const f = e.dataTransfer?.files[0]
  if (f) selectedFile.value = f
}

async function doUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    const data = await apiUpload<{ session_id: string; record_count: number }>('/screening/upload', fd)
    sessionId.value = data.session_id
    uploadInfo.value = data
    currentStep.value = 2
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploading.value = false
  }
}

// Step 2 - Criteria
const criteriaTabs = [
  { id: 'topic', label: 'Generate from Topic' },
  { id: 'yaml', label: 'Upload YAML' },
  { id: 'json', label: 'Manual JSON' },
]
const criteriaTab = ref('topic')
const topicText = ref('')
const yamlText = ref('')
const jsonText = ref('')
const yamlInput = ref<HTMLInputElement | null>(null)
const settingCriteria = ref(false)

async function onYamlChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) yamlText.value = await f.text()
}

async function doSetCriteria() {
  if (!sessionId.value) return
  settingCriteria.value = true
  try {
    let payload: Record<string, string>
    if (criteriaTab.value === 'topic') {
      if (!topicText.value.trim()) { alert('Please enter a topic.'); return }
      payload = { mode: 'topic', text: topicText.value.trim() }
    } else if (criteriaTab.value === 'yaml') {
      if (!yamlText.value.trim()) { alert('Please enter YAML criteria.'); return }
      payload = { mode: 'upload', yaml_text: yamlText.value.trim() }
    } else {
      if (!jsonText.value.trim()) { alert('Please enter JSON criteria.'); return }
      payload = { mode: 'manual', json_text: jsonText.value.trim() }
    }
    await apiPost(`/screening/criteria/${sessionId.value}`, payload)
    currentStep.value = 3
  } catch (e: unknown) {
    alert(`Failed to set criteria: ${(e as Error).message}`)
  } finally {
    settingCriteria.value = false
  }
}

// Step 3 - Run
const running = ref(false)
const runStatus = ref('')
const completedCount = ref(0)
const totalCount = ref(0)
const progressPct = ref(0)
const runError = ref('')
const logText = ref('')
const logEl = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

function appendLog(msg: string) {
  const ts = new Date().toLocaleTimeString()
  logText.value += `${ts} — ${msg}\n`
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

async function doRun() {
  if (!sessionId.value) return
  running.value = true
  runError.value = ''
  logText.value = ''
  completedCount.value = 0
  progressPct.value = 5
  runStatus.value = 'Sending request…'

  try {
    await apiPost(`/screening/run/${sessionId.value}`, { session_id: sessionId.value, seed: 42 })
    runStatus.value = 'Screening in progress…'
    startPolling()
  } catch (e: unknown) {
    runError.value = `Failed: ${(e as Error).message}`
    running.value = false
  }
}

function startPolling() {
  let lastCompleted = 0
  pollTimer = setInterval(async () => {
    try {
      const data = await apiGet<{
        status: string; total: number; completed: number;
        results: Array<{ title?: string; decision: string }>; error?: string
      }>(`/screening/results/${sessionId.value}`)

      totalCount.value = data.total || 0
      completedCount.value = data.completed || 0
      progressPct.value = totalCount.value > 0
        ? Math.round((completedCount.value / totalCount.value) * 100)
        : 10
      runStatus.value = `Screening… ${completedCount.value} / ${totalCount.value}`

      if (data.completed > lastCompleted && data.results) {
        const newOnes = data.results.slice(lastCompleted)
        newOnes.forEach((r: { title?: string; decision: string }) => {
          const icon = r.decision === 'INCLUDE' ? '✓' : r.decision === 'EXCLUDE' ? '✗' : '?'
          appendLog(`[${icon}] ${(r.title || 'Record').substring(0, 60)} — ${r.decision}`)
        })
        lastCompleted = data.completed
      }

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
  }, 2000)
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
  const a = document.createElement('a'); a.href = url; a.download = 'screening_results.json'; a.click()
  URL.revokeObjectURL(url)
}

function exportCSV() {
  const headers = ['#', 'Title', 'Decision', 'Tier', 'Score', 'Confidence']
  const rows = results.value.map((r, i) => [
    i + 1, `"${(r.title || '').replace(/"/g, '""')}"`, r.decision, r.tier ?? '', r.score ?? '', r.confidence ?? ''
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'screening_results.csv'; a.click()
  URL.revokeObjectURL(url)
}

function resetAll() {
  if (pollTimer) clearInterval(pollTimer)
  sessionId.value = null
  selectedFile.value = null
  uploadInfo.value = null
  topicText.value = ''
  yamlText.value = ''
  jsonText.value = ''
  results.value = []
  running.value = false
  logText.value = ''
  runError.value = ''
  currentStep.value = 1
}
</script>
