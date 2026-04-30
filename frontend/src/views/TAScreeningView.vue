<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Title / Abstract Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Select criteria → upload search results → run HCN screening → review decisions</p>

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

    <div v-if="currentStep < 4" class="glass-card">
      <div class="section-title"><i class="fas fa-list-check"></i> Select Criteria</div>
      <CriteriaSelector v-model="selectedCriteriaId" @select="onCriteriaSelected" />
      <div v-if="selectedCriteriaName" class="alert alert-success" style="margin-top: 0.75rem;">
        <i class="fas fa-check-circle"></i>
        Using: <strong>{{ selectedCriteriaName }}</strong>
      </div>

    </div>

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

    <div v-if="currentStep >= 3 && currentStep < 4" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Screening</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Ready to screen <strong>{{ uploadInfo?.record_count }}</strong> records
        using criteria "<strong>{{ selectedCriteriaName }}</strong>".
      </p>

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

      <div style="display:flex;align-items:center;gap:0.75rem;">
        <button class="btn btn-primary" :disabled="running" @click="doRun">
          <i v-if="running" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-play"></i>
          {{ running ? 'Screening…' : 'Start Screening' }}
        </button>
        <span style="display:flex;align-items:center;gap:0.4rem;">
          <i class="fas fa-brain" style="font-size:0.8rem;opacity:0.6;"></i>
          <select v-model="screeningReasoningEffort" class="c-select-sm" title="Reasoning effort for thinking models">
            <option value="none">Reasoning: Off</option>
            <option value="low">Reasoning: Low</option>
            <option value="medium">Reasoning: Medium</option>
            <option value="high">Reasoning: High</option>
          </select>
        </span>
      </div>
    </div>

    <div v-if="currentStep >= 4 && results.length" class="glass-card">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
        <div class="section-title" style="margin-bottom: 0;"><i class="fas fa-list-alt"></i> Results</div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" @click="exportJSON"><i class="fas fa-download"></i> JSON</button>
          <button class="btn btn-secondary btn-sm" @click="exportCSV"><i class="fas fa-download"></i> CSV</button>
          <button class="btn btn-secondary btn-sm" @click="resetAll"><i class="fas fa-redo"></i> Reset</button>
        </div>
      </div>

      <div v-if="pilotComplete" class="pilot-banner">
        <div class="pilot-banner-content">
          <div class="pilot-banner-icon"><i class="fas fa-flask"></i></div>
          <div>
            <strong>Pilot Screening Complete</strong>
            <p style="margin: 0.25rem 0 0; font-size: 0.82rem; color: var(--text-secondary);">
              Screened {{ pilotCount }} pilot papers. Review the results below and override any incorrect decisions.
              Your feedback will calibrate the AI for the remaining <strong>{{ remainingCount }}</strong> papers.
            </p>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="continuing" @click="doContinue" style="white-space: nowrap;">
          <i v-if="continuing" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-forward"></i>
          Continue Screening ({{ remainingCount }} papers)
        </button>
      </div>

      <div v-if="continuing && running" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">
            <i class="fas fa-spinner fa-spin" style="margin-right: 0.4rem;"></i>
            {{ runStatus }}
          </span>
          <span class="text-muted">{{ completedCount }} / {{ totalCount }}</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :class="{ 'progress-bar-animated': true }" :style="{ width: progressPct + '%' }"></div>
        </div>
      </div>

      <div class="summary-cards">
        <div class="summary-card summary-card--total">
          <div class="summary-card-number">{{ results.length }}</div>
          <div class="summary-card-label">Total</div>
        </div>
        <div class="summary-card summary-card--include" @click="toggleDecisionFilter('INCLUDE')">
          <div class="summary-card-number">{{ includedCount }}</div>
          <div class="summary-card-label"><i class="fas fa-check-circle"></i> Include</div>
        </div>
        <div class="summary-card summary-card--exclude" @click="toggleDecisionFilter('EXCLUDE')">
          <div class="summary-card-number">{{ excludedCount }}</div>
          <div class="summary-card-label"><i class="fas fa-times-circle"></i> Exclude</div>
        </div>
        <div class="summary-card summary-card--review" @click="toggleDecisionFilter('HUMAN_REVIEW')">
          <div class="summary-card-number">{{ reviewCount }}</div>
          <div class="summary-card-label"><i class="fas fa-user-clock"></i> Review</div>
        </div>
      </div>

      <div class="glass-section filter-panel">
        <div class="filter-panel-header">
          <div class="filter-panel-title">
            <i class="fas fa-filter"></i>
            <span>Filters</span>
          </div>
          <span class="filter-count-badge">{{ filteredResults.length }}<span class="filter-count-of"> / {{ results.length }}</span></span>
          <button v-if="hasActiveFilters" class="filter-clear-btn" @click="clearFilters"><i class="fas fa-eraser"></i> Reset</button>
        </div>
        <div class="filter-row">
          <span class="filter-row-label">Tier</span>
          <button v-for="t in [0,1,2,3]" :key="'tier'+t"
            class="ftag" :class="[`ftag--tier${t}`, { active: filterTiers.includes(t) }]"
            @click="toggleTierFilter(t)">
            <span class="ftag-dot"></span>T{{ t }}<span class="ftag-num">{{ tierCounts[t] }}</span>
          </button>
        </div>
        <div class="filter-row filter-row--search">
          <i class="fas fa-search filter-search-icon"></i>
          <input v-model="filterSearch" type="text" placeholder="Search titles..." class="filter-search-input" @click.stop />
        </div>
      </div>

      <div v-if="selectedIndices.size > 0" class="batch-bar">
        <span style="font-size: 0.82rem;">{{ selectedIndices.size }} selected</span>
        <div style="display: flex; gap: 0.4rem;">
          <button class="action-text-btn action-text-btn--include" @click="batchAction('INCLUDE')" :disabled="batchLoading">
            <i v-if="batchLoading" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-check"></i> Batch Include
          </button>
          <button class="action-text-btn action-text-btn--exclude" @click="batchAction('EXCLUDE')" :disabled="batchLoading">
            <i v-if="batchLoading" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-times"></i> Batch Exclude
          </button>
          <button class="action-text-btn" @click="selectedIndices = new Set()" style="font-size: 0.72rem;">Cancel</button>
        </div>
      </div>

      <div class="glass-section results-panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 32px;" @click.stop>
                <input type="checkbox" :checked="isAllSelected" @change="toggleSelectAll" style="cursor: pointer;" />
              </th>
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
              <th>
                Action
                <span class="th-info" @click.stop="activeTooltip = activeTooltip === 'action' ? '' : 'action'">
                  <i class="fas fa-circle-info"></i>
                  <div v-if="activeTooltip === 'action'" class="th-popover">
                    <strong>Your Decision</strong><br>
                    Override or confirm the AI screening decision.<br>
                    For HUMAN_REVIEW items, choose Include or Exclude.<br>
                    For other items, click to change the decision.<br>
                    Click Undo to revert to the original AI decision.<br>
                    Your feedback helps improve future screening accuracy.
                  </div>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="{ item: r, originalIndex: oi } in filteredResults" :key="oi">
              <tr class="result-row" :class="{ expanded: expandedRow === oi }" @click="toggleDetail(oi)">
                <td @click.stop>
                  <input type="checkbox" :checked="selectedIndices.has(oi)" @change="toggleSelect(oi)" style="cursor: pointer;" />
                </td>
                <td class="text-muted">{{ oi + 1 }}</td>
                <td style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ r.title || '(no title)' }}</td>
                <td><span :class="decisionClass(r.decision)">{{ r.decision }}</span></td>
                <td><span class="badge badge-unclear">T{{ r.tier ?? '?' }}</span></td>
                <td>{{ fmt(r.score) }}</td>
                <td>{{ fmt(r.confidence) }}</td>
                <td @click.stop>
                  <div class="action-cell">
                    <template v-if="!r.human_decision">
                      <template v-if="r.decision === 'HUMAN_REVIEW'">
                        <button class="action-text-btn action-text-btn--include" @click="submitFeedback(oi, 'INCLUDE')" :disabled="feedbackLoading === oi">
                          <i class="fas fa-check"></i> Include
                        </button>
                        <button class="action-text-btn action-text-btn--exclude" @click="submitFeedback(oi, 'EXCLUDE')" :disabled="feedbackLoading === oi">
                          <i class="fas fa-times"></i> Exclude
                        </button>
                      </template>
                      <template v-else>
                        <button class="action-text-btn action-text-btn--change" @click="submitFeedback(oi, r.decision === 'INCLUDE' ? 'EXCLUDE' : 'INCLUDE')" :disabled="feedbackLoading === oi">
                          <i v-if="feedbackLoading === oi" class="fas fa-spinner fa-spin"></i>
                          <i v-else class="fas fa-pen"></i> Change
                        </button>
                      </template>
                    </template>
                    <template v-else>
                      <span class="action-status">
                        <i class="fas fa-user-check"></i> {{ r.human_decision === 'INCLUDE' ? 'Included' : 'Excluded' }}
                      </span>
                      <button class="action-undo-btn" @click="undoFeedback(oi)" :disabled="feedbackLoading === oi">
                        Undo
                      </button>
                    </template>
                  </div>
                </td>
              </tr>
              <tr v-if="expandedRow === oi" class="detail-row">
                <td colspan="8">
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
    </div>

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
    sessionStorage.setItem('metascreener_ta_session', data.session_id)
    uploadInfo.value = data
    currentStep.value = 3
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploading.value = false
  }
}

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

