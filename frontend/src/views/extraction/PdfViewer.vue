<template>
  <div class="pdf-viewer-container">
    <div v-if="!pdfId" class="pdf-placeholder">
      <i class="fas fa-file-pdf" style="font-size: 2rem; color: #9ca3af;"></i>
      <p>Select a cell to view the source PDF</p>
    </div>

    <template v-else>
      <div v-if="loadError" class="pdf-placeholder">
        <i class="fas fa-exclamation-triangle" style="font-size: 1.5rem; color: #f59e0b;"></i>
        <p>{{ loadError }}</p>
      </div>

      <template v-else>
        <div class="pdf-controls">
          <button @click="prevPage" :disabled="currentPage <= 1" class="btn-icon">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="text-muted page-indicator">
            Page {{ currentPage }} / {{ totalPages }}
          </span>
          <button @click="nextPage" :disabled="currentPage >= totalPages" class="btn-icon">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>

        <div class="pdf-canvas-wrapper">
          <canvas ref="pdfCanvas" class="pdf-canvas"></canvas>
          <div v-if="rendering" class="pdf-loading-overlay">
            <i class="fas fa-spinner fa-spin"></i>
          </div>
        </div>
      </template>

      <div v-if="evidenceSentence" class="evidence-highlight-box">
        <div class="evidence-label"><i class="fas fa-quote-left"></i> Evidence</div>
        <div class="evidence-text">{{ evidenceSentence }}</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'

const API_BASE = '/api/extraction/v3'

interface EvidenceInfo {
  page?: number
  sentence?: string
  table_id?: string
}

const props = defineProps<{
  sessionId: string
  pdfId: string | null
  evidence: EvidenceInfo | null
}>()

const pdfCanvas = ref<HTMLCanvasElement | null>(null)
const currentPage = ref(1)
const totalPages = ref(0)
const rendering = ref(false)
const loadError = ref('')

let pdfDoc: any = null

const evidenceSentence = computed(() => {
  if (!props.evidence) return ''
  return props.evidence.sentence || props.evidence.table_id || ''
})

/** Check that pdf.js is loaded from CDN. */
function getPdfjsLib(): any {
  const lib = (window as any).pdfjsLib
  if (!lib) {
    loadError.value = 'pdf.js library not loaded. Check index.html.'
    return null
  }
  return lib
}

async function loadPdf(): Promise<void> {
  const pdfjsLib = getPdfjsLib()
  if (!pdfjsLib || !props.pdfId) return

  loadError.value = ''
  rendering.value = true
  pdfDoc = null
  totalPages.value = 0
  currentPage.value = 1

  try {
    const pdfUrl = `${API_BASE}/sessions/${props.sessionId}/pdfs/${props.pdfId}/file`
    const loadingTask = pdfjsLib.getDocument(pdfUrl)
    pdfDoc = await loadingTask.promise
    totalPages.value = pdfDoc.numPages
    await renderPage(1)
  } catch (err: any) {
    loadError.value = `Failed to load PDF: ${err.message || err}`
    rendering.value = false
  }
}

async function renderPage(pageNum: number): Promise<void> {
  if (!pdfDoc || !pdfCanvas.value) return

  rendering.value = true
  try {
    const page = await pdfDoc.getPage(pageNum)
    // Scale to fit the container width (~220px inner width for 250px panel)
    const desiredWidth = 218
    const unscaledViewport = page.getViewport({ scale: 1 })
    const scale = desiredWidth / unscaledViewport.width
    const viewport = page.getViewport({ scale })

    const canvas = pdfCanvas.value
    canvas.width = viewport.width
    canvas.height = viewport.height
    const ctx = canvas.getContext('2d')!
    await page.render({ canvasContext: ctx, viewport }).promise
    currentPage.value = pageNum
  } catch (err: any) {
    loadError.value = `Render error: ${err.message || err}`
  } finally {
    rendering.value = false
  }
}

function goToPage(num: number): void {
  if (num >= 1 && num <= totalPages.value) {
    renderPage(num)
  }
}

function prevPage(): void {
  goToPage(currentPage.value - 1)
}

function nextPage(): void {
  goToPage(currentPage.value + 1)
}

// When pdfId changes, load the new PDF
watch(() => props.pdfId, (newId) => {
  if (newId) loadPdf()
})

// When evidence changes, jump to the evidence page
watch(() => props.evidence, (ev) => {
  if (ev?.page && ev.page >= 1) {
    goToPage(ev.page)
  }
})

onMounted(() => {
  // Set pdf.js worker source if available
  const pdfjsLib = (window as any).pdfjsLib
  if (pdfjsLib && !pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js'
  }
  // If a pdfId is already set on mount, load it
  if (props.pdfId) loadPdf()
})
</script>

<style scoped>
.pdf-viewer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pdf-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  color: #6b7280;
  padding: 2rem 0.5rem;
  font-size: 0.85rem;
  gap: 0.5rem;
}

.pdf-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 0.4rem;
}

.page-indicator {
  font-size: 0.78rem;
  min-width: 80px;
  text-align: center;
}

.btn-icon {
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  padding: 0.2rem 0.5rem;
  cursor: pointer;
  color: #374151;
  font-size: 0.75rem;
  transition: background 0.15s;
}

.btn-icon:hover:not(:disabled) {
  background: #f3f4f6;
}

.btn-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pdf-canvas-wrapper {
  position: relative;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.pdf-canvas {
  display: block;
  width: 100%;
  height: auto;
}

.pdf-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.7);
  font-size: 1.25rem;
  color: #6b7280;
}

.evidence-highlight-box {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #fef3c7;
  border: 1px solid #fbbf24;
  border-radius: 0.375rem;
  font-size: 0.8rem;
}

.evidence-label {
  font-weight: 600;
  font-size: 0.72rem;
  color: #92400e;
  margin-bottom: 0.2rem;
}

.evidence-text {
  color: #78350f;
  line-height: 1.35;
}
</style>
