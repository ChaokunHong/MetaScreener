<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiGet, apiPost, apiPut, apiUpload } from '@/api'

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

/* ───── refs ───── */
const templateInput = ref<HTMLInputElement | null>(null)
const pdfInput = ref<HTMLInputElement | null>(null)

/* ───── state ───── */
const currentStep = ref(1)
const sessionId = ref<string | null>(null)
const loading = ref(false)
const activeModal = ref<string | null>(null)
const error = ref<string | null>(null)

const templateFile = ref<File | null>(null)
const templateResponse = ref<TemplateResponse | null>(null)

const schemaSheets = ref<SchemaSheet[]>([])
const pluginRecommendation = ref<string | null>(null)
const selectedPlugin = ref<string | null>(null)
const availablePlugins = ref<PluginInfo[]>([])

const pdfFiles = ref<File[]>([])
const uploadedPdfCount = ref(0)

const extractionRunning = ref(false)
const progressMessages = ref<string[]>([])

const results = ref<PdfResultData[]>([])
const selectedPdfIndex = ref(0)
const selectedSheet = ref<string>('')
const selectedCell = ref<{ row: number; field: string } | null>(null)

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

    availablePlugins.value = await apiGet<PluginInfo[]>('/v2/extraction/plugins')

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
    await apiPut(`/v2/extraction/sessions/${sessionId.value}/schema`, {
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
  error.value = null
  progressMessages.value = ['Starting dual-model extraction...', 'This may take several minutes for multiple PDFs.']
  try {
    const runResp = await apiPost<{
      status: string; completed: number; failed: number; errors?: string[]
    }>(`/v2/extraction/sessions/${sessionId.value}/run`, {})

    if (runResp.errors?.length) {
      progressMessages.value.push(`Warnings: ${runResp.errors.join('; ')}`)
    }
    if (runResp.completed === 0) {
      error.value = `Extraction failed for all PDFs. ${runResp.errors?.join('; ') ?? 'Check server logs for details.'}`
      return
    }

    progressMessages.value.push(`Completed: ${runResp.completed}/${runResp.completed + runResp.failed} PDFs`)

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
    <div class="stepper">
      <div v-for="(label, i) in ['Template', 'Schema', 'PDFs', 'Extract', 'Review', 'Export']"
           :key="i" class="stepper-item" :class="{ active: currentStep === i + 1, done: currentStep > i + 1 }">
        <div class="stepper-dot">
          <i v-if="currentStep > i + 1" class="fas fa-check"></i>
          <span v-else>{{ i + 1 }}</span>
        </div>
        <span class="stepper-label">{{ label }}</span>
        <div v-if="i < 5" class="stepper-line" :class="{ filled: currentStep > i + 1 }"></div>
      </div>
    </div>

    <div v-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i> {{ error }}
      <button class="btn-close" @click="error = null">&times;</button>
    </div>

    <div v-if="currentStep === 1" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-excel"></i> Upload Excel Template</h2>
      <p class="text-muted">Upload your data extraction template (.xlsx). The system will analyze its structure automatically.</p>

      <div class="upload-zone"
           :class="{ 'has-file': templateFile }"
           @click="templateInput?.click()"
           @dragover.prevent
           @drop="onTemplateDrop">
        <input ref="templateInput" type="file" accept=".xlsx" hidden @change="onTemplateSelect" />
        <div v-if="!templateFile">
          <i class="fas fa-cloud-upload-alt upload-icon"></i>
          <p>Drag & drop or click to select your Excel template</p>
        </div>
        <div v-else class="file-info" @click.stop>
          <i class="fas fa-file-excel file-icon"></i>
          <span>{{ templateFile.name }}</span>
          <button class="btn btn-sm" @click="templateFile = null">&times;</button>
        </div>
      </div>

      <div v-if="loading" class="glass-progress">
        <div class="glass-progress-track">
          <div class="glass-progress-fill"></div>
        </div>
        <span class="glass-progress-label">Analyzing template structure...</span>
      </div>

      <button class="btn btn-primary" :disabled="!templateFile || loading" @click="uploadTemplate">
        <i v-if="!loading" class="fas fa-upload"></i>
        <i v-else class="fas fa-spinner fa-spin"></i>
        {{ loading ? 'Analyzing...' : 'Upload & Analyze' }}
      </button>
    </div>

    <div v-if="currentStep === 2" class="glass-card step-card">
      <h2 class="section-title">
        <i class="fas fa-project-diagram"></i> Template Analysis
        <button class="info-btn" style="margin-left: 6px;" @click="activeModal = 'schema'" title="About Schema Analysis">
          <i class="fas fa-circle-info"></i>
        </button>
      </h2>

      <div v-if="templateResponse" class="schema-summary">
        <div class="stat-row">
          <div class="stat">
            <span class="stat-value">{{ templateResponse.sheets_detected }}</span>
            <span class="stat-label">Sheets Detected
              <button class="info-btn info-btn-inline" @click="activeModal = 'sheets'" title="About Sheet Detection">
                <i class="fas fa-circle-info"></i>
              </button>
            </span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ templateResponse.data_sheets.length }}</span>
            <span class="stat-label">Data Sheets</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ templateResponse.mapping_sheets.length }}</span>
            <span class="stat-label">Mapping Tables
              <button class="info-btn info-btn-inline" @click="activeModal = 'mappings'" title="About Mapping Tables">
                <i class="fas fa-circle-info"></i>
              </button>
            </span>
          </div>
        </div>

        <div class="sheet-list">
          <h3>Data Sheets (extraction order)</h3>
          <div v-for="name in templateResponse.data_sheets" :key="name" class="sheet-tag data">
            <i class="fas fa-table"></i> {{ name }}
          </div>
          <h3 v-if="templateResponse.mapping_sheets.length" style="margin-top: 1.2rem;">Mapping Tables</h3>
          <div v-for="name in templateResponse.mapping_sheets" :key="name" class="sheet-tag mapping">
            <i class="fas fa-exchange-alt"></i> {{ name }}
          </div>
        </div>

        <div class="plugin-rec">
          <i class="fas fa-plug"></i>
          <span>Domain Plugin
            <button class="info-btn info-btn-inline" @click="activeModal = 'plugin'" title="About Plugins">
              <i class="fas fa-circle-info"></i>
            </button>
          </span>
          <div class="plugin-select-wrap">
            <select v-model="selectedPlugin" class="form-control">
              <option :value="null">No plugin</option>
              <option v-for="p in availablePlugins" :key="p.plugin_id" :value="p.plugin_id">
                {{ p.name }}
              </option>
            </select>
          </div>
          <span v-if="pluginRecommendation && selectedPlugin === pluginRecommendation" class="plugin-badge">
            <i class="fas fa-star"></i> Recommended
          </span>
        </div>
      </div>

      <button class="btn btn-primary" style="margin-top: 1.5rem;" :disabled="loading" @click="confirmSchema">
        <i class="fas fa-check"></i>
        {{ loading ? 'Confirming...' : 'Confirm Schema' }}
      </button>
    </div>

    <div v-if="currentStep === 3" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-pdf"></i> Upload PDF Literature</h2>
      <p class="text-muted">Upload the PDF files you want to extract data from.</p>

      <div class="upload-zone"
           @click="pdfInput?.click()"
           @dragover.prevent
           @drop="onPdfDrop">
        <input ref="pdfInput" type="file" accept=".pdf" multiple hidden @change="onPdfSelect" />
        <i class="fas fa-cloud-upload-alt upload-icon"></i>
        <p>Drag & drop or click to select PDF files</p>
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

    <div v-if="currentStep === 4" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-cogs"></i> Data Extraction</h2>
      <p class="text-muted">{{ uploadedPdfCount }} PDF(s) ready. Dual-model extraction with HCN 4-layer quality control.</p>

      <div v-if="!extractionRunning && !results.length">
        <div class="extraction-info">
          <div class="extraction-info-item">
            <i class="fas fa-file-pdf"></i>
            <span>{{ uploadedPdfCount }} PDFs</span>
          </div>
          <div class="extraction-info-item">
            <i class="fas fa-table"></i>
            <span>{{ templateResponse?.data_sheets.length ?? 0 }} sheets per PDF</span>
          </div>
          <div class="extraction-info-item">
            <i class="fas fa-robot"></i>
            <span>2 models (dual extraction)</span>
          </div>
        </div>
        <button class="btn btn-primary" @click="runExtraction">
          <i class="fas fa-play"></i> Start Extraction
        </button>
      </div>

      <div v-if="extractionRunning" class="progress-area">
        <div class="glass-progress" style="margin-bottom: 1.5rem;">
          <div class="glass-progress-track">
            <div class="glass-progress-fill"></div>
          </div>
        </div>

        <div class="log-window" ref="logWindow">
          <div v-for="(msg, i) in progressMessages" :key="i" class="log-line">
            <span class="log-time">{{ new Date().toLocaleTimeString() }}</span>
            <span class="log-text">{{ msg }}</span>
          </div>
          <div class="log-line log-active">
            <span class="log-cursor"></span>
            <span class="log-text">Processing...</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="currentStep === 5" class="review-step">
      <div class="review-toolbar glass-card">
        <div class="review-toolbar-left">
          <select v-if="results.length > 1" v-model="selectedPdfIndex" class="form-control pdf-select">
            <option v-for="(r, i) in results" :key="i" :value="i">
              {{ r.pdf_filename }} ({{ i + 1 }}/{{ results.length }})
            </option>
          </select>
          <span v-else-if="currentPdf" class="pdf-name">
            <i class="fas fa-file-pdf"></i> {{ currentPdf.pdf_filename }}
          </span>
        </div>
        <div class="review-toolbar-tabs">
          <button v-for="name in sheetNames" :key="name"
                  class="tab-btn" :class="{ active: selectedSheet === name }"
                  @click="selectedSheet = name; selectedCell = null">
            {{ name }}
          </button>
        </div>
      </div>

      <div class="review-body">
        <div class="review-table-area" :class="{ 'has-detail': selectedCell }">
          <div v-if="currentSheetData" class="table-scroll">
            <table class="review-table">
              <thead>
                <tr>
                  <th class="row-num-th">#</th>
                  <th v-for="field in extractFields" :key="field">
                    <span class="th-text">{{ field.replace(/_/g, ' ') }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in currentSheetData.rows" :key="row.row_index"
                    :class="{ 'row-selected': selectedCell?.row === row.row_index }">
                  <td class="row-num">{{ row.row_index + 1 }}</td>
                  <td v-for="field in extractFields" :key="field"
                      class="data-cell"
                      :class="[
                        confidenceClass(row.fields[field]?.confidence || ''),
                        { 'cell-selected': selectedCell?.row === row.row_index && selectedCell?.field === field }
                      ]"
                      @click="selectCell(row.row_index, field)">
                    <span class="cell-value">{{ row.fields[field]?.value ?? '—' }}</span>
                    <span class="cell-dot" :class="'dot-' + (row.fields[field]?.confidence || '').toLowerCase()"></span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-sheet">
            <i class="fas fa-inbox"></i>
            <p>No data extracted for this sheet</p>
          </div>
        </div>

        <Transition name="slide">
          <div v-if="selectedCell && currentSheetData && currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]"
               class="detail-panel glass-card">
            <div class="detail-header">
              <h3>{{ selectedCell.field.replace(/_/g, ' ') }}</h3>
              <button class="detail-close" @click="selectedCell = null"><i class="fas fa-times"></i></button>
            </div>

            <div class="detail-conf" :class="confidenceClass(currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.confidence ?? '')">
              <i :class="confidenceIcon(currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.confidence ?? '')"></i>
              {{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.confidence }}
            </div>

            <div class="detail-section">
              <div class="detail-label">Final Value</div>
              <div class="detail-value">{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.value ?? '—' }}</div>
            </div>

            <div class="detail-compare">
              <div class="detail-model">
                <div class="detail-label">Model A</div>
                <div class="detail-value">{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.model_a_value ?? '—' }}</div>
              </div>
              <div class="detail-model">
                <div class="detail-label">Model B</div>
                <div class="detail-value">{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.model_b_value ?? '—' }}</div>
              </div>
            </div>

            <div v-if="currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.evidence" class="detail-section">
              <div class="detail-label">Evidence</div>
              <div class="detail-evidence">{{ currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.evidence }}</div>
            </div>

            <div v-if="currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.warnings?.length" class="detail-section">
              <div class="detail-label">Warnings</div>
              <div v-for="(w, i) in currentSheetData.rows[selectedCell.row]?.fields[selectedCell.field]?.warnings" :key="i" class="detail-warning">
                <i class="fas fa-exclamation-triangle"></i> {{ w }}
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <div class="review-footer glass-card">
        <div class="review-stats">
          <span v-if="currentSheetData">{{ currentSheetData.rows.length }} rows</span>
          <span>{{ extractFields.length }} fields</span>
        </div>
        <button class="btn btn-primary" @click="currentStep = 6">
          <i class="fas fa-download"></i> Proceed to Export
        </button>
      </div>
    </div>

    <div v-if="currentStep === 6" class="glass-card step-card">
      <h2 class="section-title"><i class="fas fa-file-export"></i> Export Results</h2>
      <p class="text-muted">Download your extraction results as an Excel file with audit log.</p>

      <button class="btn btn-primary" :disabled="loading" @click="exportExcel">
        <i class="fas fa-download"></i>
        {{ loading ? 'Generating...' : 'Download Excel' }}
      </button>

      <div v-if="exportUrl" class="export-success">
        <i class="fas fa-check-circle"></i>
        <a :href="exportUrl" download>Download Excel File</a>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="activeModal" class="modal-overlay" @click.self="activeModal = null">
          <div class="modal-glass-panel">
            <div class="modal-refraction"></div>
            <button class="modal-close" @click="activeModal = null">
              <i class="fas fa-times"></i>
            </button>

            <template v-if="activeModal === 'schema'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-cyan"><i class="fas fa-project-diagram"></i></div>
                <h2 class="modal-title">Template Analysis</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-question-circle"></i> What is this?</h3>
                  <p>The system automatically analyzes your Excel template's structure — detecting which sheets contain data to extract, which are lookup/mapping tables, and how they relate to each other.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-check-double"></i> What to check</h3>
                  <p>Verify that the detected <strong>Data Sheets</strong> and <strong>Mapping Tables</strong> are correct. Data sheets are where the AI will fill in extracted values. Mapping tables provide standardized terminology (e.g., antibiotic classifications).</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-arrows-alt-h"></i> Extraction order</h3>
                  <p>Data sheets are processed in order — earlier sheets' results are passed as context to later sheets. For example, study-level info extracted first helps the AI correctly extract pathogen-level data.</p>
                </div>
              </div>
            </template>

            <template v-if="activeModal === 'sheets'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-purple"><i class="fas fa-layer-group"></i></div>
                <h2 class="modal-title">Sheet Detection</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-table"></i> Data Sheets</h3>
                  <p>Sheets where the AI will extract and fill data from your PDF literature. Detected by the presence of column headers, formulas, dropdown validations, and data rows.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-exchange-alt"></i> Mapping Tables</h3>
                  <p>Lookup tables used for terminology standardization (e.g., antibiotic name → drug class). These are not filled by the AI — they serve as reference data.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-book"></i> Documentation Sheets</h3>
                  <p>Sheets like "Data_Dictionary" or "Filling_Guide" are recognized as documentation and excluded from extraction.</p>
                </div>
              </div>
            </template>

            <template v-if="activeModal === 'mappings'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-purple"><i class="fas fa-exchange-alt"></i></div>
                <h2 class="modal-title">Mapping Tables</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-spell-check"></i> What they do</h3>
                  <p>Mapping tables standardize extracted terminology. When the AI extracts a value that matches a key in a mapping table, related columns (e.g., drug class, category) are auto-filled from the mapping.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-lightbulb"></i> Example</h3>
                  <p>If your template has an "Antibiotic_Mappings" table mapping "Ampicillin" → Drug_Class: "Penicillins", then when the AI extracts "Ampicillin", the drug class column is filled automatically.</p>
                </div>
              </div>
            </template>

            <template v-if="activeModal === 'plugin'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-cyan"><i class="fas fa-plug"></i></div>
                <h2 class="modal-title">Domain Plugins</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-question-circle"></i> What is a plugin?</h3>
                  <p>Plugins provide domain-specific knowledge to improve extraction accuracy: terminology standardization, validation rules, and specialized prompts tailored to your research field.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-star"></i> Auto-detection</h3>
                  <p>The system analyzes your template's column names and keywords to recommend the best-matching plugin. You can accept the recommendation, choose a different plugin, or proceed without one.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-cogs"></i> What plugins provide</h3>
                  <ul style="margin: 0.5rem 0 0 1rem; line-height: 1.8;">
                    <li><strong>Terminology</strong> — standardizes variant names to canonical forms</li>
                    <li><strong>Validation rules</strong> — domain-specific data quality checks</li>
                    <li><strong>Extraction guidance</strong> — specialized prompts for the AI models</li>
                  </ul>
                </div>
              </div>
            </template>

          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.extraction-v2 {
  max-width: 960px;
  margin: 0 auto;
  padding: 2.5rem 2rem 4rem;
}
/* Review step breaks out of max-width for full-width table */
.extraction-v2:has(.review-step) {
  max-width: 100%;
  padding: 1rem 1.5rem;
}

