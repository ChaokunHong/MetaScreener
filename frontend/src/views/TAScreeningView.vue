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
    <div v-if="currentStep < 4" class="glass-card">
      <div class="section-title"><i class="fas fa-list-check"></i> Select Criteria</div>
      <CriteriaSelector v-model="selectedCriteriaId" @select="onCriteriaSelected" />
      <div v-if="selectedCriteriaName" class="alert alert-success" style="margin-top: 0.75rem;">
        <i class="fas fa-check-circle"></i>
        Using: <strong>{{ selectedCriteriaName }}</strong>
      </div>

      <!-- Batch size control (below criteria selector) -->
      <div class="batch-control" v-if="selectedCriteriaName" style="margin-top: 1rem;">
        <div class="batch-header">
          <label class="form-label" style="margin-bottom: 0;">Papers per batch</label>
          <button class="info-btn" @click="showBatchModal = true" title="About batch screening">
            <i class="fas fa-circle-info"></i>
          </button>
        </div>
        <div class="batch-slider-row">
          <input type="range" v-model.number="batchSize" min="1" max="5" step="1" class="batch-slider" :style="batchSliderStyle" />
          <span class="batch-value">{{ batchSize }}</span>
        </div>
        <div class="batch-hint">
          <span v-if="batchSize === 1">Individual mode — recommended, real-time progress</span>
          <span v-else>{{ batchSize }} papers/prompt — experimental, may be slower with some models</span>
        </div>
      </div>
    </div>

    <!-- STEP 2: Upload -->
    <div v-if="currentStep >= 2 && currentStep < 4" class="glass-card">
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
    <div v-if="currentStep >= 3 && currentStep < 4" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Screening</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Ready to screen <strong>{{ uploadInfo?.record_count }}</strong> records
        using criteria "<strong>{{ selectedCriteriaName }}</strong>".
      </p>

      <!-- Progress -->
      <div v-if="running" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">
            <i class="fas fa-spinner fa-spin" style="margin-right: 0.4rem;"></i>
            {{ runStatus }}
          </span>
          <span class="text-muted">{{ completedCount }} / {{ totalCount }}</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :class="{ 'progress-bar-animated': completedCount === 0 }" :style="{ width: progressPct + '%' }"></div>
        </div>
        <div v-if="completedCount === 0" class="text-muted" style="margin-top: 0.5rem; font-size: 0.78rem;">
          <i class="fas fa-clock"></i> Waiting for models to respond... This may take 10–60 seconds.
        </div>
        <div class="progress-log" ref="logEl" style="margin-top: 0.75rem;" v-if="logText">{{ logText }}</div>
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
                <span class="th-info" @click.stop="activeTooltip = activeTooltip === 'tier' ? '' : 'tier'">
                  <i class="fas fa-circle-info"></i>
                  <div v-if="activeTooltip === 'tier'" class="th-popover">
                    <strong>Decision Tier</strong><br>
                    T0 — Rule violation → auto-exclude<br>
                    T1 — Near-unanimous agreement → auto-decision<br>
                    T2 — Majority agreement → auto-include (recall bias)<br>
                    T3 — No consensus → human review
                  </div>
                </span>
              </th>
              <th>
                Score
                <span class="th-info" @click.stop="activeTooltip = activeTooltip === 'score' ? '' : 'score'">
                  <i class="fas fa-circle-info"></i>
                  <div v-if="activeTooltip === 'score'" class="th-popover">
                    <strong>Inclusion Score</strong><br>
                    Calibrated ensemble probability (0.0–1.0).<br>
                    Weighted average of all models' scores,<br>
                    adjusted by confidence and calibration.<br>
                    Higher = more likely to be relevant.
                  </div>
                </span>
              </th>
              <th>
                Confidence
                <span class="th-info" @click.stop="activeTooltip = activeTooltip === 'confidence' ? '' : 'confidence'">
                  <i class="fas fa-circle-info"></i>
                  <div v-if="activeTooltip === 'confidence'" class="th-popover">
                    <strong>Ensemble Confidence</strong><br>
                    Agreement level among models (0.0–1.0).<br>
                    Based on Shannon entropy of decisions.<br>
                    1.0 = all models agree unanimously.<br>
                    0.0 = maximum disagreement (50/50 split).
                  </div>
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
                        class="detail-model-card glass-section"
                        :class="{ 'model-error': mo.error }"
                      >
                        <div class="detail-model-header">
                          <span class="detail-model-id">
                            <img v-if="modelIconMap[mo.model_id]" :src="modelIconMap[mo.model_id]" class="detail-model-logo" />
                            {{ mo.model_id }}
                          </span>
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

    <!-- Batch info modal (Settings-style glass panel) -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showBatchModal" class="batch-modal-overlay" @click.self="showBatchModal = false">
          <div class="batch-modal-panel">
            <div class="batch-modal-refraction"></div>
            <button class="batch-modal-close" @click="showBatchModal = false"><i class="fas fa-times"></i></button>
            <div class="batch-modal-header">
              <div class="batch-modal-icon"><i class="fas fa-layer-group"></i></div>
              <h2 class="batch-modal-title">Batch Screening</h2>
            </div>
            <p class="batch-modal-desc">Controls how many papers are grouped into a single LLM prompt. More papers per batch = fewer API calls = faster screening.</p>
            <div class="batch-modal-grid">
              <div class="batch-modal-card">
                <h3><i class="fas fa-crosshairs"></i> 1 paper / prompt</h3>
                <p>Most reliable. Each paper gets its own prompt. Use when accuracy is critical or models struggle with batch format.</p>
              </div>
              <div class="batch-modal-card">
                <h3><i class="fas fa-bolt"></i> 3–5 papers / prompt</h3>
                <p>Recommended balance of speed and reliability. Reduces API calls by 3-5×. Best for most screening tasks.</p>
              </div>
              <div class="batch-modal-card">
                <h3><i class="fas fa-rocket"></i> 6–10 papers / prompt</h3>
                <p>Fastest mode. Some models may produce incomplete JSON and automatically fall back to individual calls.</p>
              </div>
              <div class="batch-modal-card">
                <h3><i class="fas fa-shield-halved"></i> Smart fallback</h3>
                <p>If a model fails to parse the batch response, MetaScreener automatically retries each paper individually — no papers are lost.</p>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { apiUpload, apiPost, apiGet, decisionBadgeClass, fmtScore } from '@/api'
