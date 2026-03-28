<template>
  <div class="extraction-view">
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Data Extraction</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Upload template → upload PDFs → run extraction → review results → export</p>

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
        <i class="fas fa-spinner fa-spin"></i> Creating session and uploading template…
      </div>

      <div v-if="schemaInfo" class="alert alert-success" style="margin-bottom: 1rem;">
        <i class="fas fa-check-circle"></i>
        Schema compiled — session <strong>{{ schemaInfo.session_id?.slice(0, 8) }}</strong>
        <div style="margin-top: 0.5rem;">
          <span v-for="sheet in schemaInfo.sheets" :key="sheet.name" class="badge-sheet">
            {{ sheet.name }}: {{ sheet.fields }} field{{ sheet.fields !== 1 ? 's' : '' }}
          </span>
        </div>
      </div>

      <button v-if="schemaInfo" class="btn btn-primary" @click="currentStep = 1">
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
        <i class="fas fa-spinner fa-spin"></i> Uploading PDFs… ({{ pdfs.length }} done)
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
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">Extracting data from PDFs…</span>
          <span class="text-muted">{{ Math.round(progress * 100) }}%</span>
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
          {{ isRunning ? 'Extracting…' : 'Start Extraction' }}
        </button>
        <button v-if="extractionDone" class="btn btn-success" @click="currentStep = 3; fetchAlerts()">
          <i class="fas fa-arrow-right"></i> Review Results
        </button>
      </div>
    </div>

    <!-- Step 4: Results Review -->
    <div v-if="currentStep === 3" class="step-content">
      <h2 style="margin-bottom: 1rem;">Results Review</h2>

      <div class="review-layout">
        <!-- Left: PDF Viewer placeholder -->
        <div class="review-panel pdf-panel">
          <h3>PDF Viewer</h3>
          <div class="pdf-placeholder">
            <i class="fas fa-file-pdf" style="font-size: 2rem; margin-bottom: 0.75rem; color: #9ca3af;"></i>
            <p>PDF viewer will be integrated with pdf.js</p>
            <p v-if="selectedEvidence">
              <strong>Evidence (Page {{ selectedEvidence.page }}):</strong><br>
              {{ selectedEvidence.sentence || selectedEvidence.table_id || 'No evidence available' }}
            </p>
          </div>
        </div>

        <!-- Center: Results Table -->
        <div class="review-panel results-panel">
          <h3>Extraction Results</h3>
          <div v-if="results.length > 0" style="overflow-x: auto;">
            <table class="results-table">
              <thead>
                <tr>
                  <th>PDF</th>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Confidence</th>
                  <th>Strategy</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(cell, i) in results"
                  :key="i"
                  @click="selectCell(cell)"
                  :class="{ 'selected-row': selectedCell === cell }"
                  style="cursor: pointer;"
                >
                  <td class="text-muted" style="font-size: 0.8rem;">{{ cell.pdf_id?.slice(0, 8) }}</td>
                  <td><strong>{{ cell.field_name }}</strong></td>
                  <td>
                    <span v-if="editingCell === cell">
                      <input
                        v-model="editValue"
                        @keyup.enter="saveEdit(cell)"
                        @keyup.escape="cancelEdit"
                        class="edit-input"
                        @click.stop
                      />
                    </span>
                    <span v-else @dblclick.stop="startEdit(cell)">{{ cell.value }}</span>
                  </td>
                  <td>
                    <span :class="['confidence-badge', `confidence-${cell.confidence?.toLowerCase()}`]">
                      {{ cell.confidence }}
                    </span>
                  </td>
                  <td class="text-muted" style="font-size: 0.8rem;">{{ cell.strategy }}</td>
                </tr>
              </tbody>
            </table>
          </div>
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
            <span class="alert-severity" :class="alert.severity">{{ alert.severity }}</span>
            {{ alert.message || alert.field_name }}
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
import { ref, onUnmounted } from 'vue'

const API_BASE = '/api/extraction/v3'

/* ── step state ── */
const steps = ['Template', 'PDFs', 'Extract', 'Review', 'Export']
const currentStep = ref(0)

