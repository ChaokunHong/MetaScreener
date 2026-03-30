<template>
  <div class="extraction-view">
    <!-- Header summary bar -->
    <div class="header-bar">
      <div>
        <h1 class="page-title" style="margin-bottom: 0;">Data Extraction</h1>
        <p class="text-muted" style="margin: 0.25rem 0 0;">
          Upload template -> upload PDFs -> run extraction -> review results -> export
        </p>
      </div>
      <div class="header-meta">
        <span v-if="sessionId" class="session-badge" title="Current session ID">
          <i class="fas fa-database"></i> {{ sessionId.slice(0, 8) }}
        </span>
        <span class="step-badge">Step {{ currentStep + 1 }}/{{ steps.length }}</span>
        <button class="btn btn-secondary btn-sm" @click="showSessions = !showSessions">
          <i class="fas fa-history"></i> Sessions
        </button>
      </div>
    </div>

    <SessionManager v-if="showSessions" ref="sessionManagerRef" @resume="resumeSession" @new-session="startNewSession" />

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

    <!-- Step 1: Template -->
    <div v-if="currentStep === 0" class="glass-card fade-in">
      <div class="section-title"><i class="fas fa-file-excel"></i> Upload Extraction Template</div>
      <p class="text-muted" style="margin-bottom: 1rem;">Upload an Excel template defining data fields to extract.</p>
      <div class="upload-zone" :class="{ dragover: draggingTemplate }" @click="templateInput?.click()"
        @dragover.prevent="draggingTemplate = true" @dragleave="draggingTemplate = false"
        @drop.prevent="onTemplateDrop" style="margin-bottom: 1rem;">
        <input ref="templateInput" type="file" accept=".xlsx,.xls" @change="handleTemplateUpload" />
        <i class="fas fa-table zone-icon"></i>
        <div class="zone-title">{{ templateFile ? templateFile.name : 'Drop Excel template here or click to browse' }}</div>
        <div class="zone-hint">.xlsx or .xls files with field definitions</div>
      </div>
      <div v-if="uploading" class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Creating session and uploading template...</div>
      <div v-if="schemaInfo" class="alert alert-success" style="margin-bottom: 1rem;">
        <i class="fas fa-check-circle"></i> Schema compiled -- session <strong>{{ schemaInfo.session_id?.slice(0, 8) }}</strong>
        <div style="margin-top: 0.5rem;">
          <span v-for="sheet in schemaInfo.sheets" :key="sheet.name" class="badge-sheet">{{ sheet.name }}: {{ sheet.fields }} field{{ sheet.fields !== 1 ? 's' : '' }}</span>
        </div>
      </div>
      <div v-if="loadingSchema" class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Loading schema preview...</div>
      <SchemaPreview v-if="schemaDetails.length > 0" :sheets="schemaDetails" />
      <button v-if="schemaInfo" class="btn btn-primary" style="margin-top: 0.75rem;" @click="currentStep = 1">
        <i class="fas fa-arrow-right"></i> Next: Upload PDFs
      </button>
    </div>

    <!-- Step 2: PDFs -->
    <div v-if="currentStep === 1" class="glass-card fade-in">
      <div class="section-title"><i class="fas fa-file-pdf"></i> Upload PDF Papers</div>
      <div class="upload-zone" :class="{ dragover: draggingPdf }" @click="pdfInput?.click()"
        @dragover.prevent="draggingPdf = true" @dragleave="draggingPdf = false"
        @drop.prevent="onPdfDrop" style="margin-bottom: 1rem;">
        <input ref="pdfInput" type="file" accept=".pdf" multiple @change="handlePdfUpload" />
        <i class="fas fa-file-pdf zone-icon"></i>
        <div class="zone-title">{{ pdfs.length ? `${pdfs.length} PDF(s) uploaded` : 'Drop PDFs here or click to browse' }}</div>
        <div class="zone-hint">Select multiple PDF files at once</div>
      </div>
      <div v-if="uploadingPdf" class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Uploading PDFs... ({{ pdfs.length }} done)</div>
      <div v-if="pdfs.length > 0" class="pdf-list" style="margin-bottom: 1rem;">
        <div v-for="pdf in pdfs" :key="pdf.pdf_id" class="pdf-item">
          <i class="fas fa-file-pdf" style="color: #ef4444; margin-right: 0.4rem;"></i>
          <span class="pdf-item-name">{{ pdf.filename }}</span>
          <span class="text-muted" style="font-size: 0.78rem; margin-left: 0.4rem;">({{ pdf.pdf_id.slice(0, 8) }})</span>
          <button class="btn-icon-danger" @click.stop="deletePdf(pdf.pdf_id)" title="Remove PDF"><i class="fas fa-trash"></i></button>
        </div>
      </div>
      <div v-if="pdfs.length === 0 && !uploadingPdf" class="empty-state">
        <i class="fas fa-cloud-upload-alt"></i><p>No PDFs uploaded yet. Drop files above or click to browse.</p>
      </div>
      <div style="display: flex; gap: 0.5rem;">
        <button class="btn btn-secondary" @click="currentStep = 0"><i class="fas fa-arrow-left"></i> Back</button>
        <button class="btn btn-primary" :disabled="pdfs.length === 0" @click="currentStep = 2"><i class="fas fa-arrow-right"></i> Next: Run Extraction</button>
      </div>
    </div>

    <!-- Step 3: Run -->
    <div v-if="currentStep === 2" class="glass-card fade-in">
      <div class="section-title"><i class="fas fa-play-circle"></i> Run Extraction</div>
      <p class="text-muted" style="margin-bottom: 1rem;"><strong>{{ pdfs.length }}</strong> PDF{{ pdfs.length !== 1 ? 's' : '' }} ready.</p>
      <div v-if="isRunning || extractionDone" style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">
            {{ isPaused ? 'Paused' : extractionDone ? 'Extraction complete' : 'Extracting data from PDFs\u2026' }}
          </span>
          <span class="text-muted">
            {{ completedPdfs }} / {{ pdfs.length }} PDFs &mdash; {{ Math.round(progress * 100) }}%
          </span>
        </div>
        <div class="progress"><div class="progress-bar" :style="{ width: progress * 100 + '%' }"></div></div>
        <div v-if="logLines.length > 0" ref="logEl" class="progress-log">
          <div v-for="(line, i) in logLines" :key="i">{{ line }}</div>
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
          {{ isRunning ? 'Extracting\u2026' : 'Start Extraction' }}
        </button>
        <button v-if="isRunning && !isPaused" class="btn btn-warning" @click="pauseExtraction">
          <i class="fas fa-pause"></i> Pause
        </button>
        <button v-if="isPaused" class="btn btn-primary" @click="resumeExtraction">
          <i class="fas fa-play"></i> Resume
        </button>
        <button v-if="isRunning" class="btn btn-danger" @click="cancelExtraction">
          <i class="fas fa-times"></i> Cancel
        </button>
        <button v-if="extractionDone" class="btn btn-success" @click="currentStep = 3; fetchAlerts()">
          <i class="fas fa-arrow-right"></i> Review Results
        </button>
      </div>
      <ExtractionDashboard v-if="extractionDone" :results="results" />
    </div>

    <!-- Step 4: Review -->
    <div v-if="currentStep === 3" class="step-content fade-in">
      <div v-if="loadingResults" class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Loading results...</div>

      <!-- Main results table — full width glass card -->
      <div class="glass-card" style="margin-bottom: 1rem;">
        <div class="section-title"><i class="fas fa-table"></i> Extraction Results</div>
        <ExtractionPivotTable ref="pivotTableRef" v-if="results.length > 0" :results="results" :selected-cell="selectedCell" :sheet-order="sheetOrder" :sheet-info="sheetInfo" @select-cell="selectCell" @save-edit="handleSaveEdit" />
        <div v-else class="empty-state"><i class="fas fa-table"></i><p>No results available yet.</p></div>
      </div>

      <!-- Secondary panels — side by side below results -->
      <div class="review-secondary">
        <!-- Cell Details (shown when a cell is selected) -->
        <div v-if="selectedCell" class="glass-card review-detail-card">
          <div class="section-title"><i class="fas fa-info-circle"></i> Cell Details</div>
          <div class="detail-grid">
            <div><strong>Field:</strong> {{ selectedCell.field_name }}</div>
            <div><strong>Value:</strong> {{ selectedCell.value }}</div>
            <div><strong>Confidence:</strong>
              <span :class="['confidence-badge', `confidence-${selectedCell.confidence?.toLowerCase()}`]">{{ selectedCell.confidence }}</span>
            </div>
            <div><strong>Strategy:</strong> {{ selectedCell.strategy }}</div>
          </div>
          <div v-if="selectedCell.evidence_json" style="margin-top: 0.5rem;">
            <strong>Evidence:</strong>
            <div class="evidence-box">{{ parseEvidence(selectedCell.evidence_json) }}</div>
          </div>
          <div style="display: flex; gap: 0.5rem; margin-top: 0.75rem;">
            <button @click="startEdit(selectedCell)" class="btn btn-secondary"><i class="fas fa-edit"></i> Edit Value</button>
            <button v-if="selectedPdfId" @click="showPdfDrawer = true" class="btn btn-secondary"><i class="fas fa-file-pdf"></i> View PDF</button>
          </div>
        </div>

        <!-- Alerts panel -->
        <div class="glass-card review-alerts-card">
          <div class="section-title"><i class="fas fa-bell"></i> Alerts & Warnings</div>
          <div v-if="loadingAlerts" class="text-muted" style="font-size: 0.85rem;"><i class="fas fa-spinner fa-spin"></i> Loading alerts...</div>
          <div v-else-if="alerts.length === 0" class="no-alerts"><i class="fas fa-check-circle" style="color: #16a34a;"></i> No alerts</div>
          <div v-for="(alert, i) in alerts" :key="i" class="alert-item">
            <span class="alert-severity warning">outlier</span>
            <span><strong>{{ alert.field_name }}</strong> <span class="text-muted" style="font-size:0.8rem;">({{ alert.pdf_id?.slice(0, 8) }})</span>: value={{ alert.value }} -- {{ alert.possible_cause }}
              <div class="text-muted" style="font-size:0.75rem;">{{ alert.suggested_action }}</div></span>
          </div>
        </div>
      </div>

      <!-- PDF Viewer — slide-out drawer -->
      <div v-if="showPdfDrawer" class="pdf-drawer-overlay" @click.self="showPdfDrawer = false">
        <div class="pdf-drawer">
          <div class="pdf-drawer-header">
            <h3><i class="fas fa-file-pdf"></i> PDF Viewer</h3>
            <button class="btn-icon" @click="showPdfDrawer = false"><i class="fas fa-times"></i></button>
          </div>
          <PdfViewer :session-id="sessionId" :pdf-id="selectedPdfId" :evidence="selectedEvidence" />
        </div>
      </div>

      <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
        <button class="btn btn-secondary" @click="currentStep = 2"><i class="fas fa-arrow-left"></i> Back</button>
        <button class="btn btn-primary" @click="currentStep = 4"><i class="fas fa-arrow-right"></i> Next: Export</button>
      </div>
    </div>

    <!-- Step 5: Export -->
    <div v-if="currentStep === 4" class="glass-card fade-in">
      <div class="section-title"><i class="fas fa-download"></i> Export Results</div>
      <p class="text-muted" style="margin-bottom: 1rem;">Download results in the preferred format.</p>
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;">
        <button v-for="fmt in exportFormats" :key="fmt.id" :class="['btn', fmt.primary ? 'btn-primary' : 'btn-secondary']" :disabled="exporting" @click="exportResults(fmt.id)">
          <i :class="exporting && exportFormat === fmt.id ? 'fas fa-spinner fa-spin' : fmt.icon"></i> {{ fmt.label }}
        </button>
      </div>
      <div v-if="exportPath" class="alert alert-success"><i class="fas fa-check-circle"></i> Exported to: <strong>{{ exportPath }}</strong></div>
      <button class="btn btn-secondary" @click="currentStep = 3"><i class="fas fa-arrow-left"></i> Back</button>
    </div>

    <div v-if="error" class="alert alert-danger fade-in" style="margin-top: 1rem;"><i class="fas fa-exclamation-circle"></i> {{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type CSSProperties } from 'vue'
import SchemaPreview from './extraction/SchemaPreview.vue'
import ExtractionDashboard from './extraction/ExtractionDashboard.vue'
import ExtractionPivotTable from './extraction/ExtractionPivotTable.vue'
import type { SheetInfo } from './extraction/ExtractionPivotTable.vue'
import SessionManager from './extraction/SessionManager.vue'
import PdfViewer from './extraction/PdfViewer.vue'
import { useExtraction } from '../composables/useExtraction'
import type { SchemaSheet, SchemaField } from './extraction/SchemaPreview.vue'
import type { ResultCell } from '../composables/useExtraction'

// Ref to the pivot table component — used to call startEdit on it from the parent
const pivotTableRef = ref<InstanceType<typeof ExtractionPivotTable> | null>(null)

const API_BASE = '/api/extraction/v3'
const ext = useExtraction()
const {
  sessionId, isRunning, isPaused, progress, completedPdfs, extractionDone, runError,
  results, loadingResults, pdfs, error, logLines, logEl, exporting, exportFormat,
  exportPath, runExtraction, cancelExtraction, pauseExtraction, resumeExtraction,
  exportResults, deletePdf,
} = ext

const steps = ['Template', 'PDFs', 'Extract', 'Review', 'Export']
const currentStep = ref(0)
const showSessions = ref(true)
const sessionManagerRef = ref<InstanceType<typeof SessionManager> | null>(null)

const exportFormats = [
  { id: 'filled_template', label: 'Download Filled Template', icon: 'fas fa-file-excel', primary: true },
  { id: 'excel', label: 'Export Excel', icon: 'fas fa-file-excel', primary: false },
  { id: 'csv', label: 'Export CSV', icon: 'fas fa-file-csv', primary: false },
  { id: 'revman', label: 'Export RevMan XML', icon: 'fas fa-file-code', primary: false },
  { id: 'r_meta', label: 'Export R meta', icon: 'fas fa-chart-bar', primary: false },
  { id: 'json', label: 'Export JSON', icon: 'fas fa-file-code', primary: false },
]

/* -- template upload -- */
const templateInput = ref<HTMLInputElement | null>(null)
const templateFile = ref<File | null>(null)
const draggingTemplate = ref(false)
const uploading = ref(false)
const loadingSchema = ref(false)

interface SchemaInfo { session_id: string; sheets: { name: string; fields: number }[] }
const schemaInfo = ref<SchemaInfo | null>(null)
const schemaDetails = ref<SchemaSheet[]>([])

/* -- pdf upload -- */
const pdfInput = ref<HTMLInputElement | null>(null)
const draggingPdf = ref(false)
const uploadingPdf = ref(false)

// Sheet tab order derived from schema extraction_order (Issue 3)
const sheetOrder = computed<string[]>(() =>
  schemaDetails.value
    .filter((s) => s.role === 'data' || !s.role)
    .slice()
    .sort((a, b) => (a.extraction_order ?? 0) - (b.extraction_order ?? 0))
    .map((s) => s.name)
)

// Cardinality info per sheet — passed to pivot table for many_per_study handling
const sheetInfo = computed<SheetInfo[]>(() =>
  schemaDetails.value.map((s) => ({
    name: s.name,
    cardinality: s.cardinality || 'one_per_study',
  }))
)

/* -- review layout -- */
const showPdfDrawer = ref(false)

/* legacy refs kept for backward compat — no longer drive grid layout */
const showPdfPanel = ref(true)
const showAlertsPanel = ref(true)

const reviewGridStyle = computed((): CSSProperties => {
  if (showPdfPanel.value && showAlertsPanel.value) return { gridTemplateColumns: '280px 1fr 220px' }
  if (showPdfPanel.value && !showAlertsPanel.value) return { gridTemplateColumns: '280px 1fr 36px' }
  if (!showPdfPanel.value && showAlertsPanel.value) return { gridTemplateColumns: '36px 1fr 220px' }
  return { gridTemplateColumns: '36px 1fr 36px' }
})

/* -- review state -- */
const selectedCell = ref<ResultCell | null>(null)
const selectedEvidence = ref<any>(null)
const selectedPdfId = computed(() => selectedCell.value?.pdf_id ?? null)
const editingCell = ref<ResultCell | null>(null)
const editValue = ref('')
const alerts = ref<any[]>([])
const loadingAlerts = ref(false)

function selectCell(cell: ResultCell) {
  selectedCell.value = cell
  try { selectedEvidence.value = JSON.parse(cell.evidence_json || '{}') } catch { selectedEvidence.value = null }
}
function startEdit(cell: ResultCell) {
  // Delegate into the child pivot table so its inline edit UI activates
  if (pivotTableRef.value) {
    pivotTableRef.value.startEdit(cell)
  } else {
    // Fallback: set local state (flat view edit)
    editingCell.value = cell
    editValue.value = String(cell.value ?? '')
  }
}

async function handleSaveEdit(cell: ResultCell, newValue: string) {
  try {
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/results/${cell.pdf_id}/cells/${cell.field_name}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_value: newValue, reason: 'Manual correction' }),
    })
    if (!resp.ok) throw new Error(`Save failed: ${resp.statusText}`)
    cell.value = newValue
  } catch (e: any) { error.value = e.message }
}