import CriteriaSelector from '@/components/CriteriaSelector.vue'

const modelIconMap: Record<string, string> = {
  'deepseek-v3': '/model_icon/deepseek.png',
  'qwen3': '/model_icon/qwen2.png',
  'kimi-k2.5': '/model_icon/moonshot.png',
  'kimi-k2': '/model_icon/moonshot.png',
  'llama4-maverick': '/model_icon/llama.png',
  'glm5-turbo': '/model_icon/chatglm-color.png',
  'mimo-v2-pro': '/model_icon/xiaomimimo.png',
  'minimax-m2.7': '/model_icon/minimax-color.png',
  'nous-hermes4': '/model_icon/nousresearch.png',
  'nvidia-nemotron': '/model_icon/nvidia-color.png',
  'cogito-671b': '/model_icon/deepcogito-color.png',
  'ai21-jamba': '/model_icon/ai21-brand-color.png',
  'gemma3-27b': '/model_icon/gemma-color.png',
  'mistral-small4': '/model_icon/mistralai.png',
  'phi4': '/model_icon/copilot-color.png',
}

const steps = ['Criteria', 'Upload', 'Run', 'Results']
const currentStep = ref(1)
const sessionId = ref<string | null>(null)
const activeTooltip = ref('')

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

// Batch size control
const batchSize = ref(1)
const showBatchModal = ref(false)

const batchSliderStyle = computed(() => {
  const pct = ((batchSize.value - 1) / 4) * 100
  return {
    background: `linear-gradient(90deg, rgba(103,210,223,0.5) 0%, rgba(167,139,250,0.45) ${pct}%, rgba(255,255,255,0.08) ${pct}%, rgba(255,255,255,0.08) 100%)`,
  }
})

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
    await apiPost(`/screening/run/${sessionId.value}`, { session_id: sessionId.value, seed: 42, batch_size: batchSize.value })
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
const localRawDecisions = ref<Record<string, any>[]>([])

