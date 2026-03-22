<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Title / Abstract Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Select criteria → upload search results → run HCN screening → review decisions</p>

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

    <!-- STEP 2: Upload -->
    <div v-if="currentStep >= 2" class="glass-card">
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

    <!-- STEP 3: Run -->
    <div v-if="currentStep >= 3" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Screening</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Ready to screen <strong>{{ uploadInfo?.record_count }}</strong> records
        using criteria "<strong>{{ selectedCriteriaName }}</strong>".
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
              <th>
                Tier
                <span class="th-info" title="Routing tier: T0 = rule violation (auto-exclude), T1 = near-unanimous agreement (auto), T2 = majority agreement (auto-include), T3 = no consensus (human review)">
                  <i class="fas fa-circle-info"></i>
                </span>
              </th>
              <th>
                Score
                <span class="th-info" title="Calibrated ensemble inclusion probability (0.0–1.0). Higher = more likely relevant. Weighted average of all models' scores adjusted by confidence and calibration.">
                  <i class="fas fa-circle-info"></i>
                </span>
              </th>
              <th>
                Confidence
                <span class="th-info" title="Ensemble agreement confidence (0.0–1.0). Based on Shannon entropy of model decisions. 1.0 = all models agree, 0.0 = maximum disagreement (50/50 split).">
                  <i class="fas fa-circle-info"></i>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(r, i) in results" :key="i">
              <tr class="result-row" :class="{ expanded: expandedRow === i }" @click="toggleDetail(i)">
                <td class="text-muted">{{ i + 1 }}</td>
                <td style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ r.title || '(no title)' }}</td>
                <td><span :class="decisionClass(r.decision)">{{ r.decision }}</span></td>
                <td><span class="badge badge-unclear">T{{ r.tier ?? '?' }}</span></td>
                <td>{{ fmt(r.score) }}</td>
                <td>{{ fmt(r.confidence) }}</td>
              </tr>
              <!-- Expanded detail row -->
              <tr v-if="expandedRow === i" class="detail-row">
                <td colspan="6">
                  <div v-if="detailLoading" style="text-align: center; padding: 1rem;">
                    <i class="fas fa-spinner fa-spin"></i> Loading model details...
                  </div>
                  <div v-else-if="detailData" class="detail-panel">
                    <div class="detail-models-grid">
                      <div
                        v-for="mo in detailData.model_outputs"
                        :key="mo.model_id"
                        class="detail-model-card"
                        :class="{ 'model-error': mo.error }"
                      >
                        <div class="detail-model-header">
                          <span class="detail-model-id">{{ mo.model_id }}</span>
                          <span :class="decisionClass(mo.decision)">{{ mo.decision }}</span>
                        </div>
                        <div v-if="mo.error" class="detail-model-error">
                          <i class="fas fa-exclamation-triangle"></i> {{ mo.error }}
                        </div>
                        <template v-else>
                          <div class="detail-model-scores">
                            <span>Score: <strong>{{ fmt(mo.score) }}</strong></span>
                            <span>Conf: <strong>{{ fmt(mo.confidence) }}</strong></span>
                          </div>
                          <div v-if="mo.rationale" class="detail-model-rationale">
                            {{ mo.rationale }}
                          </div>
                          <div v-if="mo.pico_assessment || mo.element_assessment" class="detail-elements">
                            <div
                              v-for="(assess, elemKey) in (mo.element_assessment || mo.pico_assessment || {})"
                              :key="elemKey"
                              class="detail-element-item"
                            >
                              <span class="detail-element-key">{{ elemKey }}</span>
                              <span v-if="assess.match === true" class="badge badge-include" style="font-size: 0.65rem;">match</span>
                              <span v-else-if="assess.match === false" class="badge badge-exclude" style="font-size: 0.65rem;">mismatch</span>
                              <span v-else class="badge badge-unclear" style="font-size: 0.65rem;">unclear</span>
                              <span v-if="assess.evidence" class="detail-evidence">{{ assess.evidence }}</span>
                            </div>
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { apiUpload, apiPost, apiGet, decisionBadgeClass, fmtScore } from '@/api'
import CriteriaSelector from '@/components/CriteriaSelector.vue'

const steps = ['Criteria', 'Upload', 'Run', 'Results']
const currentStep = ref(1)
const sessionId = ref<string | null>(null)

// Step 2 - Upload
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
    currentStep.value = 3
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploading.value = false
  }
}

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
  if (!sessionId.value || !selectedCriteriaData.value) return
  running.value = true
  runError.value = ''
  logText.value = ''
  completedCount.value = 0
  progressPct.value = 5
  runStatus.value = 'Setting criteria…'

  try {
    // Set criteria for this screening session
    await apiPost(`/screening/criteria/${sessionId.value}`, selectedCriteriaData.value)
    runStatus.value = 'Screening in progress…'

    // Start screening
    await apiPost(`/screening/run/${sessionId.value}`, { session_id: sessionId.value, seed: 42 })
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

// Detail expansion
const expandedRow = ref<number | null>(null)
const detailLoading = ref(false)
const detailData = ref<Record<string, any> | null>(null)

async function toggleDetail(index: number) {
  if (expandedRow.value === index) {
    expandedRow.value = null
    detailData.value = null
    return
  }
  expandedRow.value = index
  detailLoading.value = true
  detailData.value = null
  try {
    detailData.value = await apiGet<Record<string, any>>(`/screening/detail/${sessionId.value}/${index}`)
  } catch {
    detailData.value = null
  } finally {
    detailLoading.value = false
  }
}

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
  selectedCriteriaId.value = null
  selectedCriteriaName.value = ''
  selectedCriteriaData.value = null
  sessionId.value = null
  selectedFile.value = null
  uploadInfo.value = null
  results.value = []
  running.value = false
  logText.value = ''
  runError.value = ''
  currentStep.value = 1
}
</script>

<style scoped>
.th-info {
  display: inline-flex;
  margin-left: 0.3rem;
  color: var(--text-secondary, #999);
  font-size: 0.7rem;
  cursor: help;
  vertical-align: middle;
}
.result-row {
  cursor: pointer;
  transition: background 0.15s;
}
.result-row:hover {
  background: rgba(139, 92, 246, 0.04);
}
.result-row.expanded {
  background: rgba(139, 92, 246, 0.06);
}
.detail-row td {
  padding: 0 !important;
  border-top: none !important;
}
.detail-panel {
  padding: 1rem 0.75rem;
  background: rgba(255, 255, 255, 0.02);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.detail-models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}
.detail-model-card {
  padding: 0.85rem;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.detail-model-card.model-error {
  border-color: rgba(239, 68, 68, 0.3);
}
.detail-model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}
.detail-model-id {
  font-weight: 600;
  font-size: 0.82rem;
}
.detail-model-error {
  font-size: 0.78rem;
  color: #ef4444;
}
.detail-model-scores {
  display: flex;
  gap: 1rem;
  font-size: 0.78rem;
  color: var(--text-secondary, #999);
  margin-bottom: 0.4rem;
}
.detail-model-rationale {
  font-size: 0.78rem;
  color: var(--text-secondary, #999);
  font-style: italic;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}
.detail-elements {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.detail-element-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
}
.detail-element-key {
  font-weight: 600;
  min-width: 80px;
  text-transform: capitalize;
}
.detail-evidence {
  color: var(--text-secondary, #999);
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}
</style>