function parseEvidence(json: string): string {
  try { const ev = JSON.parse(json); return ev.sentence || ev.table_id || JSON.stringify(ev) } catch { return json }
}

async function fetchAlerts() {
  loadingAlerts.value = true
  try {
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/alerts`)
    if (!resp.ok) { alerts.value = []; return }
    const data = await resp.json(); alerts.value = data.alerts || []
  } catch { alerts.value = [] } finally { loadingAlerts.value = false }
}

/* -- session management -- */
function parseSchemaDetails(raw: any): SchemaSheet[] {
  if (!raw?.sheets) return []
  return (raw.sheets as any[]).map((s: any) => ({
    name: s.name ?? s.sheet_name ?? 'Sheet',
    expanded: false,
    role: s.role ?? 'data',
    cardinality: s.cardinality ?? 'one_per_study',
    extraction_order: s.extraction_order ?? 0,
    fields: (s.fields ?? s.columns ?? []).map((f: any): SchemaField => ({
      name: f.name ?? f.field_name ?? '', field_type: f.field_type ?? f.type ?? 'text',
      role: f.role ?? 'data', required: f.required ?? false, semantic_tag: f.semantic_tag ?? f.tag ?? undefined,
    })),
  }))
}

async function resumeSession(sid: string): Promise<void> {
  sessionId.value = sid; error.value = ''; showSessions.value = false; loadingSchema.value = true
  try {
    const schemaResp = await fetch(`${API_BASE}/sessions/${sid}/schema`)
    if (schemaResp.ok) {
      const full = await schemaResp.json(); schemaDetails.value = parseSchemaDetails(full)
      schemaInfo.value = { session_id: sid, sheets: (full.sheets || []).map((s: any) => ({ name: s.name ?? s.sheet_name ?? 'Sheet', fields: (s.fields ?? s.columns ?? []).length })) }
    }
  } catch { /* non-fatal */ } finally { loadingSchema.value = false }
  try { const r = await fetch(`${API_BASE}/sessions/${sid}/pdfs`); if (r.ok) pdfs.value = await r.json() } catch {}
  loadingResults.value = true
  try {
    const r = await fetch(`${API_BASE}/sessions/${sid}/results`)
    if (r.ok) { const d = await r.json(); if (d.length > 0) { results.value = d; extractionDone.value = true; currentStep.value = 3 } else if (pdfs.value.length > 0) currentStep.value = 2; else if (schemaInfo.value) currentStep.value = 1; else currentStep.value = 0 }
  } catch { currentStep.value = 0 } finally { loadingResults.value = false }
}

function startNewSession(): void {
  sessionId.value = ''; templateFile.value = null; schemaInfo.value = null; schemaDetails.value = []
  pdfs.value = []; results.value = []; extractionDone.value = false; selectedCell.value = null
  selectedEvidence.value = null; currentStep.value = 0; showSessions.value = false
  error.value = ''; runError.value = ''; progress.value = 0
}

/* -- template handlers -- */
function onTemplateDrop(e: DragEvent) { draggingTemplate.value = false; const f = e.dataTransfer?.files[0]; if (f) uploadTemplate(f) }
async function handleTemplateUpload(event: Event) { const i = event.target as HTMLInputElement; if (!i.files?.length) return; await uploadTemplate(i.files[0]) }

async function uploadTemplate(file: File) {
  templateFile.value = file; error.value = ''; uploading.value = true
  try {
    const sr = await fetch(`${API_BASE}/sessions`, { method: 'POST' }); if (!sr.ok) throw new Error(`Session creation failed: ${sr.statusText}`)
    const sd = await sr.json(); sessionId.value = sd.session_id
    const fd = new FormData(); fd.append('file', file)
    const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/template`, { method: 'POST', body: fd }); if (!resp.ok) throw new Error(`Template upload failed: ${resp.statusText}`)
    const raw = await resp.json()
    schemaInfo.value = { session_id: raw.session_id ?? sessionId.value, sheets: Array.isArray(raw.sheets) ? raw.sheets.map((s: any) => ({ name: s.name ?? s.sheet_name, fields: s.fields ?? s.field_count ?? 0 })) : [] }
    loadingSchema.value = true
    try { const r = await fetch(`${API_BASE}/sessions/${sessionId.value}/schema`); if (r.ok) schemaDetails.value = parseSchemaDetails(await r.json()) } catch {} finally { loadingSchema.value = false }
  } catch (e: any) { error.value = e.message } finally { uploading.value = false }
}