/* Horizontal stepper */
.stepper {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  margin-bottom: 3rem;
  gap: 0;
}
.stepper-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
  max-width: 130px;
}
.stepper-dot {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid #ddd;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.82rem;
  color: #bbb;
  background: #fff;
  transition: all 0.3s;
  z-index: 1;
}
.stepper-item.active .stepper-dot {
  border-color: #4a90d9;
  color: #4a90d9;
  font-weight: 700;
  box-shadow: 0 0 0 4px rgba(74, 144, 217, 0.12);
}
.stepper-item.done .stepper-dot {
  border-color: #27ae60;
  background: #27ae60;
  color: #fff;
}
.stepper-label {
  margin-top: 8px;
  font-size: 0.72rem;
  color: #aaa;
  text-align: center;
  letter-spacing: 0.02em;
}
.stepper-item.active .stepper-label {
  color: #4a90d9;
  font-weight: 600;
}
.stepper-item.done .stepper-label {
  color: #27ae60;
}
.stepper-line {
  position: absolute;
  top: 18px;
  left: calc(50% + 22px);
  width: calc(100% - 12px);
  height: 2px;
  background: #e8e8e8;
}
.stepper-line.filled {
  background: #27ae60;
}

/* Cards */
.step-card {
  padding: 2.5rem 3rem;
  margin-bottom: 2rem;
}
.step-card.wide {
  max-width: 100%;
}
.step-card .section-title {
  margin-bottom: 1.2rem;
}
.step-card .text-muted {
  margin-bottom: 1.5rem;
  line-height: 1.6;
}

