<template>
  <div class="extraction-view">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
      <h1 class="page-title" style="margin-bottom: 0;">Data Extraction</h1>
      <button class="btn btn-secondary btn-sm" @click="showSessions = !showSessions">
        <i class="fas fa-history"></i> Sessions
      </button>
    </div>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Upload template -> upload PDFs -> run extraction -> review results -> export</p>

    <!-- Session Manager -->
    <SessionManager
      v-if="showSessions"
      ref="sessionManagerRef"
      @resume="resumeSession"
      @new-session="startNewSession"
    />

    <!-- Step Indicator -->
    <div class="steps" style="margin-bottom: 2rem;">
      <template v-for="(s, i) in steps" :key="i">
        <div class="step" :class="{ active: currentStep === i, done: currentStep > i }">
          <div class="step-circle">
            <i v-if="currentStep > i" class="fas fa-check" style="font-size: 0.65rem;"></i>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span class="step-label">{{ s }}</span>
        </div>
        <div v-if="i < steps.length - 1" class="step-line" :class="{ done: currentStep > i }"></div>
      </template>
    </div>

    <!-- Step 1: Upload Extraction Template -->
    <div v-if="currentStep === 0" class="glass-card">
      <div class="section-title"><i class="fas fa-file-excel"></i> Upload Extraction Template</div>
      <p class="text-muted" style="margin-bottom: 1rem;">Upload an Excel template that defines the data fields to extract.</p>

      <div
        class="upload-zone"
        :class="{ dragover: draggingTemplate }"
        @click="templateInput?.click()"
        @dragover.prevent="draggingTemplate = true"
        @dragleave="draggingTemplate = false"
        @drop.prevent="onTemplateDrop"
        style="margin-bottom: 1rem;"
      >
        <input ref="templateInput" type="file" accept=".xlsx,.xls" @change="handleTemplateUpload" />
        <i class="fas fa-table zone-icon"></i>
        <div class="zone-title">{{ templateFile ? templateFile.name : 'Drop Excel template here or click to browse' }}</div>
        <div class="zone-hint">.xlsx or .xls files with field definitions</div>
      </div>

      <div v-if="uploading" class="alert alert-info">
        <i class="fas fa-spinner fa-spin"></i> Creating session and uploading template...
      </div>

      <div v-if="schemaInfo" class="alert alert-success" style="margin-bottom: 1rem;">
        <i class="fas fa-check-circle"></i>
        Schema compiled -- session <strong>{{ schemaInfo.session_id?.slice(0, 8) }}</strong>
        <div style="margin-top: 0.5rem;">
          <span v-for="sheet in schemaInfo.sheets" :key="sheet.name" class="badge-sheet">
            {{ sheet.name }}: {{ sheet.fields }} field{{ sheet.fields !== 1 ? 's' : '' }}
          </span>
        </div>
      </div>

      <!-- Schema Preview -->
      <SchemaPreview v-if="schemaDetails.length > 0" :sheets="schemaDetails" />

      <button v-if="schemaInfo" class="btn btn-primary" style="margin-top: 0.75rem;" @click="currentStep = 1">
        <i class="fas fa-arrow-right"></i> Next: Upload PDFs
      </button>
    </div>

    <!-- Step 2: Upload PDFs -->
    <div v-if="currentStep === 1" class="glass-card">
      <div class="section-title"><i class="fas fa-file-pdf"></i> Upload PDF Papers</div>

      <div
        class="upload-zone"
        :class="{ dragover: draggingPdf }"
        @click="pdfInput?.click()"
        @dragover.prevent="draggingPdf = true"
        @dragleave="draggingPdf = false"
        @drop.prevent="onPdfDrop"
        style="margin-bottom: 1rem;"
      >
        <input ref="pdfInput" type="file" accept=".pdf" multiple @change="handlePdfUpload" />
        <i class="fas fa-file-pdf zone-icon"></i>
        <div class="zone-title">{{ pdfs.length ? `${pdfs.length} PDF(s) uploaded` : 'Drop PDFs here or click to browse' }}</div>
        <div class="zone-hint">Select multiple PDF files at once</div>
      </div>

      <div v-if="uploadingPdf" class="alert alert-info">
        <i class="fas fa-spinner fa-spin"></i> Uploading PDFs... ({{ pdfs.length }} done)
      </div>

      <div v-if="pdfs.length > 0" class="pdf-list" style="margin-bottom: 1rem;">
        <div v-for="pdf in pdfs" :key="pdf.pdf_id" class="pdf-item">
          <i class="fas fa-file-pdf" style="color: #ef4444; margin-right: 0.4rem;"></i>
          {{ pdf.filename }}
          <span class="text-muted" style="font-size: 0.78rem; margin-left: 0.4rem;">({{ pdf.pdf_id.slice(0, 8) }})</span>
        </div>
      </div>

      <div style="display: flex; gap: 0.5rem;">
        <button class="btn btn-secondary" @click="currentStep = 0">
          <i class="fas fa-arrow-left"></i> Back
        </button>
        <button class="btn btn-primary" :disabled="pdfs.length === 0" @click="currentStep = 2">
          <i class="fas fa-arrow-right"></i> Next: Run Extraction
        </button>
      </div>
    </div>

    <!-- Step 3: Run Extraction -->
    <div v-if="currentStep === 2" class="glass-card">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Extraction</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        <strong>{{ pdfs.length }}</strong> PDF{{ pdfs.length !== 1 ? 's' : '' }} ready for extraction.
      </p>

      <div v-if="isRunning" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
          <span class="text-muted">Extracting data from PDFs...</span>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="text-muted">{{ Math.round(progress * 100) }}%</span>
            <button class="btn btn-danger" style="padding: 0.2rem 0.6rem; font-size: 0.8rem;" @click="cancelExtraction">
              <i class="fas fa-times"></i> Cancel
            </button>
          </div>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: progress * 100 + '%' }"></div>
        </div>
      </div>

      <div v-if="runError" class="alert alert-danger">{{ runError }}</div>

      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
        <button class="btn btn-secondary" :disabled="isRunning" @click="currentStep = 1">
          <i class="fas fa-arrow-left"></i> Back
        </button>
        <button class="btn btn-primary" :disabled="isRunning" @click="runExtraction">
          <i v-if="isRunning" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-play"></i>
          {{ isRunning ? 'Extracting...' : 'Start Extraction' }}
        </button>
        <button v-if="extractionDone" class="btn btn-success" @click="currentStep = 3; fetchAlerts()">
          <i class="fas fa-arrow-right"></i> Review Results
        </button>
      </div>

      <!-- Statistics Dashboard (shown after extraction completes) -->
      <ExtractionDashboard v-if="extractionDone" :results="results" />
    </div>

    <!-- Step 4: Results Review -->
    <div v-if="currentStep === 3" class="step-content">
      <h2 style="margin-bottom: 1rem;">Results Review</h2>

      <div class="review-layout">
        <!-- Left: PDF Viewer -->
        <div class="review-panel pdf-panel">
          <h3>PDF Viewer</h3>
          <PdfViewer
            :session-id="sessionId"
            :pdf-id="selectedPdfId"
            :evidence="selectedEvidence"
          />
        </div>

        <!-- Center: Results Table (Pivot or Flat) -->
        <div class="review-panel results-panel">
          <h3>Extraction Results</h3>
          <ExtractionPivotTable
            v-if="results.length > 0"
            :results="results"
            :selected-cell="selectedCell"
            @select-cell="selectCell"
            @save-edit="handleSaveEdit"
          />
          <div v-else class="alert alert-info">
            <i class="fas fa-info-circle"></i> No results available yet.
          </div>
        </div>

        <!-- Right: Alerts Panel -->
        <div class="review-panel alerts-panel">
          <h3>Alerts &amp; Warnings</h3>
          <div v-if="alerts.length === 0" class="no-alerts">
            <i class="fas fa-check-circle" style="color: #16a34a;"></i> No alerts
          </div>
          <div v-for="(alert, i) in alerts" :key="i" class="alert-item">
            <span class="alert-severity warning">outlier</span>
            <span>
              <strong>{{ alert.field_name }}</strong>
              <span class="text-muted" style="font-size:0.8rem;"> ({{ alert.pdf_id?.slice(0, 8) }})</span>:
              value={{ alert.value }} -- {{ alert.possible_cause }}
              <div class="text-muted" style="font-size:0.75rem;">{{ alert.suggested_action }}</div>
            </span>
          </div>
        </div>
      </div>

      <!-- Bottom: Manual Correction / Cell Details -->
      <div v-if="selectedCell" class="correction-panel">
        <h3>Cell Details</h3>
        <div class="detail-grid">
          <div><strong>Field:</strong> {{ selectedCell.field_name }}</div>
          <div><strong>Value:</strong> {{ selectedCell.value }}</div>
          <div><strong>Confidence:</strong> {{ selectedCell.confidence }}</div>
          <div><strong>Strategy:</strong> {{ selectedCell.strategy }}</div>
          <div v-if="selectedCell.evidence_json">
            <strong>Evidence:</strong> {{ parseEvidence(selectedCell.evidence_json) }}
          </div>
        </div>
        <button @click="startEdit(selectedCell)" class="btn btn-secondary" style="margin-top: 0.5rem;">
          <i class="fas fa-edit"></i> Edit Value
        </button>
      </div>

      <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
        <button class="btn btn-secondary" @click="currentStep = 2">
          <i class="fas fa-arrow-left"></i> Back
        </button>
        <button class="btn btn-primary" @click="currentStep = 4">
          <i class="fas fa-arrow-right"></i> Next: Export
        </button>
      </div>
    </div>

    <!-- Step 5: Export -->
    <div v-if="currentStep === 4" class="glass-card">
      <div class="section-title"><i class="fas fa-download"></i> Export Results</div>
      <p class="text-muted" style="margin-bottom: 1rem;">Download your extraction results in the preferred format.</p>

      <div class="export-options" style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;">
        <button class="btn btn-primary" :disabled="exporting" @click="exportResults('excel')">
          <i v-if="exporting && exportFormat === 'excel'" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-file-excel"></i>
          Export Excel
        </button>
        <button class="btn btn-secondary" :disabled="exporting" @click="exportResults('csv')">
          <i v-if="exporting && exportFormat === 'csv'" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-file-csv"></i>
          Export CSV
        </button>
        <button class="btn btn-secondary" :disabled="exporting" @click="exportResults('revman')">
          <i v-if="exporting && exportFormat === 'revman'" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-file-code"></i>
          Export RevMan XML
        </button>
        <button class="btn btn-secondary" :disabled="exporting" @click="exportResults('r_meta')">
          <i v-if="exporting && exportFormat === 'r_meta'" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-chart-bar"></i>
          Export R meta
        </button>
        <button class="btn btn-secondary" :disabled="exporting" @click="exportResults('json')">
          <i v-if="exporting && exportFormat === 'json'" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-file-code"></i>
          Export JSON
        </button>
      </div>

      <div v-if="exportPath" class="alert alert-success">
        <i class="fas fa-check-circle"></i> Exported to: <strong>{{ exportPath }}</strong>
      </div>

      <button class="btn btn-secondary" @click="currentStep = 3">
        <i class="fas fa-arrow-left"></i> Back
      </button>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="alert alert-danger" style="margin-top: 1rem;">
      <i class="fas fa-exclamation-circle"></i> {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import SchemaPreview from './extraction/SchemaPreview.vue'
import ExtractionDashboard from './extraction/ExtractionDashboard.vue'
import ExtractionPivotTable from './extraction/ExtractionPivotTable.vue'
import SessionManager from './extraction/SessionManager.vue'
import PdfViewer from './extraction/PdfViewer.vue'
import type { SchemaSheet, SchemaField } from './extraction/SchemaPreview.vue'

const API_BASE = '/api/extraction/v3'

/* -- step state -- */
const steps = ['Template', 'PDFs', 'Extract', 'Review', 'Export']
const currentStep = ref(0)

/* -- session manager -- */
const showSessions = ref(true)
const sessionManagerRef = ref<InstanceType<typeof SessionManager> | null>(null)

/* -- session -- */
const sessionId = ref('')

/* -- template upload -- */
const templateInput = ref<HTMLInputElement | null>(null)
const templateFile = ref<File | null>(null)
const draggingTemplate = ref(false)
const uploading = ref(false)

interface SchemaSheetInfo {
  name: string
  fields: number
}
interface SchemaInfo {
  session_id: string
  sheets: SchemaSheetInfo[]
}
const schemaInfo = ref<SchemaInfo | null>(null)
const schemaDetails = ref<SchemaSheet[]>([])

/* -- pdf upload -- */
const pdfInput = ref<HTMLInputElement | null>(null)
const draggingPdf = ref(false)
const uploadingPdf = ref(false)

interface PdfEntry {
  pdf_id: string
  filename: string
}
const pdfs = ref<PdfEntry[]>([])

/* -- active EventSource (closed on unmount) -- */
const activeEventSource = ref<EventSource | null>(null)

onUnmounted(() => {
  if (activeEventSource.value) {
    activeEventSource.value.close()
    activeEventSource.value = null
  }
})

/* -- extraction run -- */
const isRunning = ref(false)
const progress = ref(0)
const extractionDone = ref(false)
const runError = ref('')

/* -- results -- */
interface ResultCell {
  pdf_id: string
  field_name: string
  value: unknown
  confidence: string
  strategy: string
  evidence_json?: string
}
const results = ref<ResultCell[]>([])

/* -- review state -- */
const selectedCell = ref<ResultCell | null>(null)
const selectedEvidence = ref<any>(null)
const selectedPdfId = computed(() => {
  if (selectedCell.value) return selectedCell.value.pdf_id
  return null
})
const editingCell = ref<ResultCell | null>(null)
const editValue = ref('')
const alerts = ref<any[]>([])

function selectCell(cell: ResultCell) {
  selectedCell.value = cell
  try {
    selectedEvidence.value = JSON.parse(cell.evidence_json || '{}')
  } catch {
    selectedEvidence.value = null
  }
}

function startEdit(cell: ResultCell) {
  editingCell.value = cell
  editValue.value = String(cell.value ?? '')
}

async function handleSaveEdit(cell: ResultCell, newValue: string) {
  try {
    const resp = await fetch(
      `${API_BASE}/sessions/${sessionId.value}/results/${cell.pdf_id}/cells/${cell.field_name}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_value: newValue, reason: 'Manual correction' }),
      }
    )
    if (!resp.ok) throw new Error(`Save failed: ${resp.statusText}`)
    cell.value = newValue
  } catch (e: any) {
    error.value = e.message
  }
}

function parseEvidence(json: string): string {
  try {
    const ev = JSON.parse(json)
    return ev.sentence || ev.table_id || JSON.stringify(ev)
  } catch {
    return json
  }
}

async function fetchAlerts() {
  try {
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/alerts`)
    if (!resp.ok) {
      alerts.value = []
      return
    }
    const data = await resp.json()
    alerts.value = data.alerts || []
  } catch {
    alerts.value = []
  }
}

/* -- session management -- */
async function resumeSession(sid: string): Promise<void> {
  sessionId.value = sid
  error.value = ''
  showSessions.value = false

  // Load schema
  try {
    const schemaResp = await fetch(`${API_BASE}/sessions/${sid}/schema`)
    if (schemaResp.ok) {
      const fullSchema = await schemaResp.json()
      schemaDetails.value = parseSchemaDetails(fullSchema)
      schemaInfo.value = {
        session_id: sid,
        sheets: (fullSchema.sheets || []).map((s: any) => ({
          name: s.name ?? s.sheet_name ?? 'Sheet',
          fields: (s.fields ?? s.columns ?? []).length,
        })),
      }
    }
  } catch { /* non-fatal */ }

  // Load PDFs
  try {
    const pdfsResp = await fetch(`${API_BASE}/sessions/${sid}/pdfs`)
    if (pdfsResp.ok) {
      pdfs.value = await pdfsResp.json()
    }
  } catch { /* non-fatal */ }

  // Load results
  try {
    const resultsResp = await fetch(`${API_BASE}/sessions/${sid}/results`)
    if (resultsResp.ok) {
      const data = await resultsResp.json()
      if (data.length > 0) {
        results.value = data
        extractionDone.value = true
        currentStep.value = 3
      } else if (pdfs.value.length > 0) {
        currentStep.value = 2
      } else if (schemaInfo.value) {
        currentStep.value = 1
      } else {
        currentStep.value = 0
      }
    }
  } catch {
    currentStep.value = 0
  }
}

function startNewSession(): void {
  sessionId.value = ''
  templateFile.value = null
  schemaInfo.value = null
  schemaDetails.value = []
  pdfs.value = []
  results.value = []
  extractionDone.value = false
  selectedCell.value = null
  selectedEvidence.value = null
  currentStep.value = 0
  showSessions.value = false
  error.value = ''
  runError.value = ''
  progress.value = 0
}

/* -- export -- */
const exporting = ref(false)
const exportFormat = ref('')
const exportPath = ref('')

/* -- shared error -- */
const error = ref('')

/* -- template handlers -- */
function onTemplateDrop(e: DragEvent) {
  draggingTemplate.value = false
  const file = e.dataTransfer?.files[0]
  if (file) uploadTemplate(file)
}

async function handleTemplateUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  await uploadTemplate(input.files[0])
}

