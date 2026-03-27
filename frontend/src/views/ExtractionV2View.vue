<!-- frontend/src/views/ExtractionV2View.vue -->
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
    <!-- Step indicator — horizontal stepper -->
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

      <!-- Glass progress bar -->
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

    <!-- Step 2: Confirm Schema -->
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

    <!-- Step 3: Upload PDFs -->
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

    <!-- Info Modals -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="activeModal" class="modal-overlay" @click.self="activeModal = null">
          <div class="modal-glass-panel">
            <div class="modal-refraction"></div>
            <button class="modal-close" @click="activeModal = null">
              <i class="fas fa-times"></i>
            </button>

            <!-- Schema Analysis -->
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

            <!-- Sheet Detection -->
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

            <!-- Mapping Tables -->
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

            <!-- Plugin -->
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
