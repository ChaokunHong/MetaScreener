/**
 * Composable: extraction session lifecycle (run, poll, cancel, pause/resume, export).
 */
import { ref, nextTick, onUnmounted } from 'vue'

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
  const isPaused = ref(false)
  const progress = ref(0)
  const completedPdfs = ref(0)
  const extractionDone = ref(false)
  const runError = ref('')
  const results = ref<ResultCell[]>([])
  const loadingResults = ref(false)
  const pdfs = ref<PdfEntry[]>([])
  const error = ref('')
  const activeEventSource = ref<EventSource | null>(null)

  /* -- log window -- */
  const logLines = ref<string[]>([])
  const logEl = ref<HTMLElement | null>(null)

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

  function _ts(): string {
    return `[${new Date().toLocaleTimeString()}]`
  }

  function _pushLog(line: string): void {
    logLines.value.push(line)
    nextTick(() => {
      if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
    })
  }

  async function runExtraction(): Promise<void> {
    isRunning.value = true
    isPaused.value = false
    extractionDone.value = false
    runError.value = ''
    error.value = ''
    progress.value = 0
    completedPdfs.value = 0
    logLines.value = []

    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/run`, { method: 'POST' })
      if (!resp.ok) throw new Error(await resp.text())

      const eventSource = new EventSource(`${API_BASE}/sessions/${sessionId.value}/events`)
      activeEventSource.value = eventSource

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.progress != null) progress.value = data.progress
        } catch { /* ignore */ }
      }

      eventSource.addEventListener('pdf_start', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          const name = data.details?.pdf || 'PDF'
          _pushLog(`${_ts()} Starting: ${name}`)
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('doc_parsed', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          const name = data.details?.pdf || 'document'
          _pushLog(`${_ts()} Parsed: ${name}`)
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('pdf_done', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          const name = data.details?.pdf || 'PDF'
          if (data.progress != null) progress.value = data.progress
          completedPdfs.value++
          _pushLog(`${_ts()} \u2713 Completed: ${name}`)
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('pdf_error', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          const name = data.details?.pdf || 'PDF'
          const reason = data.details?.error || data.details?.reason || 'unknown'
          if (data.progress != null) progress.value = data.progress
          completedPdfs.value++
          _pushLog(`${_ts()} \u2717 Error: ${name} \u2014 ${reason}`)
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('warning', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          const msg = data.details?.message || 'Warning'
          runError.value = msg
          _pushLog(`${_ts()} \u26a0 ${msg}`)
        } catch { /* ignore */ }
      })

      eventSource.addEventListener('paused', () => {
        isPaused.value = true
        _pushLog(`${_ts()} \u23f8 Paused`)
      })

      eventSource.addEventListener('resumed', () => {
        isPaused.value = false
        _pushLog(`${_ts()} \u25b6 Resumed`)
      })

      eventSource.addEventListener('batch_done', async () => {
        eventSource.close()
        activeEventSource.value = null
        progress.value = 1.0
        isPaused.value = false
        const resultsResp = await fetch(`${API_BASE}/sessions/${sessionId.value}/results`)
        results.value = await resultsResp.json()
        extractionDone.value = true
        isRunning.value = false
        _pushLog(`${_ts()} \u2713 Extraction complete`)
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
      isPaused.value = false
      progress.value = 0
      if (activeEventSource.value) {
        activeEventSource.value.close()
        activeEventSource.value = null
      }
    }
  }

  async function pauseExtraction(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/pause`, { method: 'POST' })
      if (!resp.ok) throw new Error(await resp.text())
      isPaused.value = true
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function resumeExtraction(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId.value}/resume`, { method: 'POST' })
      if (!resp.ok) throw new Error(await resp.text())
      isPaused.value = false
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function pollForCompletion(): Promise<void> {
    const maxAttempts = 900  // 30 minutes (900 × 2s)
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
          isPaused.value = false
          progress.value = 1.0
          return
        }
      } catch { /* ignore */ }
    }
    runError.value = 'Extraction timed out'
    isRunning.value = false
    isPaused.value = false
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
    isPaused,
    progress,
    completedPdfs,
    extractionDone,
    runError,
    results,
    loadingResults,
    pdfs,
    error,
    logLines,
    logEl,
    exporting,
    exportFormat,
    exportPath,
    runExtraction,
    cancelExtraction,
    pauseExtraction,
    resumeExtraction,
    exportResults,
    deletePdf,
    uploadPdfs,
  }
}
