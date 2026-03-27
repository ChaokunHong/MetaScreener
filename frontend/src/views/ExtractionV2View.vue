<!-- frontend/src/views/ExtractionV2View.vue -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiGet, apiPost, apiUpload } from '@/api'

/* ───── types ───── */
interface SchemaField {
  column: string
  name: string
  description: string
  field_type: string
  role: string
  required: boolean
  dropdown_options: string[] | null
}
interface SchemaSheet {
  sheet_name: string
  role: string
  cardinality: string
  fields: SchemaField[]
  extraction_order: number
}
interface TemplateResponse {
  session_id: string
  sheets_detected: number
  data_sheets: string[]
  mapping_sheets: string[]
  plugin_recommendation: string | null
}
interface PluginInfo {
  plugin_id: string
  name: string
  version: string
  description: string
  domain: string
}
interface CellData {
  value: unknown
  confidence: string
  model_a_value: unknown
  model_b_value: unknown
  evidence: string | null
  warnings: string[]
  edited_by_user: boolean
}
interface RowData {
  row_index: number
  fields: Record<string, CellData>
}
interface SheetResultData {
  sheet_name: string
  rows: RowData[]
}
interface PdfResultData {
  pdf_id: string
  pdf_filename: string
  sheets: Record<string, SheetResultData>
}
interface SessionStatus {
  session_id: string
  status: string
  pdf_count: number
  schema_confirmed: boolean
  plugin_id: string | null
  results_count: number
}

/* ───── state ───── */
const currentStep = ref(1)
const sessionId = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// Step 1: Template
const templateFile = ref<File | null>(null)
const templateResponse = ref<TemplateResponse | null>(null)

// Step 2: Schema
const schemaSheets = ref<SchemaSheet[]>([])
const pluginRecommendation = ref<string | null>(null)
const selectedPlugin = ref<string | null>(null)
const availablePlugins = ref<PluginInfo[]>([])

// Step 3: PDFs
const pdfFiles = ref<File[]>([])
const uploadedPdfCount = ref(0)

// Step 4: Progress
const extractionRunning = ref(false)
const progressMessages = ref<string[]>([])

// Step 5: Results
const results = ref<PdfResultData[]>([])
const selectedPdfIndex = ref(0)
const selectedSheet = ref<string>('')
const selectedCell = ref<{ row: number; field: string } | null>(null)

// Step 6: Export
const exportUrl = ref<string | null>(null)

/* ───── computed ───── */
const currentPdf = computed(() => results.value[selectedPdfIndex.value] || null)
const currentSheetData = computed<SheetResultData | null>(() => {
  if (!currentPdf.value || !selectedSheet.value) return null
  return currentPdf.value.sheets[selectedSheet.value] || null
})
const sheetNames = computed(() => {
  if (!currentPdf.value) return []
  return Object.keys(currentPdf.value.sheets)
})
const extractFields = computed<string[]>(() => {
  if (!currentSheetData.value || !currentSheetData.value.rows.length) return []
  return Object.keys(currentSheetData.value.rows[0]?.fields ?? {})
})