function parseSchemaDetails(raw: any): SchemaSheet[] {
  if (!raw || !raw.sheets) return []
  return (raw.sheets as any[]).map((s: any) => ({
    name: s.name ?? s.sheet_name ?? 'Sheet',
    expanded: false,
    fields: (s.fields ?? s.columns ?? []).map((f: any): SchemaField => ({
      name: f.name ?? f.field_name ?? '',
      field_type: f.field_type ?? f.type ?? 'text',
      role: f.role ?? 'data',
      required: f.required ?? false,
      semantic_tag: f.semantic_tag ?? f.tag ?? undefined,
    })),
  }))
}

async function uploadTemplate(file: File) {
  templateFile.value = file
  error.value = ''
  uploading.value = true
  try {
    // Create session
    const sessionResp = await fetch(`${API_BASE}/sessions`, { method: 'POST' })
    if (!sessionResp.ok) throw new Error(`Session creation failed: ${sessionResp.statusText}`)
    const sessionData = await sessionResp.json()
    sessionId.value = sessionData.session_id

    // Upload template
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/template`, {
      method: 'POST',
      body: formData,
    })
    if (!resp.ok) throw new Error(`Template upload failed: ${resp.statusText}`)
    const raw = await resp.json()

    // Normalise response into SchemaInfo shape
    schemaInfo.value = {
      session_id: raw.session_id ?? sessionId.value,
      sheets: Array.isArray(raw.sheets)
        ? raw.sheets.map((s: any) => ({ name: s.name ?? s.sheet_name, fields: s.fields ?? s.field_count ?? 0 }))
        : [],
    }

    // Fetch full schema details for preview
    try {
      const schemaResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/schema`)
      if (schemaResp.ok) {
        const fullSchema = await schemaResp.json()
        schemaDetails.value = parseSchemaDetails(fullSchema)
      }
    } catch {
      // Non-fatal: schema preview is optional
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}