const pilotComplete = ref(false)
const pilotCount = ref(0)
const remainingCount = ref(0)
const continuing = ref(false)

const running = ref(false)
const screeningReasoningEffort = ref('medium')
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
    await apiPost(`/screening/criteria/${sessionId.value}`, selectedCriteriaData.value)
    runStatus.value = 'Screening in progress…'

    await apiPost(`/screening/run/${sessionId.value}`, { session_id: sessionId.value, seed: 42, reasoning_effort: screeningReasoningEffort.value })
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
        results: Array<{ title?: string; decision: string }>; error?: string;
        pilot_count?: number; remaining_count?: number
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

      // Pilot complete: show results but don't finish — wait for user to continue
      if (data.status === 'pilot_complete') {
        clearInterval(pollTimer!)
        results.value = data.results || []
        running.value = false
        pilotComplete.value = true
        pilotCount.value = data.pilot_count || 0
        remainingCount.value = data.remaining_count || 0
        currentStep.value = 4
        return
      }

      if (data.status === 'completed' || (data.completed >= data.total && data.total > 0)) {
        clearInterval(pollTimer!)
        results.value = data.results || []
        running.value = false
        continuing.value = false
        currentStep.value = 4
        pilotComplete.value = false
      }
    } catch {
      // transient error, keep polling
    }
  }, 2000)
}

