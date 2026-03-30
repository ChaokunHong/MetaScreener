<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Automated Literature Retrieval</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Configure search → retrieve from databases → deduplicate → export to screening</p>

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

    <div v-if="currentStep === 1" class="glass-card">
      <div class="section-title"><i class="fas fa-sliders"></i> Configure Search</div>

      <div class="form-group">
        <label class="form-label">Search Criteria</label>
        <CriteriaSelector v-model="selectedCriteriaId" @select="onCriteriaSelected" />
        <div v-if="selectedCriteriaName" class="alert alert-success" style="margin-top: 0.75rem; margin-bottom: 0;">
          <i class="fas fa-check-circle"></i>
          Using: <strong>{{ selectedCriteriaName }}</strong>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Databases</label>
        <div class="provider-grid">
          <label
            v-for="p in providers"
            :key="p.id"
            class="provider-card"
            :class="{ selected: selectedProviders.includes(p.id) }"
          >
            <input
              type="checkbox"
              :value="p.id"
              v-model="selectedProviders"
              style="display: none;"
            />
            <div class="provider-card-inner">
              <div class="provider-icon"><i :class="p.icon"></i></div>
              <div class="provider-info">
                <span class="provider-name">{{ p.label }}</span>
                <span v-if="p.note" class="provider-note">{{ p.note }}</span>
              </div>
              <div class="provider-check">
                <i v-if="selectedProviders.includes(p.id)" class="fas fa-check-circle" style="color: var(--primary-purple);"></i>
                <i v-else class="far fa-circle" style="color: var(--text-secondary); opacity: 0.4;"></i>
              </div>
            </div>
          </label>
        </div>

        <div v-if="selectedProviders.includes('scopus')" class="alert alert-warning" style="margin-top: 0.75rem;">
          <i class="fas fa-key"></i>
          <div style="flex: 1;">
            <div style="font-weight: 600; margin-bottom: 0.4rem;">Scopus API Key Required</div>
            <input
              v-model="scopusApiKey"
              type="text"
              class="form-control"
              placeholder="Enter your Elsevier Scopus API key"
              style="background: rgba(255,255,255,0.8);"
            />
          </div>
        </div>
      </div>

      <div v-if="startError" class="alert alert-danger">
        <i class="fas fa-exclamation-circle"></i> {{ startError }}
      </div>

      <button
        class="btn btn-primary"
        :disabled="!canStart || starting"
        @click="startSearch"
      >
        <i v-if="starting" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-search"></i>
        {{ starting ? 'Starting…' : 'Start Search' }}
      </button>
    </div>

    <div v-if="currentStep === 2" class="glass-card">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
        <div class="section-title" style="margin-bottom: 0;">
          <i class="fas fa-satellite-dish"></i>
          {{ currentPhase === 'searching' ? 'Searching Databases' : currentPhase === 'deduplicating' ? 'Deduplicating Records' : currentPhase === 'downloading' ? 'Downloading PDFs' : 'Processing' }}
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <span class="badge" :class="statusBadgeClass">{{ searchStatus }}</span>
          <button
            v-if="searchStatus === 'running'"
            class="btn btn-secondary btn-sm"
            @click="stopSearch"
            style="font-size: 0.75rem; padding: 0.25rem 0.75rem;"
          >
            <i class="fas fa-stop"></i> Stop
          </button>
        </div>
      </div>

      <div style="margin-bottom: 1.5rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted" style="font-size: 0.85rem;">Overall progress</span>
          <span class="text-muted" style="font-size: 0.85rem;">{{ completedProviders }} / {{ selectedProviders.length }} databases</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: overallProgressPct + '%' }"></div>
        </div>
      </div>

      <div class="provider-progress-grid">
        <div
          v-for="p in activeProviders"
          :key="p.id"
          class="provider-progress-card"
          :class="providerCardClass(p.id)"
        >
          <div class="ppc-header">
            <i :class="p.icon" style="opacity: 0.7;"></i>
            <span class="ppc-name">{{ p.label }}</span>
            <span v-if="providerDone(p.id)" class="ppc-status">
              <i class="fas fa-check-circle" style="color: #10b981;"></i>
            </span>
            <span v-else-if="currentProvider === p.id" class="ppc-status">
              <i class="fas fa-spinner fa-spin" style="color: var(--primary-purple);"></i>
            </span>
            <span v-else class="ppc-status">
              <i class="fas fa-clock" style="color: var(--text-secondary); opacity: 0.4;"></i>
            </span>
          </div>
          <div class="ppc-count">
            <template v-if="searchCounts[p.id] !== undefined">
              <span class="ppc-num">{{ searchCounts[p.id].toLocaleString() }}</span>
              <span class="ppc-label">records found</span>
            </template>
            <span v-else class="ppc-label">Searching…</span>
          </div>
        </div>
      </div>

      <div class="log-panel" ref="logPanelEl">
        <div v-for="(entry, i) in logEntries" :key="i" class="log-entry">
          <span class="log-time">{{ entry.time }}</span>
          <span class="log-msg">{{ entry.msg }}</span>
        </div>
        <div v-if="logEntries.length === 0" class="log-entry" style="opacity: 0.5;">
          <span class="log-msg">Waiting for updates…</span>
        </div>
      </div>

      <div v-if="searchError" class="alert alert-danger" style="margin-top: 1rem;">
        <i class="fas fa-exclamation-circle"></i> {{ searchError }}
      </div>
    </div>

    <div v-if="currentStep >= 3 && dedupResult" class="glass-card">
      <div class="section-title"><i class="fas fa-layer-group"></i> Deduplication Summary</div>

      <div class="dedup-totals">
        <div class="dedup-stat">
          <div class="dedup-stat-num">{{ totalFound.toLocaleString() }}</div>
          <div class="dedup-stat-label">Total Found</div>
        </div>
        <div class="dedup-arrow"><i class="fas fa-arrow-right"></i></div>
        <div class="dedup-stat dedup-stat--after">
          <div class="dedup-stat-num">{{ dedupCount.toLocaleString() }}</div>
          <div class="dedup-stat-label">After Dedup</div>
        </div>
        <div class="dedup-reduction" v-if="totalFound > 0">
          <span class="reduction-badge">-{{ reductionPct }}% duplicates removed</span>
        </div>
      </div>

      <div class="dedup-layers" v-if="dedupResult.per_layer_counts">
        <div class="dedup-layers-title">Removed per deduplication layer</div>
        <div v-for="layer in dedupLayers" :key="layer.key" class="dedup-layer-row">
          <div class="dedup-layer-label">{{ layer.label }}</div>
          <div class="dedup-layer-bar-wrap">
            <div
              class="dedup-layer-bar"
              :style="{ width: layerBarWidth(layer.key) + '%' }"
            ></div>
          </div>
          <div class="dedup-layer-count">{{ (dedupResult.per_layer_counts[layer.key] || 0).toLocaleString() }}</div>
        </div>
      </div>

      <div style="margin-top: 1rem;">
        <button class="btn btn-secondary btn-sm" @click="showMergeLog = !showMergeLog">
          <i class="fas fa-list-ul"></i>
          {{ showMergeLog ? 'Hide Merge Log' : 'View Merge Log' }}
          <i :class="showMergeLog ? 'fas fa-chevron-up' : 'fas fa-chevron-down'" style="font-size: 0.65rem;"></i>
        </button>
        <div v-if="showMergeLog && dedupResult.merge_log" class="merge-log">
          <div v-for="(entry, i) in dedupResult.merge_log.slice(0, 50)" :key="i" class="merge-log-entry">
            <span class="merge-log-layer">{{ entry.layer }}</span>
            <span class="merge-log-msg">{{ entry.message || entry }}</span>
          </div>
          <div v-if="dedupResult.merge_log.length > 50" class="merge-log-entry" style="opacity: 0.5;">
            … {{ dedupResult.merge_log.length - 50 }} more entries
          </div>
        </div>
      </div>

      <div style="margin-top: 1.25rem;">
        <button class="btn btn-primary" @click="currentStep = 4">
          <i class="fas fa-table"></i> View Results ({{ dedupCount.toLocaleString() }} records)
        </button>
      </div>
    </div>

    <div v-if="currentStep >= 4 && records.length > 0" class="glass-card">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
        <div class="section-title" style="margin-bottom: 0;">
          <i class="fas fa-table"></i> Deduplicated Records
          <span class="badge badge-include" style="margin-left: 0.75rem;">{{ records.length.toLocaleString() }}</span>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" @click="exportCSV">
            <i class="fas fa-download"></i> Export CSV
          </button>
          <button class="btn btn-primary btn-sm" :disabled="sending" @click="sendToScreening">
            <i v-if="sending" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-filter"></i>
            {{ sending ? 'Sending…' : 'Send to Screening' }}
          </button>
        </div>
      </div>

      <div class="results-search-row">
        <i class="fas fa-search results-search-icon"></i>
        <input
          v-model="recordSearch"
          type="text"
          class="results-search-input"
          placeholder="Filter by title, author, or journal…"
        />
        <span class="results-search-count">{{ filteredRecords.length.toLocaleString() }} / {{ records.length.toLocaleString() }}</span>
      </div>

      <div class="table-wrap" style="margin-top: 0.75rem;">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              <th>Authors</th>
              <th>Year</th>
              <th>Journal</th>
              <th>Sources</th>
              <th>DOI</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(rec, i) in paginatedRecords" :key="i">
              <td style="color: var(--text-secondary); font-size: 0.78rem;">{{ recordOffset + i + 1 }}</td>
              <td style="max-width: 320px;">
                <a v-if="rec.doi" :href="`https://doi.org/${rec.doi}`" target="_blank" class="record-title-link">
                  {{ rec.title || '—' }}
                </a>
                <span v-else>{{ rec.title || '—' }}</span>
              </td>
              <td style="font-size: 0.78rem; color: var(--text-secondary); max-width: 180px;">{{ formatAuthors(rec.authors) }}</td>
              <td style="font-size: 0.82rem; white-space: nowrap;">{{ rec.year || '—' }}</td>
              <td style="font-size: 0.78rem; color: var(--text-secondary); max-width: 160px;">{{ rec.journal || '—' }}</td>
              <td>
                <div style="display: flex; flex-wrap: wrap; gap: 0.2rem;">
                  <span v-for="src in (rec.sources || [])" :key="src" class="source-badge">{{ src }}</span>
                </div>
              </td>
              <td style="font-size: 0.72rem; color: var(--text-secondary);">
                <a v-if="rec.doi" :href="`https://doi.org/${rec.doi}`" target="_blank" style="color: inherit;">
                  {{ rec.doi }}
                </a>
                <span v-else>—</span>
              </td>
            </tr>
            <tr v-if="filteredRecords.length === 0">
              <td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-secondary);">No matching records</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="pagination-row">
        <button class="btn btn-secondary btn-sm" :disabled="currentPage === 1" @click="currentPage--">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span style="font-size: 0.82rem; color: var(--text-secondary);">
          Page {{ currentPage }} of {{ totalPages }}
        </span>
        <button class="btn btn-secondary btn-sm" :disabled="currentPage === totalPages" @click="currentPage++">
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </div>

    <div v-if="currentStep >= 3" style="margin-top: 1rem; text-align: center;">
      <button class="btn btn-secondary btn-sm" @click="resetAll">
        <i class="fas fa-redo"></i> New Search
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPost } from '@/api'
import CriteriaSelector from '@/components/CriteriaSelector.vue'