/* ───── step 1: upload template ───── */
function onTemplateDrop(e: DragEvent) {
  e.preventDefault()
  const file = e.dataTransfer?.files[0]
  if (file && file.name.endsWith('.xlsx')) templateFile.value = file
}
function onTemplateSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) templateFile.value = input.files[0] ?? null
}
async function uploadTemplate() {
  if (!templateFile.value) return
  loading.value = true
  error.value = null
  try {
    const { session_id } = await apiPost<{ session_id: string }>('/v2/extraction/sessions', {})
    sessionId.value = session_id

    const fd = new FormData()
    fd.append('file', templateFile.value)
    const resp = await apiUpload<TemplateResponse>(`/v2/extraction/sessions/${session_id}/template`, fd)
    templateResponse.value = resp
    pluginRecommendation.value = resp.plugin_recommendation
    selectedPlugin.value = resp.plugin_recommendation

    // Load plugins
    availablePlugins.value = await apiGet<PluginInfo[]>('/v2/extraction/plugins')

    // Load schema details
    // For now we use the template response info
    currentStep.value = 2
  } catch (e: unknown) {
    error.value = `Template upload failed: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

/* ───── step 2: confirm schema ───── */
async function confirmSchema() {
  if (!sessionId.value) return
  loading.value = true
  try {
    await apiPost(`/v2/extraction/sessions/${sessionId.value}/schema`, {
      plugin_id: selectedPlugin.value,
    })
    currentStep.value = 3
  } catch (e: unknown) {
    error.value = `Schema confirmation failed: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

/* ───── step 3: upload PDFs ───── */
function onPdfDrop(e: DragEvent) {
  e.preventDefault()
  const files = Array.from(e.dataTransfer?.files || []).filter(f => f.name.endsWith('.pdf'))
  pdfFiles.value.push(...files)
}
function onPdfSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) pdfFiles.value.push(...Array.from(input.files))
}
function removePdf(index: number) {
  pdfFiles.value.splice(index, 1)
}
async function uploadPdfs() {
  if (!sessionId.value || !pdfFiles.value.length) return
  loading.value = true
  try {
    const fd = new FormData()
    for (const f of pdfFiles.value) fd.append('files', f)
    const resp = await apiUpload<{ pdf_count: number }>(`/v2/extraction/sessions/${sessionId.value}/pdfs`, fd)
    uploadedPdfCount.value = resp.pdf_count
    currentStep.value = 4
  } catch (e: unknown) {
    error.value = `PDF upload failed: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

/* ───── step 4: run extraction ───── */
async function runExtraction() {
  if (!sessionId.value) return
  extractionRunning.value = true
  progressMessages.value = ['Starting extraction...']
  try {
    await apiPost(`/v2/extraction/sessions/${sessionId.value}/run`, {})
    progressMessages.value.push('Extraction completed!')
    // Load results
    const resp = await apiGet<{ results: Record<string, PdfResultData> }>(
      `/v2/extraction/sessions/${sessionId.value}/results`
    )
    results.value = Object.values(resp.results)
    if (results.value.length > 0) {
      const firstPdf = results.value[0]
      if (firstPdf) {
        const sheets = Object.keys(firstPdf.sheets)
        if (sheets.length > 0) selectedSheet.value = sheets[0] ?? ''
      }
    }
    currentStep.value = 5
  } catch (e: unknown) {
    error.value = `Extraction failed: ${(e as Error).message}`
  } finally {
    extractionRunning.value = false
  }
}

/* ───── step 5: cell editing ───── */
function selectCell(rowIndex: number, fieldName: string) {
  selectedCell.value = { row: rowIndex, field: fieldName }
}
function confidenceClass(confidence: string): string {
  switch (confidence) {
    case 'HIGH': return 'conf-high'
    case 'MEDIUM': return 'conf-medium'
    case 'LOW': return 'conf-low'
    case 'SINGLE': return 'conf-single'
    default: return ''
  }
}
function confidenceIcon(confidence: string): string {
  switch (confidence) {
    case 'HIGH': return 'fas fa-check-circle'
    case 'MEDIUM': return 'fas fa-exclamation-triangle'
    case 'LOW': return 'fas fa-times-circle'
    case 'SINGLE': return 'fas fa-minus-circle'
    default: return ''
  }
}

/* ───── step 6: export ───── */
async function exportExcel() {
  if (!sessionId.value) return
  loading.value = true
  try {
    const resp = await apiPost<{ download_url: string }>(
      `/v2/extraction/sessions/${sessionId.value}/export`, {}
    )
    exportUrl.value = resp.download_url
  } catch (e: unknown) {
    error.value = `Export failed: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}

// Suppress unused variable warning for schemaSheets and sessionStatus-related
void schemaSheets
</script>

<template>
  <div class="extraction-v2">
    <!-- Step indicator -->
    <div class="step-indicator">
      <div v-for="s in 6" :key="s"
           class="step-dot"
           :class="{ active: currentStep === s, done: currentStep > s }">
        <span v-if="currentStep > s"><i class="fas fa-check"></i></span>
        <span v-else>{{ s }}</span>
      </div>
      <div class="step-labels">
        <span :class="{ active: currentStep === 1 }">Upload Template</span>
        <span :class="{ active: currentStep === 2 }">Confirm Schema</span>
        <span :class="{ active: currentStep === 3 }">Upload PDFs</span>
        <span :class="{ active: currentStep === 4 }">Extract</span>
        <span :class="{ active: currentStep === 5 }">Review</span>
        <span :class="{ active: currentStep === 6 }">Export</span>
      </div>
    </div>

    <!-- Error alert -->
    <div v-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i> {{ error }}
      <button class="btn-close" @click="error = null">&times;</button>
    </div>

    <!-- Step 1: Upload Template -->
    <div v-if="currentStep === 1" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-excel"></i> Upload Excel Template</h2>
      <p class="text-muted">Upload your data extraction template (.xlsx). The system will analyze its structure automatically.</p>

      <div class="upload-zone"
           @dragover.prevent
           @drop="onTemplateDrop"
           :class="{ 'has-file': templateFile }">
        <div v-if="!templateFile">
          <i class="fas fa-cloud-upload-alt upload-icon"></i>
          <p>Drag & drop your Excel template here</p>
          <label class="btn btn-outline">
            Or browse files
            <input type="file" accept=".xlsx" hidden @change="onTemplateSelect" />
          </label>
        </div>
        <div v-else class="file-info">
          <i class="fas fa-file-excel file-icon"></i>
          <span>{{ templateFile.name }}</span>
          <button class="btn btn-sm" @click="templateFile = null">&times;</button>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="!templateFile || loading" @click="uploadTemplate">
        <i class="fas fa-upload"></i>
        {{ loading ? 'Analyzing...' : 'Upload & Analyze' }}
      </button>
    </div>

    <!-- Step 2: Confirm Schema -->
    <div v-if="currentStep === 2" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-project-diagram"></i> Template Analysis</h2>

      <div v-if="templateResponse" class="schema-summary">
        <div class="stat-row">
          <div class="stat">
            <span class="stat-value">{{ templateResponse.sheets_detected }}</span>
            <span class="stat-label">Sheets Detected</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ templateResponse.data_sheets.length }}</span>
            <span class="stat-label">Data Sheets</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ templateResponse.mapping_sheets.length }}</span>
            <span class="stat-label">Mapping Tables</span>
          </div>
        </div>

        <div class="sheet-list">
          <h3>Data Sheets (extraction order)</h3>
          <div v-for="name in templateResponse.data_sheets" :key="name" class="sheet-tag data">
            <i class="fas fa-table"></i> {{ name }}
          </div>
          <h3 v-if="templateResponse.mapping_sheets.length">Mapping Tables</h3>
          <div v-for="name in templateResponse.mapping_sheets" :key="name" class="sheet-tag mapping">
            <i class="fas fa-exchange-alt"></i> {{ name }}
          </div>
        </div>

        <div v-if="pluginRecommendation" class="plugin-rec">
          <i class="fas fa-plug"></i>
          <span>Recommended plugin: <strong>{{ pluginRecommendation }}</strong></span>
          <select v-model="selectedPlugin" class="form-control form-control-sm">
            <option :value="null">No plugin</option>
            <option v-for="p in availablePlugins" :key="p.plugin_id" :value="p.plugin_id">
              {{ p.name }} ({{ p.version }})
            </option>
          </select>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="loading" @click="confirmSchema">
        <i class="fas fa-check"></i>
        {{ loading ? 'Confirming...' : 'Confirm Schema' }}
      </button>
    </div>

    <!-- Step 3: Upload PDFs -->
    <div v-if="currentStep === 3" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-pdf"></i> Upload PDF Literature</h2>
      <p class="text-muted">Upload the PDF files you want to extract data from.</p>

      <div class="upload-zone"
           @dragover.prevent
           @drop="onPdfDrop">
        <i class="fas fa-cloud-upload-alt upload-icon"></i>
        <p>Drag & drop PDF files here</p>
        <label class="btn btn-outline">
          Browse files
          <input type="file" accept=".pdf" multiple hidden @change="onPdfSelect" />
        </label>
      </div>

      <div v-if="pdfFiles.length" class="pdf-list">
        <div v-for="(f, i) in pdfFiles" :key="i" class="pdf-item">
          <i class="fas fa-file-pdf"></i>
          <span>{{ f.name }}</span>
          <span class="text-muted">{{ (f.size / 1024).toFixed(0) }} KB</span>
          <button class="btn btn-sm btn-danger" @click="removePdf(i)">&times;</button>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="!pdfFiles.length || loading" @click="uploadPdfs">
        <i class="fas fa-upload"></i>
        {{ loading ? 'Uploading...' : `Upload ${pdfFiles.length} PDF(s)` }}
      </button>
    </div>

    <!-- Step 4: Extraction Progress -->
    <div v-if="currentStep === 4" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-cogs"></i> Data Extraction</h2>
      <p class="text-muted">{{ uploadedPdfCount }} PDF(s) ready. Dual-model extraction with HCN 4-layer quality control.</p>

      <div v-if="!extractionRunning && !results.length">
        <button class="btn btn-primary btn-lg" @click="runExtraction">
          <i class="fas fa-play"></i> Start Extraction
        </button>
      </div>

      <div v-if="extractionRunning" class="progress-area">
        <div class="spinner"></div>
        <div v-for="(msg, i) in progressMessages" :key="i" class="progress-msg">
          {{ msg }}
        </div>
      </div>
    </div>

    <!-- Step 5: Review & Edit -->
    <div v-if="currentStep === 5" class="glass-card step-card wide">
      <h2 class="section-title"><i class="fas fa-edit"></i> Review Extraction Results</h2>

      <!-- PDF selector -->
      <div v-if="results.length > 1" class="pdf-selector">
        <label>PDF:</label>
        <select v-model="selectedPdfIndex" class="form-control">
          <option v-for="(r, i) in results" :key="i" :value="i">
            {{ r.pdf_filename }} ({{ i + 1 }}/{{ results.length }})
          </option>
        </select>
      </div>

      <!-- Sheet tabs -->
      <div class="sheet-tabs">
        <button v-for="name in sheetNames" :key="name"
                class="tab-btn"
                :class="{ active: selectedSheet === name }"
                @click="selectedSheet = name; selectedCell = null">
          {{ name }}
        </button>
      </div>

      <!-- Results table -->
      <div v-if="currentSheetData" class="table-container">
        <table class="result-table">
          <thead>
            <tr>
              <th v-for="field in extractFields" :key="field">{{ field }}</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in currentSheetData.rows" :key="row.row_index">
              <td v-for="field in extractFields" :key="field"
                  :class="confidenceClass(row.fields[field]?.confidence || '')"
                  @click="selectCell(row.row_index, field)"
                  class="clickable-cell">
                {{ row.fields[field]?.value ?? '—' }}
              </td>
              <td>
                <span v-for="field in extractFields" :key="field"
                      :title="field + ': ' + (row.fields[field]?.confidence || 'N/A')">
                  <i :class="confidenceIcon(row.fields[field]?.confidence || '')"></i>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Cell detail panel -->
      <div v-if="selectedCell && currentSheetData" class="cell-detail glass-card">
        <h3>Cell Detail</h3>
        <template v-if="currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]">
          <div class="detail-row">
            <span class="detail-label">Field:</span>
            <span>{{ selectedCell.field }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Confidence:</span>
            <span :class="confidenceClass(currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.confidence ?? '')">
              {{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.confidence }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Model A:</span>
            <span>{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.model_a_value ?? '—' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Model B:</span>
            <span>{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.model_b_value ?? '—' }}</span>
          </div>
          <div v-if="currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.evidence" class="detail-row">
            <span class="detail-label">Evidence:</span>
            <span class="evidence-text">{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.evidence }}</span>
          </div>
          <div v-if="currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.warnings?.length" class="detail-row">
            <span class="detail-label">Warnings:</span>
            <ul>
              <li v-for="(w, i) in currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.warnings" :key="i">{{ w }}</li>
            </ul>
          </div>
        </template>
        <button class="btn btn-sm" @click="selectedCell = null">Close</button>
      </div>

      <div class="step-actions">
        <button class="btn btn-primary" @click="currentStep = 6">
          <i class="fas fa-download"></i> Proceed to Export
        </button>
      </div>
    </div>

    <!-- Step 6: Export -->
    <div v-if="currentStep === 6" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-export"></i> Export Results</h2>
      <p class="text-muted">Download your extraction results as an Excel file with audit log.</p>

      <button class="btn btn-primary btn-lg" :disabled="loading" @click="exportExcel">
        <i class="fas fa-download"></i>
        {{ loading ? 'Generating...' : 'Download Excel' }}
      </button>

      <div v-if="exportUrl" class="export-success">
        <i class="fas fa-check-circle"></i>
        <a :href="exportUrl" download>Download Excel File</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.extraction-v2 {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

/* Step indicator */
.step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 2rem;
}
.step-indicator .step-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid #ccc;
  margin: 0 0.5rem;
  font-size: 0.85rem;
  color: #999;
  transition: all 0.3s;
}
.step-dot.active {
  border-color: #4a90d9;
  color: #4a90d9;
  font-weight: bold;
}
.step-dot.done {
  border-color: #27ae60;
  background: #27ae60;
  color: #fff;
}
.step-labels {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #999;
}
.step-labels span.active {
  color: #4a90d9;
  font-weight: 600;
}