async function doContinue() {
  if (!sessionId.value) return
  continuing.value = true
  pilotComplete.value = false
  running.value = true
  runStatus.value = 'Applying learned weights and screening remaining papers…'

  try {
    await apiPost(`/screening/continue/${sessionId.value}`, {})
    startPolling()
  } catch (e: unknown) {
    runError.value = `Continue failed: ${(e as Error).message}`
    running.value = false
    continuing.value = false
  }
}

const results = ref<Array<{
  title?: string; decision: string; tier?: number; score?: number; confidence?: number;
  human_decision?: string; original_decision?: string
}>>([])

const includedCount = computed(() => results.value.filter(r => r.decision === 'INCLUDE').length)
const excludedCount = computed(() => results.value.filter(r => r.decision === 'EXCLUDE').length)
const reviewCount = computed(() => results.value.filter(r => r.decision === 'HUMAN_REVIEW').length)

// Helper: parse tier (backend may return string "2" or number 2)
function parseTier(tier: unknown): number {
  if (typeof tier === 'number') return tier
  if (typeof tier === 'string') { const n = parseInt(tier, 10); return isNaN(n) ? -1 : n }
  return -1
}

// Dashboard: tier distribution and avg confidence
const tierCounts = computed(() => {
  const counts = [0, 0, 0, 0]
  results.value.forEach(r => {
    const t = parseTier(r.tier)
    if (t >= 0 && t <= 3) counts[t]++
  })
  return counts
})
const avgConfidence = computed(() => {
  const vals = results.value.filter(r => r.confidence != null).map(r => r.confidence as number)
  if (vals.length === 0) return '—'
  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)
})

const filterTiers = ref<number[]>([])
const filterDecisions = ref<string[]>([])
const filterScoreMin = ref<number | null>(null)
const filterScoreMax = ref<number | null>(null)
const filterSearch = ref('')

function toggleTierFilter(t: number) {
  const idx = filterTiers.value.indexOf(t)
  if (idx >= 0) filterTiers.value.splice(idx, 1)
  else filterTiers.value.push(t)
}
function toggleDecisionFilter(d: string) {
  const idx = filterDecisions.value.indexOf(d)
  if (idx >= 0) filterDecisions.value.splice(idx, 1)
  else filterDecisions.value.push(d)
}
function clearFilters() {
  filterTiers.value = []
  filterDecisions.value = []
  filterScoreMin.value = null
  filterScoreMax.value = null
  filterSearch.value = ''
}