/* Upload zone — frosted glass */
.upload-zone {
  position: relative;
  border: 1.5px solid rgba(74, 144, 217, 0.25);
  border-radius: 18px;
  padding: 3rem 2rem;
  text-align: center;
  margin: 0.5rem 0 1.5rem;
  cursor: pointer;
  background: linear-gradient(135deg,
    rgba(255, 255, 255, 0.6) 0%,
    rgba(235, 245, 255, 0.4) 40%,
    rgba(220, 238, 255, 0.3) 100%);
  -webkit-backdrop-filter: blur(16px) saturate(1.4);
  backdrop-filter: blur(16px) saturate(1.4);
  box-shadow:
    0 4px 24px rgba(74, 144, 217, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    inset 0 -1px 0 rgba(255, 255, 255, 0.2);
  transition: all 0.35s ease;
  overflow: hidden;
}
.upload-zone::before {
  content: '';
  position: absolute;
  top: 0; left: 10%; right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent);
}
.upload-zone:hover {
  border-color: rgba(74, 144, 217, 0.5);
  background: linear-gradient(135deg,
    rgba(255, 255, 255, 0.55) 0%,
    rgba(230, 243, 255, 0.45) 50%,
    rgba(210, 233, 255, 0.35) 100%);
  box-shadow:
    0 8px 32px rgba(74, 144, 217, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
  transform: translateY(-1px);
}
.upload-zone.has-file {
  border-color: rgba(39, 174, 96, 0.4);
  background: linear-gradient(135deg,
    rgba(255, 255, 255, 0.5) 0%,
    rgba(232, 245, 233, 0.4) 100%);
}
.upload-zone p {
  color: #999;
  font-size: 0.88rem;
  margin-top: 0.4rem;
}
.upload-icon {
  font-size: 2.2rem;
  color: #a8c4dd;
  margin-bottom: 0.3rem;
  transition: color 0.3s;
}
.upload-zone:hover .upload-icon {
  color: #4a90d9;
}
.file-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  justify-content: center;
}
.file-icon {
  font-size: 1.5rem;
  color: #27ae60;
}