/* Cards */
.step-card {
  padding: 2rem;
  margin-bottom: 1.5rem;
}
.step-card.wide {
  max-width: 100%;
}

/* Upload zone */
.upload-zone {
  border: 2px dashed #ccc;
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  margin: 1rem 0;
  transition: border-color 0.3s;
  cursor: pointer;
}
.upload-zone:hover, .upload-zone.has-file {
  border-color: #4a90d9;
}
.upload-icon {
  font-size: 2.5rem;
  color: #999;
  margin-bottom: 0.5rem;
}
.file-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: center;
}
.file-icon {
  font-size: 1.5rem;
  color: #27ae60;
}

/* Schema summary */
.stat-row {
  display: flex;
  gap: 1.5rem;
  margin: 1rem 0;
}
.stat {
  text-align: center;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 8px;
  flex: 1;
}
.stat-value {
  display: block;
  font-size: 2rem;
  font-weight: bold;
  color: #4a90d9;
}
.stat-label {
  font-size: 0.85rem;
  color: #666;
}
.sheet-list h3 {
  margin: 1rem 0 0.5rem;
  font-size: 0.95rem;
}
.sheet-tag {
  display: inline-block;
  padding: 0.3rem 0.8rem;
  border-radius: 6px;
  margin: 0.2rem;
  font-size: 0.85rem;
}
.sheet-tag.data {
  background: #e3f2fd;
  color: #1565c0;
}
.sheet-tag.mapping {
  background: #fff3e0;
  color: #e65100;
}
.plugin-rec {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 1rem 0;
  padding: 0.8rem;
  background: #f0f7ff;
  border-radius: 8px;
}
.plugin-rec select {
  max-width: 250px;
}