/* ── session ── */
const sessionId = ref('')

/* ── template upload ── */
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

/* ── pdf upload ── */
const pdfInput = ref<HTMLInputElement | null>(null)
const draggingPdf = ref(false)
const uploadingPdf = ref(false)

interface PdfEntry {
  pdf_id: string
  filename: string
}
const pdfs = ref<PdfEntry[]>([])

/* ── active EventSource (closed on unmount) ── */
const activeEventSource = ref<EventSource | null>(null)

onUnmounted(() => {
  if (activeEventSource.value) {
    activeEventSource.value.close()
    activeEventSource.value = null
  }
})

/* ── extraction run ── */
const isRunning = ref(false)
const progress = ref(0)
const extractionDone = ref(false)
const runError = ref('')

/* ── results ── */
interface ResultCell {
  pdf_id: string
  field_name: string
  value: unknown
  confidence: string
  strategy: string
  evidence_json?: string
}
const results = ref<ResultCell[]>([])

/* ── review state ── */
const selectedCell = ref<ResultCell | null>(null)
const selectedEvidence = ref<any>(null)
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

function cancelEdit() {
  editingCell.value = null
}

async function saveEdit(cell: ResultCell) {
  try {
    const resp = await fetch(
      `${API_BASE}/sessions/${sessionId.value}/results/${cell.pdf_id}/cells/${cell.field_name}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_value: editValue.value, reason: 'Manual correction' }),
      }
    )
    if (!resp.ok) throw new Error(`Save failed: ${resp.statusText}`)
    cell.value = editValue.value
    editingCell.value = null
  } catch (e: any) {
    error.value = e.message
  }
}

function parseEvidence(json: string) {
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

/* ── export ── */
const exporting = ref(false)
const exportFormat = ref('')
const exportPath = ref('')

/* ── shared error ── */
const error = ref('')

/* ── template handlers ── */
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
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}

/* ── pdf handlers ── */
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

/* ── extraction ── */
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
      } catch {}
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
      } catch {}
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
    } catch {}
  }
  runError.value = 'Extraction timed out'
  isRunning.value = false
}

/* ── export ── */
async function exportResults(format: string) {
  exporting.value = true
  exportFormat.value = format
  exportPath.value = ''
  error.value = ''
  try {
    const resp = await fetch(
      `${API_BASE}/sessions/${sessionId.value}/export?format=${format}`,
      { method: 'POST' }
    )
    if (!resp.ok) throw new Error(`Export failed: ${resp.statusText}`)
    const data = await resp.json()
    exportPath.value = data.path
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

/* ── badge for sheet names ── */
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

/* ── pdf list ── */
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

/* ── results table ── */
.results-table-container {
  overflow-x: auto;
  margin-bottom: 1rem;
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.results-table th,
.results-table td {
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
}

.results-table th {
  background: #f9fafb;
  font-weight: 600;
  white-space: nowrap;
}

.results-table tr:hover td {
  background: #f9fafb;
}

/* ── confidence badges ── */
.confidence-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.confidence-verified  { background: #15803d; color: white; }
.confidence-high      { background: #22c55e; color: white; }
.confidence-medium    { background: #eab308; color: white; }
.confidence-low       { background: #f97316; color: white; }
.confidence-single    { background: #a3a3a3; color: white; }
.confidence-failed    { background: #ef4444; color: white; }

/* ── success button ── */
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

/* ── step content wrapper (Step 4) ── */
.step-content {
  padding: 0;
}

/* ── 3-column review layout ── */
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

/* ── row selection ── */
.selected-row td {
  background: #eff6ff !important;
}

.results-table tr:hover td {
  background: #f9fafb;
}

/* ── inline edit input ── */
.edit-input {
  width: 100%;
  padding: 0.25rem 0.375rem;
  border: 1px solid #1d4ed8;
  border-radius: 0.25rem;
  font-size: 0.875rem;
  outline: none;
}

/* ── alerts panel ── */
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

/* ── correction / detail panel ── */
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