const emit = defineEmits<{
  alert: [message: string, type?: 'success' | 'danger' | 'warning' | 'info']
}>()

const router = useRouter()

const steps = ['Configure', 'Progress', 'Dedup Summary', 'Results']
const currentStep = ref(1)

const selectedCriteriaId = ref<string | null>(null)
const selectedCriteriaName = ref('')
const selectedCriteriaData = ref<Record<string, unknown> | null>(null)
const enableDownload = ref(false)
const enableOcr = ref(false)
const scopusApiKey = ref('')
const starting = ref(false)
const startError = ref('')

interface Provider {
  id: string
  label: string
  icon: string
  note?: string
  defaultOn: boolean
}

const providers: Provider[] = [
  { id: 'pubmed',           label: 'PubMed',           icon: 'fas fa-dna',          defaultOn: true  },
  { id: 'openalex',        label: 'OpenAlex',          icon: 'fas fa-globe',         defaultOn: true  },
  { id: 'europepmc',       label: 'Europe PMC',        icon: 'fas fa-flask',         defaultOn: true  },
  { id: 'scopus',          label: 'Scopus',            icon: 'fas fa-book',          defaultOn: false, note: 'Requires API key' },
  { id: 'semantic_scholar',label: 'Semantic Scholar',  icon: 'fas fa-brain',         defaultOn: false },
]