/* PDF list */
.pdf-list {
  margin: 1rem 0;
}
.pdf-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-bottom: 1px solid #eee;
}

/* Progress */
.progress-area {
  text-align: center;
  padding: 2rem;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #4a90d9;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.progress-msg {
  color: #666;
  margin: 0.3rem 0;
}

/* Sheet tabs */
.sheet-tabs {
  display: flex;
  gap: 0.5rem;
  margin: 1rem 0;
}
.tab-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #ddd;
  border-radius: 6px 6px 0 0;
  background: #f8f9fa;
  cursor: pointer;
  font-size: 0.9rem;
}
.tab-btn.active {
  background: #fff;
  border-bottom-color: #fff;
  font-weight: 600;
  color: #4a90d9;
}

/* Result table */
.table-container {
  overflow-x: auto;
  margin: 1rem 0;
}
.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.result-table th {
  background: #f8f9fa;
  padding: 0.6rem;
  text-align: left;
  border-bottom: 2px solid #ddd;
  font-size: 0.85rem;
  white-space: nowrap;
}
.result-table td {
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid #eee;
}
.clickable-cell {
  cursor: pointer;
  transition: background 0.2s;
}
.clickable-cell:hover {
  background: #f0f7ff;
}

/* Confidence colors */
.conf-high { }
.conf-medium { background: #fff8e1; }
.conf-low { background: #fce4ec; }
.conf-single { background: #f5f5f5; color: #999; }

/* Cell detail */
.cell-detail {
  position: sticky;
  bottom: 1rem;
  padding: 1.5rem;
  margin-top: 1rem;
  border: 1px solid #4a90d9;
}
.detail-row {
  display: flex;
  gap: 0.5rem;
  margin: 0.4rem 0;
}
.detail-label {
  font-weight: 600;
  min-width: 100px;
  color: #666;
}
.evidence-text {
  font-style: italic;
  color: #555;
  background: #f8f9fa;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
}

/* Actions */
.step-actions {
  margin-top: 1.5rem;
  display: flex;
  gap: 1rem;
}

/* Export */
.export-success {
  margin-top: 1rem;
  padding: 1rem;
  background: #e8f5e9;
  border-radius: 8px;
  color: #2e7d32;
}

/* Buttons */
.btn-lg {
  padding: 0.8rem 2rem;
  font-size: 1.1rem;
}
.btn-sm {
  padding: 0.2rem 0.5rem;
  font-size: 0.85rem;
}
.btn-danger {
  color: #e74c3c;
  border-color: #e74c3c;
}

/* Alert */
.alert-error {
  background: #fce4ec;
  color: #c62828;
  padding: 0.8rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.btn-close {
  margin-left: auto;
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
}

/* PDF selector */
.pdf-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.pdf-selector select {
  max-width: 400px;
}
</style>