/* -- pdf handlers -- */
function onPdfDrop(e: DragEvent) { draggingPdf.value = false; const f = e.dataTransfer?.files; if (f?.length) ext.uploadPdfs(Array.from(f), uploadingPdf) }
async function handlePdfUpload(event: Event) { const i = event.target as HTMLInputElement; if (!i.files?.length) return; await ext.uploadPdfs(Array.from(i.files), uploadingPdf) }
</script>

<style scoped>
.extraction-view { max-width: 1100px; margin: 0 auto; }
.header-bar { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; gap: 1rem; flex-wrap: wrap; }
.header-meta { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
.session-badge { display: inline-flex; align-items: center; gap: 0.3rem; background: #e0f2fe; color: #0369a1; border-radius: 0.375rem; padding: 0.2rem 0.5rem; font-size: 0.78rem; font-family: monospace; }
.step-badge { display: inline-flex; align-items: center; background: #f3f4f6; color: #374151; border-radius: 0.375rem; padding: 0.2rem 0.5rem; font-size: 0.78rem; font-weight: 600; }
.fade-in { animation: fadeIn 0.2s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.badge-sheet { display: inline-block; background: #e0f2fe; color: #0369a1; border-radius: 0.375rem; padding: 0.125rem 0.5rem; font-size: 0.8rem; margin-right: 0.4rem; margin-top: 0.25rem; }
.pdf-list { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 0.75rem 1rem; }
.pdf-item { padding: 0.25rem 0; font-size: 0.875rem; display: flex; align-items: center; }
.pdf-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-icon-danger { background: none; border: none; color: #9ca3af; cursor: pointer; padding: 0.25rem 0.4rem; border-radius: 0.25rem; font-size: 0.8rem; transition: color 0.15s, background 0.15s; flex-shrink: 0; margin-left: auto; }
.btn-icon-danger:hover { color: #dc2626; background: #fef2f2; }
.empty-state { display: flex; flex-direction: column; align-items: center; text-align: center; color: #9ca3af; padding: 2rem 1rem; font-size: 0.875rem; gap: 0.5rem; }
.empty-state i { font-size: 2rem; color: #d1d5db; }
.empty-state p { margin: 0; }
.btn-danger { background: #dc2626; color: white; border: none; padding: 0.45rem 1.25rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.875rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.btn-danger:hover { background: #b91c1c; }
.btn-warning { background: #f59e0b; color: white; border: none; padding: 0.45rem 1.25rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.875rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.btn-warning:hover { background: #d97706; }
.btn-success { background: #15803d; color: white; border: none; padding: 0.45rem 1.25rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.875rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.btn-success:hover { background: #166534; }
.step-content { padding: 0; }

/* -- secondary panels below results -- */
.review-secondary {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}
@media (max-width: 768px) { .review-secondary { grid-template-columns: 1fr; } }
.review-detail-card { min-height: 120px; }
.review-alerts-card { min-height: 120px; }

.evidence-box {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.82rem;
  color: #374151;
  margin-top: 0.25rem;
  line-height: 1.5;
  font-style: italic;
}

/* -- PDF drawer overlay -- */
.pdf-drawer-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}
.pdf-drawer {
  width: 480px;
  max-width: 90vw;
  background: white;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  animation: slideIn 0.2s ease-out;
}
@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
.pdf-drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}
.pdf-drawer-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-icon { background: none; border: none; cursor: pointer; color: #9ca3af; padding: 0.2rem 0.35rem; border-radius: 0.25rem; font-size: 0.8rem; line-height: 1; transition: color 0.15s, background 0.15s; flex-shrink: 0; }
.btn-icon:hover { color: #1d4ed8; background: #eff6ff; }
.selected-row td { background: #eff6ff !important; }
.no-alerts { font-size: 0.875rem; color: #6b7280; padding: 0.5rem 0; display: flex; align-items: center; gap: 0.4rem; }
.alert-item { padding: 0.5rem 0; border-bottom: 1px solid #e5e7eb; font-size: 0.875rem; display: flex; align-items: flex-start; gap: 0.4rem; }
.alert-item:last-child { border-bottom: none; }
.alert-severity { font-weight: 600; text-transform: uppercase; font-size: 0.7rem; padding: 0.125rem 0.375rem; border-radius: 0.25rem; white-space: nowrap; flex-shrink: 0; }
.alert-severity.warning { background: #fffbeb; color: #92400e; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem 1rem; font-size: 0.875rem; margin-bottom: 0.5rem; }
</style>