/* Schema summary */
.schema-summary {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}
.stat-row {
  display: flex;
  gap: 1.2rem;
}
.stat {
  text-align: center;
  padding: 1.5rem 1rem;
  background: rgba(248, 249, 250, 0.6);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 14px;
  flex: 1;
}
.stat-value {
  display: block;
  font-size: 1.6rem;
  font-weight: 700;
  color: #4a90d9;
  line-height: 1;
}
.stat-label {
  font-size: 0.78rem;
  color: #999;
  margin-top: 0.5rem;
  letter-spacing: 0.01em;
}
.sheet-list {
  padding: 0.2rem 0;
}
.sheet-list h3 {
  margin: 0 0 0.6rem;
  font-size: 0.85rem;
  color: #777;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.sheet-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 1rem;
  border-radius: 8px;
  margin: 0.25rem 0.3rem 0.25rem 0;
  font-size: 0.8rem;
  font-weight: 500;
}
.sheet-tag.data {
  background: rgba(227, 242, 253, 0.65);
  color: #1565c0;
}
.sheet-tag.mapping {
  background: rgba(255, 243, 224, 0.65);
  color: #e65100;
}
.plugin-rec {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.1rem 1.4rem;
  background: rgba(240, 247, 255, 0.5);
  border: 1px solid rgba(74, 144, 217, 0.1);
  border-radius: 14px;
}
.plugin-select-wrap {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}
.plugin-select-wrap select {
  width: 100%;
  min-width: 280px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.plugin-badge {
  font-size: 0.78rem;
  color: #e67e22;
  white-space: nowrap;
}
.info-btn-inline {
  font-size: 0.65rem;
  vertical-align: middle;
  margin-left: 2px;
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

/* Glass progress bar */
.glass-progress {
  margin: 1.2rem 0 1.5rem;
  text-align: center;
}
.glass-progress-track {
  position: relative;
  height: 6px;
  border-radius: 6px;
  background: linear-gradient(135deg,
    rgba(255, 255, 255, 0.5) 0%,
    rgba(235, 245, 255, 0.3) 100%);
  border: 1px solid rgba(74, 144, 217, 0.15);
  overflow: hidden;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.6),
    0 1px 4px rgba(74, 144, 217, 0.06);
}
.glass-progress-fill {
  position: absolute;
  top: 0; left: 0;
  height: 100%;
  width: 35%;
  border-radius: 6px;
  background: linear-gradient(90deg,
    rgba(74, 144, 217, 0.6),
    rgba(74, 144, 217, 0.35),
    rgba(74, 144, 217, 0.6));
  background-size: 200% 100%;
  animation: glass-shimmer 1.8s ease-in-out infinite;
  box-shadow: 0 0 12px rgba(74, 144, 217, 0.2);
}
@keyframes glass-shimmer {
  0% { left: -35%; background-position: 0% 50%; }
  100% { left: 100%; background-position: 200% 50%; }
}
.glass-progress-label {
  display: block;
  margin-top: 0.6rem;
  font-size: 0.78rem;
  color: #8aa8c4;
  letter-spacing: 0.02em;
}

/* Extraction info cards */
.extraction-info {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.extraction-info-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.7rem 1.2rem;
  background: rgba(248, 249, 250, 0.6);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  font-size: 0.85rem;
  color: #555;
}
.extraction-info-item i {
  color: #4a90d9;
}

/* Progress */
.progress-area {
  padding: 1rem 0;
}

/* Log window */
.log-window {
  background: #1a1d23;
  border-radius: 12px;
  padding: 1rem 1.2rem;
  max-height: 280px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 0.78rem;
  line-height: 1.7;
  margin-top: 0.5rem;
}
.log-line {
  display: flex;
  gap: 0.6rem;
  color: rgba(255, 255, 255, 0.7);
}
.log-time {
  color: rgba(255, 255, 255, 0.3);
  flex-shrink: 0;
}
.log-text {
  color: rgba(255, 255, 255, 0.75);
}
.log-active {
  color: #4a90d9;
}
.log-active .log-text {
  color: #6db3f2;
}
.log-cursor {
  display: inline-block;
  width: 7px;
  height: 14px;
  background: #4a90d9;
  animation: blink 1s step-end infinite;
  vertical-align: middle;
  margin-right: 0.3rem;
}
@keyframes blink {
  50% { opacity: 0; }
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

/* ── Review Step (full-width, not inside .extraction-v2 max-width) ── */
.review-step {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  gap: 0;
}

/* Toolbar */
.review-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  margin-bottom: 0.75rem;
  flex-shrink: 0;
}
.review-toolbar-left {
  flex-shrink: 0;
}
.pdf-select {
  max-width: 300px;
  font-size: 0.82rem;
}
.pdf-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: #555;
}
.review-toolbar-tabs {
  display: flex;
  gap: 0.35rem;
  overflow-x: auto;
  flex: 1;
}
.tab-btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  font-size: 0.78rem;
  white-space: nowrap;
  transition: all 0.2s;
  color: #777;
}
.tab-btn:hover { background: rgba(74, 144, 217, 0.08); color: #4a90d9; }
.tab-btn.active {
  background: rgba(74, 144, 217, 0.1);
  border-color: rgba(74, 144, 217, 0.25);
  color: #4a90d9;
  font-weight: 600;
}

/* Body: table + detail side by side */
.review-body {
  display: flex;
  gap: 0.75rem;
  flex: 1;
  min-height: 0;
}
.review-table-area {
  flex: 1;
  min-width: 0;
  transition: flex 0.3s;
}
.review-table-area.has-detail {
  flex: 3;
}

/* Scrollable table */
.table-scroll {
  height: 100%;
  overflow: auto;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #fff;
}
.review-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.78rem;
}
.review-table thead {
  position: sticky;
  top: 0;
  z-index: 2;
}
.review-table th {
  background: #f7f8fa;
  padding: 0.55rem 0.7rem;
  text-align: left;
  border-bottom: 2px solid #e8e8e8;
  font-size: 0.72rem;
  font-weight: 600;
  color: #888;
  text-transform: capitalize;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.row-num-th {
  width: 36px;
  text-align: center;
}
.review-table td {
  padding: 0.45rem 0.7rem;
  border-bottom: 1px solid #f2f2f2;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.review-table tbody tr:nth-child(even) {
  background: rgba(248, 249, 250, 0.5);
}
.review-table tbody tr:hover {
  background: rgba(74, 144, 217, 0.04);
}
.review-table tbody tr.row-selected {
  background: rgba(74, 144, 217, 0.08);
}
.row-num {
  text-align: center;
  color: #bbb;
  font-size: 0.72rem;
  font-weight: 500;
}

/* Data cells */
.data-cell {
  cursor: pointer;
  position: relative;
  transition: background 0.15s;
}
.data-cell:hover {
  background: rgba(74, 144, 217, 0.06) !important;
}
.data-cell.cell-selected {
  background: rgba(74, 144, 217, 0.12) !important;
  box-shadow: inset 0 0 0 1.5px rgba(74, 144, 217, 0.4);
}
.cell-value {
  display: inline;
}
.cell-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
}
.dot-high { background: #27ae60; }
.dot-medium { background: #f39c12; }
.dot-low { background: #e74c3c; }
.dot-single { background: #bbb; }

/* Confidence row tinting */
.conf-high { }
.conf-medium { background: rgba(255, 248, 225, 0.5); }
.conf-low { background: rgba(252, 228, 236, 0.4); }
.conf-single { color: #aaa; }

.empty-sheet {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #bbb;
  font-size: 0.9rem;
}
.empty-sheet i { font-size: 2rem; margin-bottom: 0.5rem; }

/* Detail panel (right side) */
.detail-panel {
  width: 320px;
  flex-shrink: 0;
  padding: 1.2rem 1.4rem;
  border-radius: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.detail-header h3 {
  font-size: 0.9rem;
  font-weight: 700;
  color: #333;
  text-transform: capitalize;
  margin: 0;
}
.detail-close {
  width: 24px; height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.04);
  color: #999;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.7rem;
  transition: all 0.2s;
}
.detail-close:hover { background: rgba(0,0,0,0.08); color: #555; }

.detail-conf {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.8rem;
  border-radius: 8px;
  font-size: 0.78rem;
  font-weight: 600;
  width: fit-content;
}
.detail-conf.conf-high { background: rgba(39, 174, 96, 0.1); color: #27ae60; }
.detail-conf.conf-medium { background: rgba(243, 156, 18, 0.1); color: #e67e22; }
.detail-conf.conf-low { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
.detail-conf.conf-single { background: rgba(0,0,0,0.05); color: #999; }

.detail-section { }
.detail-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.25rem;
}
.detail-value {
  font-size: 0.85rem;
  color: #333;
  word-break: break-word;
}
.detail-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.detail-model {
  padding: 0.6rem;
  background: rgba(248, 249, 250, 0.7);
  border-radius: 8px;
}
.detail-evidence {
  font-size: 0.8rem;
  color: #555;
  font-style: italic;
  background: rgba(248, 249, 250, 0.7);
  padding: 0.6rem 0.8rem;
  border-radius: 8px;
  border-left: 3px solid rgba(74, 144, 217, 0.3);
  line-height: 1.5;
}
.detail-warning {
  font-size: 0.78rem;
  color: #e67e22;
  display: flex;
  gap: 0.4rem;
  align-items: flex-start;
}
.detail-warning i { margin-top: 2px; flex-shrink: 0; }

/* Detail slide transition */
.slide-enter-active { transition: all 0.25s ease-out; }
.slide-leave-active { transition: all 0.2s ease-in; }
.slide-enter-from { opacity: 0; transform: translateX(20px); }
.slide-leave-to { opacity: 0; transform: translateX(20px); }

/* Footer */
.review-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 1.5rem;
  border-radius: 12px;
  margin-top: 0.75rem;
  flex-shrink: 0;
}
.review-stats {
  display: flex;
  gap: 1.5rem;
  font-size: 0.78rem;
  color: #999;
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

/* Buttons — use global .btn styles, no overrides */

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

/* Buttons — use global .btn styles, no overrides */
</style>
