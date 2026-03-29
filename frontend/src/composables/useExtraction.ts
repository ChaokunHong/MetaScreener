/**
 * Composable: extraction session lifecycle (run, poll, cancel, export).
 */
import { ref, onUnmounted } from 'vue'

const API_BASE = '/api/extraction/v3'

export interface ResultCell {
  pdf_id: string
  field_name: string
  value: unknown
  confidence: string
  strategy: string
  evidence_json?: string
}

export interface PdfEntry {
  pdf_id: string
  filename: string
}

export interface SchemaSheetInfo {
  name: string
  fields: number
}

export interface SchemaInfo {
  session_id: string
  sheets: SchemaSheetInfo[]
}

export function useExtraction() {
  const sessionId = ref('')
  const isRunning = ref(false)
  const progress = ref(0)
  const extractionDone = ref(false)
  const runError = ref('')
  const results = ref<ResultCell[]>([])
  const loadingResults = ref(false)
  const pdfs = ref<PdfEntry[]>([])
  const error = ref('')
  const activeEventSource = ref<EventSource | null>(null)

  /* -- export -- */
  const exporting = ref(false)
  const exportFormat = ref('')
  const exportPath = ref('')

  onUnmounted(() => {
    if (activeEventSource.value) {
      activeEventSource.value.close()
      activeEventSource.value = null
    }
  })

  async function runExtraction(): Promise<void> {
    isRunning.value = true
    extractionDone.value = false
    runError.value = ''
    error.value = ''
    progress.value = 0

    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/run`, { method: 'POST' })
      if (!resp.ok) throw new Error(await resp.text())

      const eventSource = new EventSource(`${API_BASE}/sessions/${sessionId.value}/events`)
      activeEventSource.value = eventSource

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          progress.value = data.progress || 0
        } catch { /* ignore */ }
      }

      eventSource.addEventListener('batch_done', async () => {
        eventSource.close()
        activeEventSource.value = null
        progress.value = 1.0
        const resultsResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/results`)
        results.value = await resultsResp.json()
        extractionDone.value = true
        isRunning.value = false
      })

      eventSource.addEventListener('pdf_done', (event) => {
        try {
          const data = JSON.parse(event.data)
          progress.value = data.progress || progress.value
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('warning', (event) => {
        try {
          const data = JSON.parse(event.data)
          runError.value = data.details?.message || 'Warning from server'
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('idle', () => {
        eventSource.close()
        activeEventSource.value = null
        pollForCompletion()
      })

      eventSource.onerror = () => {
        eventSource.close()
        activeEventSource.value = null
        pollForCompletion()
      }
    } catch (e: any) {
      runError.value = e.message
      isRunning.value = false
    }
  }

  async function cancelExtraction(): Promise<void> {
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

  async function pollForCompletion(): Promise<void> {
    const maxAttempts = 150
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
      } catch { /* ignore */ }
    }
    runError.value = 'Extraction timed out'
    isRunning.value = false
  }

  async function exportResults(format: string): Promise<void> {
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
        console.warn('download_endpoint_failed', downloadResp.status)
      }
    } catch (e: any) {
      error.value = e.message
    } finally {
      exporting.value = false
      exportFormat.value = ''
    }
  }

  async function deletePdf(pdfId: string): Promise<void> {
    const ok = window.confirm('Remove this PDF from the session?')
    if (!ok) return
    try {
      const resp = await fetch(
        `${API_BASE}/sessions/${sessionId.value}/pdfs/${pdfId}`,
        { method: 'DELETE' }
      )
      if (!resp.ok) throw new Error('Delete failed')
      pdfs.value = pdfs.value.filter(p => p.pdf_id !== pdfId)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function uploadPdfs(files: File[], uploadingPdf: { value: boolean }): Promise<void> {
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

  return {
    sessionId,
    isRunning,
    progress,
    extractionDone,
    runError,
    results,
    loadingResults,
    pdfs,
    error,
    exporting,
    exportFormat,
    exportPath,
    runExtraction,
    cancelExtraction,
    exportResults,
    deletePdf,
    uploadPdfs,
  }
}