const hasActiveFilters = computed(() =>
  filterTiers.value.length > 0 || filterDecisions.value.length > 0 ||
  filterScoreMin.value != null || filterScoreMax.value != null || filterSearch.value !== ''
)

const filteredResults = computed(() => {
  const out: Array<{ item: typeof results.value[0]; originalIndex: number }> = []
  results.value.forEach((r, i) => {
    if (filterTiers.value.length > 0 && !filterTiers.value.includes(parseTier(r.tier))) return
    if (filterDecisions.value.length > 0 && !filterDecisions.value.includes(r.decision)) return
    if (filterScoreMin.value != null && (r.score == null || r.score < filterScoreMin.value)) return
    if (filterScoreMax.value != null && (r.score == null || r.score > filterScoreMax.value)) return
    if (filterSearch.value) {
      const q = filterSearch.value.toLowerCase()
      const title = (r.title || '').toLowerCase()
      if (!title.includes(q)) return
    }
    out.push({ item: r, originalIndex: i })
  })
  return out
})

const selectedIndices = ref<Set<number>>(new Set())
const batchLoading = ref(false)

const isAllSelected = computed(() => {
  if (filteredResults.value.length === 0) return false
  return filteredResults.value.every(({ originalIndex }) => selectedIndices.value.has(originalIndex))
})

function toggleSelectAll() {
  if (isAllSelected.value) {
    filteredResults.value.forEach(({ originalIndex }) => selectedIndices.value.delete(originalIndex))
  } else {
    filteredResults.value.forEach(({ originalIndex }) => selectedIndices.value.add(originalIndex))
  }
  selectedIndices.value = new Set(selectedIndices.value)
}

function toggleSelect(index: number) {
  if (selectedIndices.value.has(index)) selectedIndices.value.delete(index)
  else selectedIndices.value.add(index)
  selectedIndices.value = new Set(selectedIndices.value)
}

async function batchAction(decision: string) {
  if (!sessionId.value || selectedIndices.value.size === 0) return
  batchLoading.value = true
  try {
    const items = Array.from(selectedIndices.value).map(idx => ({
      record_index: idx,
      decision,
    }))
    const resp = await apiPost<{ applied: Array<{ record_index: number; old_decision: string; new_decision: string }> }>(
      `/screening/batch-feedback/${sessionId.value}`,
      { items }
    )
    resp.applied.forEach(a => {
      if (results.value[a.record_index]) {
        if (!results.value[a.record_index].original_decision) {
          results.value[a.record_index].original_decision = a.old_decision
        }
        results.value[a.record_index].decision = a.new_decision
        results.value[a.record_index].human_decision = a.new_decision
      }
    })
    selectedIndices.value = new Set()
  } catch (e: unknown) {
    alert(`Batch feedback failed: ${(e as Error).message}`)
  } finally {
    batchLoading.value = false
  }
}

function decisionClass(d: string) { return decisionBadgeClass(d) }
function fmt(v: unknown) { return fmtScore(v) }

// Feedback / user override
const feedbackLoading = ref<number | null>(null)

async function submitFeedback(index: number, decision: string) {
  if (!sessionId.value) return
  feedbackLoading.value = index
  try {
    const resp = await apiPost<{ new_decision: string; old_decision: string; n_feedback: number }>(
      `/screening/feedback/${sessionId.value}`,
      { record_index: index, decision }
    )
    if (results.value[index]) {
      if (!results.value[index].original_decision) {
        results.value[index].original_decision = resp.old_decision
      }
      results.value[index].decision = resp.new_decision
      results.value[index].human_decision = resp.new_decision
    }
  } catch (e: unknown) {
    alert(`Feedback failed: ${(e as Error).message}`)
  } finally {
    feedbackLoading.value = null
  }
}

async function undoFeedback(index: number) {
  const r = results.value[index]
  if (!r || !r.original_decision || !sessionId.value) return
  feedbackLoading.value = index
  try {
    await apiPost(`/screening/undo-feedback/${sessionId.value}`, {
      record_index: index,
      decision: r.original_decision,
    })
    r.decision = r.original_decision
    r.human_decision = undefined
    r.original_decision = undefined
  } catch (e: unknown) {
    alert(`Undo failed: ${(e as Error).message}`)
  } finally {
    feedbackLoading.value = null
  }
}

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
  sessionStorage.removeItem('metascreener_ta_session')
  selectedFile.value = null
  uploadInfo.value = null
  results.value = []
  running.value = false
  logText.value = ''
  runError.value = ''
  currentStep.value = 1
  pilotComplete.value = false
  pilotCount.value = 0
  remainingCount.value = 0
  continuing.value = false
}