const selectedProviders = ref<string[]>(
  providers.filter(p => p.defaultOn).map(p => p.id)
)

function onCriteriaSelected(item: { id: string; name: string; [key: string]: unknown }) {
  selectedCriteriaName.value = item.name
  selectedCriteriaData.value = item as Record<string, unknown>
}

const canStart = computed(() =>
  selectedCriteriaId.value !== null && selectedProviders.value.length > 0
)

const sessionId = ref<string | null>(null)
const searchStatus = ref<'running' | 'completed' | 'failed' | ''>('')
const searchCounts = ref<Record<string, number>>({})
const totalFound = ref(0)
const dedupCount = ref(0)
const searchError = ref('')
const logEntries = ref<{ time: string; msg: string }[]>([])
const logPanelEl = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

interface SearchStatus {
  session_id: string
  status: 'running' | 'completed' | 'failed'
  phase: string
  current_provider: string | null
  search_counts: Record<string, number>
  total_found: number
  dedup_count: number
  error?: string
}

const currentPhase = ref('searching')
const currentProvider = ref<string | null>(null)

const activeProviders = computed(() =>
  providers.filter(p => selectedProviders.value.includes(p.id))
)

const completedProviders = computed(() =>
  Object.keys(searchCounts.value).length
)

const overallProgressPct = computed(() => {
  if (selectedProviders.value.length === 0) return 0
  if (searchStatus.value === 'completed') return 100
  return Math.round((completedProviders.value / selectedProviders.value.length) * 100)
})

