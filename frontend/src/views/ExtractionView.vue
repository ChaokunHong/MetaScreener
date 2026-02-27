<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Data Extraction</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Upload extraction form (YAML) and PDFs, then extract structured data</p>

    <!-- Step 1: Upload PDFs -->
    <div class="glass-card">
      <div class="section-title">① Upload PDFs</div>
      <div
        class="upload-zone"
        @click="pdfInput?.click()"
        @dragover.prevent="draggingPdf = true"
        @dragleave="draggingPdf = false"
        @drop.prevent="onPdfDrop"
        :class="{ dragover: draggingPdf }"
        style="margin-bottom: 1rem;"
      >
        <input ref="pdfInput" type="file" accept=".pdf" multiple @change="onPdfChange" />
        <div style="font-size: 2rem; margin-bottom: 0.25rem;">📄</div>
        <div style="font-weight: 500;">
          {{ pdfFiles.length ? `${pdfFiles.length} file(s) selected` : 'Drop PDFs here or click to browse' }}
        </div>
      </div>

      <div v-if="pdfInfo" class="alert alert-success">
        ✓ Uploaded {{ pdfInfo.pdf_count }} PDFs — session: <code>{{ pdfInfo.session_id }}</code>
      </div>

      <button class="btn btn-primary" :disabled="!pdfFiles.length || uploadingPdfs" @click="doUploadPdfs">
        <span v-if="uploadingPdfs">⏳ Uploading…</span>
        <span v-else>Upload PDFs</span>
      </button>
    </div>

    <!-- Step 2: Upload Extraction Form -->
    <div v-if="sessionId" class="glass-card">
      <div class="section-title">② Upload Extraction Form (YAML)</div>
      <div class="form-group">
        <label class="form-label">YAML extraction form</label>
        <input ref="formInput" type="file" accept=".yaml,.yml" class="form-control" style="padding: 0.5rem;" @change="onFormChange" />
      </div>
      <div class="form-group">
        <label class="form-label">Or paste YAML content</label>
        <textarea v-model="formYaml" class="form-control" rows="6" placeholder="fields:&#10;  - name: sample_size&#10;    type: integer&#10;  - name: outcome&#10;    type: text"></textarea>
      </div>

      <div v-if="formInfo" class="alert alert-success">✓ Form uploaded: {{ formInfo.form_name }}</div>

      <button class="btn btn-primary" :disabled="!formYaml.trim() || uploadingForm" @click="doUploadForm">
        <span v-if="uploadingForm">⏳ Uploading…</span>
        <span v-else>Upload Form</span>
      </button>
    </div>

    <!-- Step 3: Run + Results -->
    <div v-if="formReady" class="glass-card">
      <div class="section-title">③ Extract Data</div>
      <div v-if="extractError" class="alert alert-danger">{{ extractError }}</div>

      <button class="btn btn-primary" :disabled="running" @click="doExtract" style="margin-bottom: 1rem;">
        <span v-if="running">⏳ Extracting…</span>
        <span v-else>▶ Extract Data</span>
      </button>

      <!-- Results table -->
      <div v-if="rows.length" style="margin-top: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.75rem;">
          <div class="section-title" style="margin-bottom: 0;">Extracted Data</div>
          <button class="btn btn-secondary btn-sm" @click="exportCSV">⬇ CSV</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paper</th>
                <th v-for="col in columns" :key="col">{{ col }}</th>
                <th>Consensus</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.paper_id">
                <td style="white-space: nowrap; max-width: 180px; overflow: hidden; text-overflow: ellipsis;">{{ row.paper_id }}</td>
                <td v-for="col in columns" :key="col">{{ row.fields?.[col] ?? '—' }}</td>
                <td>
                  <span v-if="row.consensus" style="color: #10b981;" title="All models agree">✓</span>
                  <span v-else style="color: #f59e0b;" title="Discrepancy between models">⚠</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiUpload, apiPost, apiGet } from '@/api'

// PDF upload
const pdfInput = ref<HTMLInputElement | null>(null)
const pdfFiles = ref<File[]>([])
const draggingPdf = ref(false)
const uploadingPdfs = ref(false)
const pdfInfo = ref<{ session_id: string; pdf_count: number } | null>(null)
const sessionId = ref<string | null>(null)

function onPdfChange(e: Event) {
  pdfFiles.value = Array.from((e.target as HTMLInputElement).files || [])
}
function onPdfDrop(e: DragEvent) {
  draggingPdf.value = false
  pdfFiles.value = Array.from(e.dataTransfer?.files || [])
}

async function doUploadPdfs() {
  if (!pdfFiles.value.length) return
  uploadingPdfs.value = true
  try {
    const fd = new FormData()
    pdfFiles.value.forEach(f => fd.append('files', f))
    const data = await apiUpload<{ session_id: string; pdf_count: number }>('/extraction/upload-pdfs', fd)
    pdfInfo.value = data
    sessionId.value = data.session_id
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploadingPdfs.value = false
  }
}

// Form upload
const formInput = ref<HTMLInputElement | null>(null)
const formYaml = ref('')
const uploadingForm = ref(false)
const formInfo = ref<{ form_name: string } | null>(null)
const formReady = ref(false)

async function onFormChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) formYaml.value = await f.text()
}

async function doUploadForm() {
  if (!sessionId.value || !formYaml.value.trim()) return
  uploadingForm.value = true
  try {
    const data = await apiPost<{ form_name: string }>(
      `/extraction/upload-form/${sessionId.value}`,
      { yaml_text: formYaml.value }
    )
    formInfo.value = data
    formReady.value = true
  } catch (e: unknown) {
    alert(`Form upload failed: ${(e as Error).message}`)
  } finally {
    uploadingForm.value = false
  }
}

// Run extraction
const running = ref(false)
const extractError = ref('')

interface ExtractionRow {
  paper_id: string
  fields?: Record<string, unknown>
  consensus?: boolean
}

const rows = ref<ExtractionRow[]>([])
const columns = computed<string[]>(() => {
  const first = rows.value[0]
  if (!rows.value.length || !first || !first.fields) return []
  return Object.keys(first.fields)
})

async function doExtract() {
  if (!sessionId.value) return
  running.value = true
  extractError.value = ''
  try {
    await apiPost(`/extraction/run/${sessionId.value}`, {})
    const data = await apiGet<{ results: ExtractionRow[] }>(`/extraction/results/${sessionId.value}`)
    rows.value = data.results || []
  } catch (e: unknown) {
    extractError.value = `Extraction failed: ${(e as Error).message}`
  } finally {
    running.value = false
  }
}

function exportCSV() {
  const cols = columns.value
  const headers = ['paper_id', ...cols, 'consensus']
  const rowData = rows.value.map(r => [
    `"${r.paper_id}"`,
    ...cols.map(c => `"${r.fields?.[c] ?? ''}"`),
    r.consensus ? 'true' : 'false',
  ])
  const csv = [headers, ...rowData].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'extraction_results.csv'; a.click()
  URL.revokeObjectURL(url)
}
</script>