// Load results from history if navigated from HistoryView
onMounted(async () => {
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

  // Restore active session on page refresh
  const savedSessionId = sessionStorage.getItem('metascreener_ta_session')
  if (savedSessionId && !stored) {
    try {
      const data = await apiGet<{
        status: string; total: number; completed: number;
        results: Array<{ title?: string; decision: string }>;
        pilot_count?: number; remaining_count?: number
      }>(`/screening/results/${savedSessionId}`)

      if (data.status === 'pilot_complete' && data.results?.length) {
        sessionId.value = savedSessionId
        results.value = data.results
        currentStep.value = 4
        pilotComplete.value = true
        pilotCount.value = data.pilot_count || 0
        remainingCount.value = data.remaining_count || 0
        selectedCriteriaName.value = 'Restored session'
      } else if (data.status === 'completed' && data.results?.length) {
        sessionId.value = savedSessionId
        results.value = data.results
        currentStep.value = 4
        selectedCriteriaName.value = 'Restored session'
      }
    } catch {
      sessionStorage.removeItem('metascreener_ta_session')
    }
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
.action-cell {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  white-space: nowrap;
}
.action-text-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: var(--text-secondary, #999);
  cursor: pointer;
  font-size: 0.72rem;
  transition: all 0.15s;
}
.action-text-btn:hover { background: rgba(255,255,255,0.08); }
.action-text-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-text-btn--include:hover {
  border-color: rgba(16,185,129,0.4);
  color: #10b981;
  background: rgba(16,185,129,0.08);
}
.action-text-btn--exclude:hover {
  border-color: rgba(239,68,68,0.4);
  color: #ef4444;
  background: rgba(239,68,68,0.08);
}
.action-text-btn--change:hover {
  border-color: rgba(245,158,11,0.4);
  color: #f59e0b;
  background: rgba(245,158,11,0.08);
}
.action-status {
  font-size: 0.72rem;
  color: var(--primary-purple, #8b5cf6);
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
.action-undo-btn {
  font-size: 0.68rem;
  color: var(--text-secondary, #999);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
.action-undo-btn:hover { color: var(--text-primary, #fff); }
.action-undo-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pilot-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(139,92,246,0.08) 0%, rgba(6,182,212,0.06) 100%);
  border: 1px solid rgba(139,92,246,0.2);
}
.pilot-banner-content {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}
.pilot-banner-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(139,92,246,0.12);
  color: var(--primary-purple, #8b5cf6);
  font-size: 1rem;
  flex-shrink: 0;
}

/* ── Summary Cards ── */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.summary-card {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 1rem 0.5rem;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.03);
  cursor: pointer;
  transition: all 0.2s;
}
.summary-card:hover { background: rgba(255,255,255,0.06); transform: translateY(-1px); }
.summary-card-number {
  font-size: 2rem;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.summary-card-label {
  font-size: 0.75rem;
  font-weight: 600;
  margin-top: 0.35rem;
  display: flex; align-items: center; gap: 0.3rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.summary-card-label i { font-size: 0.7rem; }
.summary-card--total {
  cursor: default;
}
.summary-card--total .summary-card-number { color: var(--text-primary, #fff); }
.summary-card--total .summary-card-label { color: var(--text-secondary, #888); }
.summary-card--include .summary-card-number { color: var(--text-primary, #fff); }
.summary-card--include .summary-card-label { color: var(--text-primary, #fff); }
.summary-card--include:hover { border-color: rgba(16,185,129,0.3); background: rgba(16,185,129,0.08); }
.summary-card--include:hover .summary-card-number { color: #10b981; }
.summary-card--include:hover .summary-card-label { color: #10b981; }
.summary-card--exclude .summary-card-number { color: var(--text-primary, #fff); }
.summary-card--exclude .summary-card-label { color: var(--text-primary, #fff); }
.summary-card--exclude:hover { border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.08); }
.summary-card--exclude:hover .summary-card-number { color: #ef4444; }
.summary-card--exclude:hover .summary-card-label { color: #ef4444; }
.summary-card--review .summary-card-number { color: var(--text-primary, #fff); }
.summary-card--review .summary-card-label { color: var(--text-primary, #fff); }
.summary-card--review:hover { border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.08); }
.summary-card--review:hover .summary-card-number { color: #f59e0b; }
.summary-card--review:hover .summary-card-label { color: #f59e0b; }

/* ── Filter Panel ── */
.filter-panel {
  margin-bottom: 1.5rem;
  padding: 0 !important;
}
.filter-panel-header {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.filter-panel-title {
  display: flex; align-items: center; gap: 0.4rem;
  font-size: 0.82rem; font-weight: 600; color: var(--text-primary, #eee);
}
.filter-panel-title i { font-size: 0.75rem; opacity: 0.6; }
/* ── Results Panel ── */
.results-panel { padding: 0 !important; }
.results-panel .table-wrap { border: none; border-radius: 0; }
.results-panel thead th { border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03); }
.results-panel tbody td { border-bottom: 1px solid rgba(255,255,255,0.04); }
.results-panel tbody tr:last-child td { border-bottom: none; }
.filter-row {
  display: flex; align-items: center; gap: 0.4rem;
  padding: 0.55rem 1rem;
}
.filter-row + .filter-row {
  border-top: 1px solid rgba(255,255,255,0.04);
}
.filter-row-label {
  font-size: 0.7rem; font-weight: 600; color: var(--text-secondary, #666);
  text-transform: uppercase; letter-spacing: 0.04em;
  min-width: 56px; flex-shrink: 0;
}
.filter-count-badge {
  font-size: 0.8rem; font-weight: 700; color: var(--text-primary, #fff);
  font-variant-numeric: tabular-nums;
}
.filter-count-of { font-weight: 400; color: var(--text-secondary, #777); }
.filter-clear-btn {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.2rem 0.55rem; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08); background: transparent;
  color: var(--text-secondary, #888); cursor: pointer;
  font-size: 0.7rem; transition: all 0.15s;
}
.filter-clear-btn:hover { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.filter-clear-btn i { font-size: 0.65rem; }
/* Search row */
.filter-row--search {
  padding: 0.4rem 1rem 0.55rem;
  gap: 0.5rem;
}
.filter-search-icon { color: var(--text-secondary, #555); font-size: 0.75rem; flex-shrink: 0; }
.filter-search-input {
  flex: 1; background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
  padding: 0.3rem 0.5rem;
  color: var(--text-primary, #fff); font-size: 0.8rem; outline: none;
  backdrop-filter: blur(4px);
  transition: all 0.15s;
}
.filter-search-input:focus { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.15); }
.filter-search-input::placeholder { color: var(--text-secondary, #555); }
/* Filter tags */
.ftag {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.25rem 0.6rem; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.06); background: transparent;
  color: var(--text-secondary, #777); cursor: pointer;
  font-size: 0.72rem; transition: all 0.15s; white-space: nowrap;
}
.ftag:hover { background: rgba(255,255,255,0.04); }
.ftag .ftag-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.ftag i { font-size: 0.65rem; }
.ftag-num {
  font-size: 0.62rem; opacity: 0.45; margin-left: 0.1rem;
  font-variant-numeric: tabular-nums;
}
.ftag.active { font-weight: 600; border-color: currentColor; }
.ftag.active .ftag-num { opacity: 0.8; }
.ftag--tier0 .ftag-dot { background: #ef4444; }
.ftag--tier1 .ftag-dot { background: #10b981; }
.ftag--tier2 .ftag-dot { background: #8b5cf6; }
.ftag--tier3 .ftag-dot { background: #f59e0b; }
.ftag--tier0.active { color: #ef4444; background: rgba(239,68,68,0.08); }
.ftag--tier1.active { color: #10b981; background: rgba(16,185,129,0.08); }
.ftag--tier2.active { color: #8b5cf6; background: rgba(139,92,246,0.08); }
.ftag--tier3.active { color: #f59e0b; background: rgba(245,158,11,0.08); }
.ftag--include.active { color: #10b981; background: rgba(16,185,129,0.08); }
.ftag--exclude.active { color: #ef4444; background: rgba(239,68,68,0.08); }
.ftag--review.active { color: #f59e0b; background: rgba(245,158,11,0.08); }

/* ── Batch Bar ── */
.batch-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.6rem 1rem; margin-bottom: 0.75rem; border-radius: 10px;
  background: linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(6,182,212,0.08) 100%);
  border: 1px solid rgba(139,92,246,0.25); color: var(--text-primary, #fff);
}
</style>
