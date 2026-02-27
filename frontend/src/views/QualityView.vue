<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Quality Assessment</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Assess risk of bias using RoB 2, ROBINS-I, or QUADAS-2</p>

    <!-- Step 1: Tool selection -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-tools"></i> Select Assessment Tool</div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 0.75rem;">
        <div
          v-for="tool in tools"
          :key="tool.id"
          class="glass-section"
          :style="{
            marginBottom: 0,
            cursor: 'pointer',
            border: selectedTool === tool.id ? '2px solid var(--primary-purple)' : undefined,
            transition: 'all 0.2s ease'
          }"
          @click="selectedTool = tool.id"
        >
          <div style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--primary-purple);"><i :class="tool.icon"></i></div>
          <div style="font-weight: 600; color: var(--text-primary);">{{ tool.name }}</div>
          <div class="text-muted" style="font-size: 0.8rem; margin-top: 0.25rem;">{{ tool.desc }}</div>
        </div>
      </div>
    </div>

    <!-- Step 2: Upload PDFs -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-file-pdf"></i> Upload PDFs</div>
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
        <i class="fas fa-file-pdf zone-icon"></i>
        <div class="zone-title">{{ pdfFiles.length ? `${pdfFiles.length} PDF(s) selected` : 'Drop PDFs here or click to browse' }}</div>
      </div>

      <div v-if="uploadInfo" class="alert alert-success">
        <i class="fas fa-check-circle"></i>
        {{ uploadInfo.pdf_count }} PDFs uploaded — session: <code>{{ uploadInfo.session_id }}</code>
      </div>

      <button class="btn btn-primary" :disabled="!pdfFiles.length || uploadingPdfs" @click="doUploadPdfs">
        <i v-if="uploadingPdfs" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-upload"></i>
        {{ uploadingPdfs ? 'Uploading…' : 'Upload PDFs' }}
      </button>
    </div>

    <!-- Step 3: Run -->
    <div v-if="sessionId" class="glass-card">
      <div class="section-title"><i class="fas fa-clipboard-list"></i> Assess Quality</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Tool: <strong>{{ selectedTool }}</strong> — {{ pdfFiles.length }} papers to assess
      </p>

      <div v-if="robError" class="alert alert-danger">{{ robError }}</div>

      <button class="btn btn-primary" :disabled="running || !selectedTool" @click="doAssess" style="margin-bottom: 1rem;">
        <i v-if="running" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-play"></i>
        {{ running ? 'Assessing…' : 'Assess Quality' }}
      </button>

      <!-- Traffic-light results table -->
      <div v-if="results.length">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.75rem;">
          <div class="section-title" style="margin-bottom: 0;"><i class="fas fa-traffic-light"></i> Results — Traffic Light</div>
          <button class="btn btn-secondary btn-sm" @click="exportCSV"><i class="fas fa-download"></i> CSV</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paper</th>
                <th v-for="domain in domains" :key="domain">{{ domain }}</th>
                <th>Overall</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in results" :key="r.paper_id">
                <td style="white-space: nowrap; max-width: 180px; overflow: hidden; text-overflow: ellipsis;">{{ r.paper_id }}</td>
                <td
                  v-for="domain in domains"
                  :key="domain"
                  :class="robClass(r.domains?.[domain])"
                  style="text-align: center; font-size: 0.8rem; font-weight: 500;"
                >{{ r.domains?.[domain] || '—' }}</td>
                <td
                  :class="robClass(r.overall)"
                  style="text-align: center; font-weight: 600; font-size: 0.8rem;"
                >{{ r.overall || '—' }}</td>
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

const tools = [
  { id: 'rob2',     icon: 'fas fa-dice',       name: 'RoB 2',     desc: 'Randomised trials — 5 domains' },
  { id: 'robins_i', icon: 'fas fa-microscope', name: 'ROBINS-I',  desc: 'Observational studies — 7 domains' },
  { id: 'quadas2',  icon: 'fas fa-search',     name: 'QUADAS-2',  desc: 'Diagnostic accuracy — 4 domains' },
]
const selectedTool = ref('rob2')

// PDF upload
const pdfInput = ref<HTMLInputElement | null>(null)
const pdfFiles = ref<File[]>([])
const draggingPdf = ref(false)
const uploadingPdfs = ref(false)
const uploadInfo = ref<{ session_id: string; pdf_count: number } | null>(null)
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
    const data = await apiUpload<{ session_id: string; pdf_count: number }>('/quality/upload-pdfs', fd)
    uploadInfo.value = data
    sessionId.value = data.session_id
  } catch (e: unknown) {
    alert(`Upload failed: ${(e as Error).message}`)
  } finally {
    uploadingPdfs.value = false
  }
}

// Assess
const running = ref(false)
const robError = ref('')

interface RoBResult {
  paper_id: string
  overall?: string
  domains?: Record<string, string>
}

const results = ref<RoBResult[]>([])

const domains = computed<string[]>(() => {
  const first = results.value[0]
  if (!results.value.length || !first || !first.domains) return []
  return Object.keys(first.domains)
})

async function doAssess() {
  if (!sessionId.value || !selectedTool.value) return
  running.value = true
  robError.value = ''
  try {
    await apiPost(`/quality/run/${sessionId.value}?tool=${selectedTool.value}`, {})
    const data = await apiGet<{ results: RoBResult[] }>(`/quality/results/${sessionId.value}`)
    results.value = data.results || []
  } catch (e: unknown) {
    robError.value = `Assessment failed: ${(e as Error).message}`
  } finally {
    running.value = false
  }
}

function robClass(judgement?: string): string {
  if (!judgement) return ''
  const j = judgement.toLowerCase()
  if (j.includes('low')) return 'rob-low'
  if (j.includes('high') || j.includes('critical') || j.includes('serious')) return 'rob-high'
  if (j.includes('concern') || j.includes('moderate')) return 'rob-concerns'
  return 'rob-unclear'
}

function exportCSV() {
  const cols = domains.value
  const headers = ['paper_id', ...cols, 'overall']
  const rows2 = results.value.map(r => [
    `"${r.paper_id}"`,
    ...cols.map(c => `"${r.domains?.[c] ?? ''}"`),
    `"${r.overall ?? ''}"`,
  ])
  const csv = [headers, ...rows2].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'quality_results.csv'; a.click()
  URL.revokeObjectURL(url)
}
</script>