/* -- pdf handlers -- */
function onPdfDrop(e: DragEvent) {
  draggingPdf.value = false
  const files = e.dataTransfer?.files
  if (files?.length) uploadPdfs(Array.from(files))
}

async function handlePdfUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  await uploadPdfs(Array.from(input.files))
}

async function uploadPdfs(files: File[]) {
  error.value = ''
  uploadingPdf.value = true
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/pdfs`, {
        method: 'POST',
        body: formData,
      })
      if (!resp.ok) throw new Error(`PDF upload failed for ${file.name}: ${resp.statusText}`)
      const data = await resp.json()
      pdfs.value.push({ pdf_id: data.pdf_id, filename: data.filename ?? file.name })
    } catch (e: any) {
      error.value = e.message
    }
  }
  uploadingPdf.value = false
}

/* -- extraction -- */
async function runExtraction() {
  isRunning.value = true
  extractionDone.value = false
  runError.value = ''
  error.value = ''
  progress.value = 0

  try {
    // Start extraction
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/run`, { method: 'POST' })
    if (!resp.ok) throw new Error(await resp.text())

    // Connect to SSE for real progress
    const eventSource = new EventSource(`${API_BASE}/sessions/${sessionId.value}/events`)
    activeEventSource.value = eventSource

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        progress.value = data.progress || 0
      } catch { /* ignore parse errors */ }
    }

    eventSource.addEventListener('batch_done', async () => {
      eventSource.close()
      activeEventSource.value = null
      progress.value = 1.0

      // Fetch final results
      const resultsResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/results`)
      results.value = await resultsResp.json()
      extractionDone.value = true
      isRunning.value = false
    })

    eventSource.addEventListener('pdf_done', (event) => {
      try {
        const data = JSON.parse(event.data)
        progress.value = data.progress || progress.value
      } catch { /* ignore parse errors */ }
    })

    eventSource.addEventListener('warning', (event) => {
      try {
        const data = JSON.parse(event.data)
        runError.value = data.details?.message || 'Warning from server'
      } catch { /* ignore parse errors */ }
    })

    eventSource.addEventListener('idle', () => {
      // No extraction running, poll for status
      eventSource.close()
      activeEventSource.value = null
      pollForCompletion()
    })

    eventSource.onerror = () => {
      eventSource.close()
      activeEventSource.value = null
      // Fallback: poll for completion
      pollForCompletion()
    }

  } catch (e: any) {
    runError.value = e.message
    isRunning.value = false
  }
}

async function cancelExtraction() {
  try {
    await fetch(`${API_BASE}/sessions/${sessionId.value}/cancel`, { method: 'POST' })
  } catch (e: any) {
    error.value = e.message
  } finally {
    isRunning.value = false
    progress.value = 0
    if (activeEventSource.value) {
      activeEventSource.value.close()
      activeEventSource.value = null
    }
  }
}

async function pollForCompletion() {
  // Poll session status every 2 seconds until completed
  const maxAttempts = 150  // 5 minutes
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(resolve => setTimeout(resolve, 2000))
    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}`)
      const session = await resp.json()
      if (session.status === 'completed' || session.status === 'failed') {
        const resultsResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/results`)
        results.value = await resultsResp.json()
        extractionDone.value = true
        isRunning.value = false
        progress.value = 1.0
        return
      }
    } catch { /* ignore polling errors */ }
  }
  runError.value = 'Extraction timed out'
  isRunning.value = false
}

/* -- export -- */
async function exportResults(format: string) {
  exporting.value = true
  exportFormat.value = format
  exportPath.value = ''
  error.value = ''
  try {
    // 1. Trigger server-side export
    const resp = await fetch(
      `${API_BASE}/sessions/${sessionId.value}/export?format=${format}`,
      { method: 'POST' }
    )
    if (!resp.ok) throw new Error(`Export failed: ${resp.statusText}`)
    const data = await resp.json()
    exportPath.value = data.path

    // 2. Download the file to the user's browser
    const downloadResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/download`)
    if (downloadResp.ok) {
      const blob = await downloadResp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = format === 'excel' ? 'xlsx' : format === 'revman' ? 'xml' : format === 'r_meta' ? 'csv' : format
      a.download = `extraction_export.${ext}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } else {
      // Non-fatal: server path is still shown even if browser download fails
      console.warn('download_endpoint_failed', downloadResp.status)
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    exporting.value = false
    exportFormat.value = ''
  }
}
</script>

<style scoped>
.extraction-view {
  max-width: 1100px;
  margin: 0 auto;
}

/* -- badge for sheet names -- */
.badge-sheet {
  display: inline-block;
  background: #e0f2fe;
  color: #0369a1;
  border-radius: 0.375rem;
  padding: 0.125rem 0.5rem;
  font-size: 0.8rem;
  margin-right: 0.4rem;
  margin-top: 0.25rem;
}

/* -- pdf list -- */
.pdf-list {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.pdf-item {
  padding: 0.25rem 0;
  font-size: 0.875rem;
}

/* -- danger button -- */
.btn-danger {
  background: #dc2626;
  color: white;
  border: none;
  padding: 0.45rem 1.25rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.btn-danger:hover {
  background: #b91c1c;
}

/* -- success button -- */
.btn-success {
  background: #15803d;
  color: white;
  border: none;
  padding: 0.45rem 1.25rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.btn-success:hover {
  background: #166534;
}

/* -- step content wrapper (Step 4) -- */
.step-content {
  padding: 0;
}

/* -- 3-column review layout -- */
.review-layout {
  display: grid;
  grid-template-columns: 250px 1fr 250px;
  gap: 1rem;
  min-height: 500px;
  margin-bottom: 1rem;
}

.review-panel {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1rem;
  overflow-y: auto;
  max-height: 600px;
}

.review-panel h3 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 0.5rem;
}

.pdf-panel {
  background: #f9fafb;
}

.results-panel {
  background: white;
}

.alerts-panel {
  background: #fffbeb;
}

.pdf-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  color: #6b7280;
  padding: 2rem 1rem;
  font-size: 0.875rem;
  gap: 0.5rem;
}

/* -- row selection -- */
.selected-row td {
  background: #eff6ff !important;
}

/* -- alerts panel -- */
.no-alerts {
  font-size: 0.875rem;
  color: #6b7280;
  padding: 0.5rem 0;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.alert-item {
  padding: 0.5rem 0;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.875rem;
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
}

.alert-item:last-child {
  border-bottom: none;
}

.alert-severity {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.7rem;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.alert-severity.error {
  background: #fef2f2;
  color: #b91c1c;
}

.alert-severity.warning {
  background: #fffbeb;
  color: #92400e;
}

.alert-severity.info {
  background: #eff6ff;
  color: #1d4ed8;
}

/* -- correction / detail panel -- */
.correction-panel {
  margin-top: 0.5rem;
  padding: 1rem;
  border: 1px solid #bbf7d0;
  border-radius: 0.5rem;
  background: #f0fdf4;
  margin-bottom: 1rem;
}

.correction-panel h3 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.4rem 1rem;
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
}
</style>