const statusBadgeClass = computed(() => {
  if (searchStatus.value === 'completed') return 'badge badge-include'
  if (searchStatus.value === 'failed') return 'badge badge-exclude'
  return 'badge badge-review'
})

function providerDone(id: string) {
  return id in searchCounts.value
}

function providerCardClass(id: string) {
  if (providerDone(id)) return 'ppc--done'
  if (currentProvider.value === id) return 'ppc--active'
  return 'ppc--waiting'
}

function addLog(msg: string) {
  const now = new Date()
  const time = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  logEntries.value.push({ time, msg })
  nextTick(() => {
    if (logPanelEl.value) {
      logPanelEl.value.scrollTop = logPanelEl.value.scrollHeight
    }
  })
}

async function startSearch() {
  startError.value = ''
  if (!canStart.value) return

  starting.value = true
  try {
    const body: Record<string, unknown> = {
      criteria_id: selectedCriteriaId.value,
      providers: selectedProviders.value,
      enable_download: false,
      enable_ocr: false,
    }
    if (selectedProviders.value.includes('scopus') && scopusApiKey.value) {
      body.scopus_api_key = scopusApiKey.value
    }

    const resp = await apiPost<{ session_id: string }>('/retrieval/search', body)
    sessionId.value = resp.session_id
    sessionStorage.setItem('retrieval_session_id', resp.session_id)

    currentStep.value = 2
    searchStatus.value = 'running'
    logEntries.value = []
    addLog('Search started')
    startPolling()
  } catch (e: unknown) {
    startError.value = (e as Error).message || 'Failed to start search'
  } finally {
    starting.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!sessionId.value) return
    try {
      const status = await apiGet<SearchStatus>(`/retrieval/search/${sessionId.value}`)
      searchStatus.value = status.status
      currentPhase.value = status.phase || 'searching'
      currentProvider.value = status.current_provider || null

      if (status.phase === 'deduplicating' && currentPhase.value !== 'deduplicating') {
        addLog('All providers done. Deduplicating records…')
      }
      if (status.phase === 'downloading') {
        addLog('Downloading PDFs…')
      }

      if (status.search_counts) {
        const prev = { ...searchCounts.value }
        searchCounts.value = status.search_counts
        for (const [db, count] of Object.entries(status.search_counts)) {
          if (!(db in prev)) {
            const p = providers.find(x => x.id === db)
            addLog(`${p?.label || db}: ${count.toLocaleString()} records retrieved`)
          }
        }
      }

      if (status.current_provider && !providerDone(status.current_provider)) {
        const p = providers.find(x => x.id === status.current_provider)
        if (p) {
          // Only log once per provider
          const alreadyLogged = logEntries.value.some(e => e.msg.includes(`Searching ${p.label}`))
          if (!alreadyLogged) {
            addLog(`Searching ${p.label}…`)
          }
        }
      }

      if (status.total_found !== undefined) totalFound.value = status.total_found
      if (status.dedup_count !== undefined) dedupCount.value = status.dedup_count

      if (status.status === 'completed') {
        addLog(`Search complete — ${status.total_found?.toLocaleString()} found, ${status.dedup_count?.toLocaleString()} after dedup`)
        stopPolling()
        await loadResults()
      } else if (status.status === 'failed') {
        searchError.value = status.error || 'Search failed'
        addLog(`Error: ${searchError.value}`)
        stopPolling()
      }
    } catch {
      // network hiccup — keep polling
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function stopSearch() {
  stopPolling()
  if (sessionId.value) {
    try {
      await apiPost(`/retrieval/stop/${sessionId.value}`)
    } catch {
      // ignore — session may already be done
    }
  }
  searchStatus.value = 'completed'
  addLog('Search stopped by user')
  try {
    await loadResults()
  } catch {
    currentStep.value = 3
  }
}

interface DedupResult {
  per_layer_counts?: Record<string, number>
  merge_log?: Array<{ layer: string; message: string } | string>
}

interface RetrievalRecord {
  title?: string
  authors?: string | string[]
  year?: number | string
  journal?: string
  doi?: string
  sources?: string[]
  [key: string]: unknown
}

interface RetrievalResults {
  session_id: string
  status: string
  result: {
    search_counts?: Record<string, number>
    total_found?: number
    dedup_count?: number
    downloaded?: number
    download_failed?: number
    ocr_completed?: number
    records: RetrievalRecord[]
    dedup_result?: DedupResult
  }
}

const dedupResult = ref<DedupResult | null>(null)
const records = ref<RetrievalRecord[]>([])
const showMergeLog = ref(false)
const sending = ref(false)

const dedupLayers = [
  { key: 'doi',        label: 'DOI match' },
  { key: 'pmid',       label: 'PubMed ID' },
  { key: 'pmcid',      label: 'PMC ID' },
  { key: 'external_id',label: 'External ID' },
  { key: 'title_year', label: 'Title + Year' },
  { key: 'semantic',   label: 'Semantic similarity' },
]

const reductionPct = computed(() => {
  if (totalFound.value === 0) return 0
  return Math.round(((totalFound.value - dedupCount.value) / totalFound.value) * 100)
})

function layerBarWidth(key: string): number {
  if (!dedupResult.value?.per_layer_counts || totalFound.value === 0) return 0
  const count = dedupResult.value.per_layer_counts[key] || 0
  const max = Math.max(...Object.values(dedupResult.value.per_layer_counts), 1)
  return Math.round((count / max) * 100)
}

async function loadResults() {
  if (!sessionId.value) return
  try {
    const res = await apiGet<RetrievalResults>(`/retrieval/results/${sessionId.value}`)
    if (res.result) {
      records.value = res.result.records || []
      dedupResult.value = res.result.dedup_result || null
      if (res.result.total_found !== undefined) totalFound.value = res.result.total_found
      if (res.result.dedup_count !== undefined) dedupCount.value = res.result.dedup_count
    }
    currentStep.value = 3
  } catch (e: unknown) {
    searchError.value = (e as Error).message || 'Failed to load results'
    emit('alert', searchError.value, 'danger')
  }
}

const recordSearch = ref('')
const currentPage = ref(1)
const pageSize = 25

const filteredRecords = computed(() => {
  const q = recordSearch.value.toLowerCase().trim()
  if (!q) return records.value
  return records.value.filter(r => {
    const title = (r.title || '').toLowerCase()
    const journal = (r.journal || '').toLowerCase()
    const authors = Array.isArray(r.authors) ? r.authors.join(' ').toLowerCase() : (r.authors || '').toLowerCase()
    return title.includes(q) || journal.includes(q) || authors.includes(q)
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / pageSize)))

const recordOffset = computed(() => (currentPage.value - 1) * pageSize)

const paginatedRecords = computed(() =>
  filteredRecords.value.slice(recordOffset.value, recordOffset.value + pageSize)
)

function formatAuthors(authors: string | string[] | undefined): string {
  if (!authors) return '—'
  const list = Array.isArray(authors) ? authors : [authors]
  if (list.length <= 3) return list.join(', ')
  return list.slice(0, 3).join(', ') + ` et al.`
}

function exportCSV() {
  const headers = ['Title', 'Authors', 'Year', 'Journal', 'Sources', 'DOI']
  const rows = filteredRecords.value.map(r => [
    `"${(r.title || '').replace(/"/g, '""')}"`,
    `"${formatAuthors(r.authors).replace(/"/g, '""')}"`,
    r.year || '',
    `"${(r.journal || '').replace(/"/g, '""')}"`,
    (r.sources || []).join(';'),
    r.doi || '',
  ])
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `retrieval_${sessionId.value || 'results'}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function sendToScreening() {
  sending.value = true
  try {
    sessionStorage.setItem('retrieval_records', JSON.stringify(records.value))
    sessionStorage.setItem('retrieval_criteria_id', selectedCriteriaId.value || '')
    router.push('/screening')
  } catch (e: unknown) {
    emit('alert', (e as Error).message || 'Failed to send to screening', 'danger')
  } finally {
    sending.value = false
  }
}

function resetAll() {
  stopPolling()
  currentStep.value = 1
  sessionId.value = null
  searchStatus.value = ''
  searchCounts.value = {}
  totalFound.value = 0
  dedupCount.value = 0
  searchError.value = ''
  logEntries.value = []
  records.value = []
  dedupResult.value = null
  recordSearch.value = ''
  currentPage.value = 1
  showMergeLog.value = false
  startError.value = ''
  sessionStorage.removeItem('retrieval_session_id')
}

onMounted(async () => {
  const savedId = sessionStorage.getItem('retrieval_session_id')
  if (!savedId) return

  // Check if the backend session still exists and what state it's in
  try {
    const status = await apiGet<SearchStatus>(`/retrieval/search/${savedId}`)
    sessionId.value = savedId

    if (status.status === 'completed') {
      // Session completed — load results directly
      searchStatus.value = 'completed'
      searchCounts.value = status.search_counts || {}
      totalFound.value = status.total_found || 0
      dedupCount.value = status.dedup_count || 0
      addLog('Previous search completed. Loading results…')
      await loadResults()
    } else if (status.status === 'running') {
      // Still running — resume polling
      currentStep.value = 2
      searchStatus.value = 'running'
      searchCounts.value = status.search_counts || {}
      totalFound.value = status.total_found || 0
      addLog('Reconnecting to running search…')
      startPolling()
    } else {
      // Failed or unknown — clear and start fresh
      sessionStorage.removeItem('retrieval_session_id')
    }
  } catch {
    // Backend doesn't know this session (e.g., server restarted) — start fresh
    sessionStorage.removeItem('retrieval_session_id')
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
/* ── Step indicator ─────────────────────────────── */
.steps { display: flex; align-items: center; gap: 0; }
.step { display: flex; align-items: center; gap: 0.45rem; flex-shrink: 0; }
.step-circle {
  width: 26px; height: 26px; border-radius: 50%;
  border: 2px solid rgba(139,92,246,0.25); background: rgba(255,255,255,0.6);
  display: flex; align-items: center; justify-content: center;
  font-size: 0.72rem; font-weight: 600; color: var(--text-secondary); transition: all 0.2s;
}
.step.active .step-circle { border-color: var(--primary-purple); background: rgba(139,92,246,0.12); color: var(--primary-purple); }
.step.done .step-circle { border-color: #10b981; background: rgba(16,185,129,0.12); color: #10b981; }
.step-label { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }
.step.active .step-label { color: var(--primary-purple); font-weight: 600; }
.step.done .step-label { color: #10b981; }
.step-line { flex: 1; height: 1px; background: rgba(139,92,246,0.15); margin: 0 0.5rem; min-width: 24px; }
.step-line.done { background: rgba(16,185,129,0.4); }

/* ── Provider selection grid ─────────────────────── */
.provider-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.6rem; }
.provider-card { border-radius: 10px; border: 1.5px solid rgba(255,255,255,0.45); background: rgba(255,255,255,0.22); cursor: pointer; transition: all 0.15s; }
.provider-card:hover { border-color: rgba(139,92,246,0.35); background: rgba(139,92,246,0.04); }
.provider-card.selected { border-color: rgba(139,92,246,0.55); background: rgba(139,92,246,0.08); }
.provider-card-inner { display: flex; align-items: center; gap: 0.6rem; padding: 0.65rem 0.85rem; }
.provider-icon { width: 28px; height: 28px; border-radius: 7px; background: rgba(139,92,246,0.1); display: flex; align-items: center; justify-content: center; font-size: 0.78rem; color: var(--primary-purple); flex-shrink: 0; }
.provider-info { flex: 1; min-width: 0; }
.provider-name { display: block; font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.provider-note { display: block; font-size: 0.7rem; color: var(--text-secondary); }
.provider-check { flex-shrink: 0; font-size: 0.95rem; }

/* ── Toggle switch ───────────────────────────────── */
.options-row { display: flex; flex-direction: column; gap: 0.85rem; }
.toggle-label { display: flex; align-items: flex-start; gap: 0.75rem; cursor: pointer; }
.toggle-switch { position: relative; width: 36px; height: 20px; border-radius: 10px; background: rgba(200,200,200,0.4); border: 1px solid rgba(200,200,200,0.5); transition: all 0.2s; flex-shrink: 0; margin-top: 2px; cursor: pointer; }
.toggle-switch.on { background: rgba(139,92,246,0.4); border-color: rgba(139,92,246,0.55); }
.toggle-thumb { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); transition: transform 0.2s; }
.toggle-switch.on .toggle-thumb { transform: translateX(16px); }
.toggle-info { display: flex; flex-direction: column; gap: 0.1rem; }
.toggle-name { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.toggle-hint { font-size: 0.75rem; color: var(--text-secondary); }

/* ── Progress bar ────────────────────────────────── */
.progress { height: 6px; border-radius: 999px; background: rgba(139,92,246,0.1); overflow: hidden; }
.progress-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--primary-purple), #c084fc); transition: width 0.4s ease; }

/* ── Provider progress cards ─────────────────────── */
.provider-progress-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.6rem; margin-bottom: 1.25rem; }
.provider-progress-card { border-radius: 10px; border: 1.5px solid rgba(255,255,255,0.45); background: rgba(255,255,255,0.22); padding: 0.75rem 0.9rem; transition: all 0.2s; }
.provider-progress-card.ppc--done { border-color: rgba(16,185,129,0.35); background: rgba(16,185,129,0.05); }
.provider-progress-card.ppc--active { border-color: rgba(139,92,246,0.5); background: rgba(139,92,246,0.08); animation: pulse-border 1.5s ease-in-out infinite; }
.provider-progress-card.ppc--waiting { border-color: rgba(255,255,255,0.08); opacity: 0.6; }
@keyframes pulse-border { 0%,100% { border-color: rgba(139,92,246,0.3); } 50% { border-color: rgba(139,92,246,0.7); } }
.ppc-header { display: flex; align-items: center; gap: 0.45rem; margin-bottom: 0.5rem; font-size: 0.75rem; color: var(--text-secondary); }
.ppc-name { flex: 1; font-weight: 500; color: var(--text-primary); font-size: 0.8rem; }
.ppc-status { font-size: 0.8rem; }
.ppc-count { display: flex; align-items: baseline; gap: 0.3rem; }
.ppc-num { font-size: 1.25rem; font-weight: 700; color: var(--primary-purple); line-height: 1; }
.ppc-label { font-size: 0.72rem; color: var(--text-secondary); }

/* ── Live log ────────────────────────────────────── */
.log-panel { height: 140px; overflow-y: auto; border-radius: 8px; border: 1px solid rgba(139,92,246,0.12); background: rgba(249,250,251,0.7); padding: 0.6rem 0.8rem; font-family: 'SF Mono', 'Fira Code', monospace; }
.log-entry { display: flex; gap: 0.75rem; font-size: 0.75rem; line-height: 1.6; }
.log-time { color: rgba(139,92,246,0.65); flex-shrink: 0; }
.log-msg { color: var(--text-primary); }

/* ── Dedup summary ───────────────────────────────── */
.dedup-totals { display: flex; align-items: center; gap: 1.25rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.dedup-stat { text-align: center; }
.dedup-stat-num { font-size: 2rem; font-weight: 700; color: var(--text-primary); line-height: 1; }
.dedup-stat--after .dedup-stat-num { color: var(--primary-purple); }
.dedup-stat-label { font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.25rem; }
.dedup-arrow { color: var(--text-secondary); font-size: 1.2rem; }
.reduction-badge { display: inline-block; padding: 0.3rem 0.75rem; border-radius: 999px; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.28); color: #065f46; font-size: 0.8rem; font-weight: 600; }
.dedup-layers { margin-bottom: 1rem; }
.dedup-layers-title { font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.75rem; }
.dedup-layer-row { display: grid; grid-template-columns: 140px 1fr 60px; align-items: center; gap: 0.75rem; margin-bottom: 0.45rem; }
.dedup-layer-label { font-size: 0.8rem; color: var(--text-secondary); text-align: right; }
.dedup-layer-bar-wrap { height: 8px; border-radius: 999px; background: rgba(139,92,246,0.08); overflow: hidden; }
.dedup-layer-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, rgba(139,92,246,0.5), rgba(192,132,252,0.7)); transition: width 0.5s ease; }
.dedup-layer-count { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); }
.merge-log { margin-top: 0.75rem; max-height: 180px; overflow-y: auto; border-radius: 8px; border: 1px solid rgba(139,92,246,0.12); background: rgba(249,250,251,0.7); padding: 0.5rem 0.75rem; }
.merge-log-entry { display: flex; gap: 0.5rem; font-size: 0.74rem; line-height: 1.7; }
.merge-log-layer { font-weight: 600; color: var(--primary-purple); flex-shrink: 0; min-width: 90px; }
.merge-log-msg { color: var(--text-secondary); }

/* ── Results table ───────────────────────────────── */
.results-search-row { display: flex; align-items: center; gap: 0.6rem; background: rgba(255,255,255,0.6); border: 1px solid rgba(203,213,224,0.6); border-radius: 8px; padding: 0.45rem 0.85rem; }
.results-search-icon { color: var(--text-secondary); font-size: 0.8rem; }
.results-search-input { flex: 1; border: none; background: none; outline: none; font-size: 0.875rem; color: var(--text-primary); font-family: inherit; }
.results-search-count { font-size: 0.75rem; color: var(--text-secondary); flex-shrink: 0; }
.table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid rgba(203,213,224,0.4); }
table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
thead th { padding: 0.65rem 0.85rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); background: rgba(249,250,251,0.8); border-bottom: 1px solid rgba(203,213,224,0.4); white-space: nowrap; }
tbody tr { border-bottom: 1px solid rgba(203,213,224,0.25); transition: background 0.1s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(139,92,246,0.03); }
tbody td { padding: 0.6rem 0.85rem; vertical-align: top; }
.record-title-link { color: var(--text-primary); text-decoration: none; font-weight: 500; line-height: 1.4; }
.record-title-link:hover { color: var(--primary-purple); text-decoration: underline; }
.source-badge { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 5px; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; background: rgba(139,92,246,0.1); color: var(--primary-purple); border: 1px solid rgba(139,92,246,0.2); white-space: nowrap; }
.pagination-row { display: flex; align-items: center; justify-content: center; gap: 0.75rem; margin-top: 1rem; }
</style>