async function toggleDetail(index: number) {
  if (expandedRow.value === index) {
    expandedRow.value = null
    detailData.value = null
    return
  }
  expandedRow.value = index
  detailLoading.value = true
  detailData.value = null

  // Try local raw_decisions first (from history), then API
  if (localRawDecisions.value.length > index) {
    detailData.value = localRawDecisions.value[index]
    detailLoading.value = false
    return
  }

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

// Load results from history if navigated from HistoryView
onMounted(() => {
  const stored = sessionStorage.getItem('metascreener_history_results')
  if (stored) {
    sessionStorage.removeItem('metascreener_history_results')
    try {
      const data = JSON.parse(stored)
      if (data.results && Array.isArray(data.results)) {
        results.value = data.results
        currentStep.value = 4
        selectedCriteriaName.value = 'Loaded from history'
        if (data.raw_decisions && Array.isArray(data.raw_decisions)) {
          localRawDecisions.value = data.raw_decisions
        }
      }
    } catch { /* ignore parse errors */ }
  }
})
</script>

<style scoped>
.th-info {
  display: inline-flex;
  position: relative;
  margin-left: 0.3rem;
  color: var(--text-secondary, #999);
  font-size: 0.7rem;
  cursor: pointer;
  vertical-align: middle;
}
.th-popover {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(30, 30, 45, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  font-size: 0.78rem;
  font-weight: 400;
  color: #e0e0e0;
  line-height: 1.6;
  white-space: nowrap;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  pointer-events: auto;
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
  padding: 1rem 1.25rem;
  max-height: 260px;
  overflow-y: auto;
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
  line-height: 1.45;
}
.detail-elements {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.detail-element-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.75rem;
  padding: 0.2rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.detail-element-key {
  font-weight: 600;
  min-width: 80px;
  text-transform: capitalize;
}
.detail-evidence {
  color: var(--text-secondary, #999);
  font-size: 0.72rem;
  line-height: 1.35;
  margin-top: 0.1rem;
}
.detail-model-logo {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  object-fit: contain;
  vertical-align: middle;
  margin-right: 0.35rem;
}
.progress-bar-animated {
  background-image: linear-gradient(
    45deg,
    rgba(255,255,255,0.15) 25%,
    transparent 25%,
    transparent 50%,
    rgba(255,255,255,0.15) 50%,
    rgba(255,255,255,0.15) 75%,
    transparent 75%
  );
  background-size: 1rem 1rem;
  animation: progress-stripe 1s linear infinite;
}
@keyframes progress-stripe {
  0% { background-position: 1rem 0; }
  100% { background-position: 0 0; }
}
.batch-control {
  margin-bottom: 1.25rem;
  padding: 1rem;
  border-radius: 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
}
.batch-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
}
.batch-slider-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.batch-slider {
  flex: 1;
  height: 8px;
  -webkit-appearance: none;
  appearance: none;
  border: 1px solid rgba(0,0,0,0.15);
  border-radius: 4px;
  outline: none;
}
.batch-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-purple, #8b5cf6);
  cursor: pointer;
  border: 2px solid rgba(255,255,255,0.4);
  box-shadow: 0 2px 6px rgba(139,92,246,0.35);
  margin-top: -6px;
}
.batch-slider::-webkit-slider-runnable-track {
  height: 8px;
  border-radius: 4px;
}
.batch-slider::-moz-range-track {
  height: 8px;
  border: 1px solid rgba(0,0,0,0.15);
  border-radius: 4px;
  background: transparent;
}
.batch-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary-purple, #8b5cf6);
  cursor: pointer;
  border: 2px solid rgba(255,255,255,0.4);
  box-shadow: 0 2px 6px rgba(139,92,246,0.35);
}
.batch-value {
  font-weight: 700;
  font-size: 1rem;
  color: var(--primary-purple, #8b5cf6);
  min-width: 24px;
  text-align: center;
}
.batch-hint {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-secondary, #999);
}

/* ── Batch modal (Settings-style glass) ── */
.batch-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(6px);
}
.batch-modal-panel {
  position: relative;
  width: min(640px, 92%);
  max-height: 82vh;
  overflow-y: auto;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: linear-gradient(
    145deg,
    rgba(255,255,255,0.58) 0%,
    rgba(255,255,255,0.42) 40%,
    rgba(255,255,255,0.50) 100%
  );
  -webkit-backdrop-filter: blur(40px) saturate(200%) brightness(1.15);
  backdrop-filter: blur(40px) saturate(200%) brightness(1.15);
  box-shadow:
    0 32px 80px rgba(15,23,42,0.18),
    0 12px 32px rgba(6,182,212,0.08),
    inset 0 1px 0 rgba(255,255,255,0.7);
  padding: 2rem;
  color: #1e293b;
}
.batch-modal-refraction {
  position: absolute;
  top: 0; left: 40px; right: 40px;
  height: 1.5px;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.95) 30%, rgba(255,255,255,0.95) 70%, transparent 100%);
  border-radius: 1px;
}
.batch-modal-close {
  position: absolute;
  top: 16px; right: 16px;
  width: 30px; height: 30px;
  border-radius: 50%;
  border: none;
  background: rgba(241,245,249,0.7);
  color: rgba(51,65,85,0.6);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.batch-modal-close:hover {
  color: rgba(51,65,85,0.9);
  background: rgba(255,255,255,1);
  transform: rotate(90deg);
}
.batch-modal-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
}
.batch-modal-icon {
  width: 44px; height: 44px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.1rem;
  background: rgba(139,92,246,0.12);
  color: #8b5cf6;
}
.batch-modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0;
  color: #0f172a;
}
.batch-modal-desc {
  font-size: 0.88rem;
  color: #475569;
  line-height: 1.55;
  margin: 0 0 1.25rem 0;
}
.batch-modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.batch-modal-card {
  padding: 18px 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(235, 238, 242, 0.9);
  box-shadow: 0 2px 8px rgba(15,23,42,0.05);
}
.batch-modal-card h3 {
  font-size: 0.88rem;
  font-weight: 700;
  margin: 0 0 6px 0;
  color: #1e293b;
}
.batch-modal-card h3 i {
  color: #8b5cf6;
  margin-right: 6px;
  font-size: 0.8rem;
}
.batch-modal-card p {
  font-size: 0.8rem;
  color: #64748b;
  margin: 0;
  line-height: 1.45;
}
.modal-enter-active { transition: opacity 0.2s; }
.modal-leave-active { transition: opacity 0.15s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
