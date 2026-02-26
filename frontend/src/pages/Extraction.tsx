import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'
import { GlassButton } from '../components/glass/GlassButton'
import { Stepper } from '../components/screening/Stepper'
import { apiUpload, apiPost } from '../api/client'
import { useExtractionResults } from '../api/queries'
import type { ExtractionUploadResponse } from '../api/types'
import {
  Upload,
  FileUp,
  FileText,
  Play,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Download,
  X,
} from 'lucide-react'

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const STEPS = ['Upload Form', 'Upload PDFs', 'Extract & Review']

interface UploadedFile {
  name: string
  size: number
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function Extraction() {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [formFilename, setFormFilename] = useState<string | null>(null)
  const [pdfFiles, setPdfFiles] = useState<UploadedFile[]>([])
  const [pdfCount, setPdfCount] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [editedResults, setEditedResults] = useState<Record<string, unknown>[] | null>(null)

  const { data: extractionData } = useExtractionResults(
    step === 2 ? sessionId : null,
  )

  // Step 1: Upload YAML form
  const handleFormUpload = useCallback(async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      // First upload PDFs to create session if needed, or upload form
      // For form upload, we need a session first. We'll upload it in step 2.
      setFormFilename(file.name)
      // Store the file for later upload after PDF session is created
      setFormFile(file)
      setStep(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  // We store the form file to upload after session creation
  const [formFile, setFormFile] = useState<File | null>(null)

  const handleFormDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) void handleFormUpload(file)
    },
    [handleFormUpload],
  )

  const handleFormInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void handleFormUpload(file)
  }

  // Step 2: Upload PDFs
  const handlePdfUpload = useCallback(
    async (files: FileList) => {
      setError(null)
      setUploading(true)
      try {
        const formData = new FormData()
        for (let i = 0; i < files.length; i++) {
          formData.append('files', files[i])
        }
        const resp = await apiUpload<ExtractionUploadResponse>(
          '/extraction/upload-pdfs',
          formData,
        )
        setSessionId(resp.session_id)
        setPdfCount(resp.pdf_count)
        setPdfFiles(
          Array.from(files).map((f) => ({ name: f.name, size: f.size })),
        )

        // Now upload the form YAML to the session
        if (formFile) {
          const formFormData = new FormData()
          formFormData.append('file', formFile)
          await apiUpload(
            `/extraction/upload-form/${resp.session_id}`,
            formFormData,
          )
        }

        setStep(2)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [formFile],
  )

  const handlePdfDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const files = e.dataTransfer.files
      if (files.length > 0) void handlePdfUpload(files)
    },
    [handlePdfUpload],
  )

  const handlePdfInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) void handlePdfUpload(files)
  }

  // Step 3: Run extraction
  const handleRun = async () => {
    if (!sessionId) return
    setRunning(true)
    setError(null)
    try {
      await apiPost(`/extraction/run/${sessionId}`)
      setEditedResults(null)
      void queryClient.invalidateQueries({ queryKey: ['extraction-results'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
    } finally {
      setRunning(false)
    }
  }

  const rawResults = extractionData?.results ?? []
  const results = editedResults ?? rawResults
  const resultColumns =
    results.length > 0 ? Object.keys(results[0]) : []

  const handleCellEdit = (rowIdx: number, col: string, value: string) => {
    const updated = [...results]
    updated[rowIdx] = { ...updated[rowIdx], [col]: value }
    setEditedResults(updated)
  }

  const handleExportCSV = () => {
    if (results.length === 0) return
    const cols = resultColumns
    const header = cols.join(',')
    const rows = results.map((row) =>
      cols.map((col) => {
        const val = String(row[col] ?? '')
        return val.includes(',') || val.includes('"') || val.includes('\n')
          ? `"${val.replace(/"/g, '""')}"`
          : val
      }).join(','),
    )
    downloadBlob([header, ...rows].join('\n'), 'extraction_results.csv', 'text/csv')
  }

  const handleExportJSON = () => {
    if (results.length === 0) return
    downloadBlob(JSON.stringify(results, null, 2), 'extraction_results.json', 'application/json')
  }

  const handleExportExcel = () => {
    // Excel export requires xlsx library; fall back to CSV download
    alert('Excel export requires the xlsx library. Downloading as CSV instead.')
    handleExportCSV()
  }

  return (
    <>
      <Header
        title="Data Extraction"
        description="Structured data extraction from included studies"
      />

      <Stepper steps={STEPS} currentStep={step} />

      <div className="space-y-6">
        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 px-4 py-2 rounded-xl">
            <AlertTriangle size={16} />
            {error}
          </div>
        )}

        {/* Step 1: Upload Extraction Form YAML */}
        {step === 0 && (
          <GlassCard>
            <div className="flex items-center gap-2 mb-4">
              <FileText size={20} className="text-cyan-400" />
              <h3 className="text-lg font-semibold text-white">
                Upload Extraction Form
              </h3>
            </div>
            <p className="text-white/50 text-sm mb-4">
              Upload a YAML file defining the fields to extract from each study.
              Use{' '}
              <code className="text-purple-300 bg-white/5 px-1 rounded">
                metascreener init-form
              </code>{' '}
              to generate one.
            </p>

            <div
              onDrop={handleFormDrop}
              onDragOver={(e) => {
                e.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={() => setIsDragging(false)}
              className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                isDragging
                  ? 'border-purple-400 bg-purple-500/10'
                  : 'border-white/20 hover:border-white/30'
              }`}
            >
              <Upload size={40} className="mx-auto text-white/30 mb-4" />
              <p className="text-white/70 mb-2">
                Drag & drop your extraction form YAML
              </p>
              <p className="text-white/40 text-sm mb-4">
                Supports .yaml, .yml files
              </p>
              <label>
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={handleFormInputChange}
                  className="hidden"
                />
                <GlassButton variant="outline" disabled={uploading}>
                  {uploading ? 'Uploading...' : 'Browse Files'}
                </GlassButton>
              </label>
            </div>
          </GlassCard>
        )}

        {/* Step 2: Upload PDFs */}
        {step === 1 && (
          <>
            {/* Show uploaded form */}
            <GlassCard variant="subtle">
              <div className="flex items-center gap-3">
                <FileUp size={20} className="text-green-400" />
                <div className="flex-1">
                  <p className="text-white font-medium">{formFilename}</p>
                  <p className="text-white/50 text-sm">
                    Extraction form loaded
                  </p>
                </div>
                <GlassButton
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setStep(0)
                    setFormFilename(null)
                    setFormFile(null)
                  }}
                >
                  <X size={16} />
                </GlassButton>
              </div>
            </GlassCard>

            <GlassCard>
              <div className="flex items-center gap-2 mb-4">
                <Upload size={20} className="text-cyan-400" />
                <h3 className="text-lg font-semibold text-white">
                  Upload PDFs
                </h3>
              </div>
              <p className="text-white/50 text-sm mb-4">
                Upload the PDF files of included studies for data extraction.
              </p>

              <div
                onDrop={handlePdfDrop}
                onDragOver={(e) => {
                  e.preventDefault()
                  setIsDragging(true)
                }}
                onDragLeave={() => setIsDragging(false)}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  isDragging
                    ? 'border-purple-400 bg-purple-500/10'
                    : 'border-white/20 hover:border-white/30'
                }`}
              >
                <Upload size={40} className="mx-auto text-white/30 mb-4" />
                <p className="text-white/70 mb-2">
                  Drag & drop PDF files here
                </p>
                <p className="text-white/40 text-sm mb-4">
                  Select multiple PDF files for batch extraction
                </p>
                <label>
                  <input
                    type="file"
                    accept=".pdf"
                    multiple
                    onChange={handlePdfInputChange}
                    className="hidden"
                  />
                  <GlassButton variant="outline" disabled={uploading}>
                    {uploading ? 'Uploading...' : 'Browse PDFs'}
                  </GlassButton>
                </label>
              </div>
            </GlassCard>
          </>
        )}

        {/* Step 3: Results */}
        {step === 2 && (
          <>
            {/* Upload summary */}
            <GlassCard variant="subtle">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileUp size={20} className="text-green-400" />
                  <div>
                    <p className="text-white font-medium">
                      {formFilename} + {pdfCount} PDFs
                    </p>
                    <p className="text-white/50 text-sm">
                      Ready for extraction
                    </p>
                  </div>
                </div>
                <GlassButton
                  onClick={() => { void handleRun() }}
                  disabled={running}
                >
                  <span className="flex items-center gap-2">
                    {running ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Extracting...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> Run Extraction
                      </>
                    )}
                  </span>
                </GlassButton>
              </div>
            </GlassCard>

            {/* PDF file list */}
            {pdfFiles.length > 0 && (
              <GlassCard>
                <h3 className="text-white font-medium mb-3">
                  Uploaded Files ({pdfFiles.length})
                </h3>
                <div className="space-y-1">
                  {pdfFiles.map((f) => (
                    <div
                      key={f.name}
                      className="flex items-center justify-between p-2 rounded-lg bg-white/5"
                    >
                      <div className="flex items-center gap-2">
                        <FileText size={14} className="text-white/40" />
                        <span className="text-sm text-white/80">{f.name}</span>
                      </div>
                      <span className="text-xs text-white/40">
                        {formatFileSize(f.size)}
                      </span>
                    </div>
                  ))}
                </div>
              </GlassCard>
            )}

            {/* Results table */}
            {results.length > 0 && (
              <GlassCard>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">
                    Extraction Results
                  </h3>
                  <div className="flex gap-2">
                    <GlassButton variant="outline" size="sm" onClick={handleExportCSV}>
                      <span className="flex items-center gap-2">
                        <Download size={14} /> CSV
                      </span>
                    </GlassButton>
                    <GlassButton variant="outline" size="sm" onClick={handleExportJSON}>
                      <span className="flex items-center gap-2">
                        <Download size={14} /> JSON
                      </span>
                    </GlassButton>
                    <GlassButton variant="outline" size="sm" onClick={handleExportExcel}>
                      <span className="flex items-center gap-2">
                        <Download size={14} /> Excel
                      </span>
                    </GlassButton>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        {resultColumns.map((col) => (
                          <th
                            key={col}
                            className="text-left text-white/50 text-xs uppercase tracking-wider py-2 px-3"
                          >
                            {col}
                          </th>
                        ))}
                        <th className="text-left text-white/50 text-xs uppercase tracking-wider py-2 px-3">
                          Consensus
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((row, rowIdx) => (
                        <tr
                          key={rowIdx}
                          className="border-b border-white/5 hover:bg-white/5"
                        >
                          {resultColumns.map((col) => (
                            <td
                              key={col}
                              contentEditable
                              suppressContentEditableWarning
                              onBlur={(e) => {
                                handleCellEdit(rowIdx, col, e.currentTarget.textContent ?? '')
                              }}
                              className="text-white/80 py-2 px-3 cursor-text focus:outline-none focus:ring-1 focus:ring-purple-500/50 focus:bg-white/5 rounded"
                            >
                              {String(row[col] ?? '\u2014')}
                            </td>
                          ))}
                          <td className="py-2 px-3">
                            {row['consensus'] === true ? (
                              <CheckCircle
                                size={16}
                                className="text-green-400"
                              />
                            ) : (
                              <AlertTriangle
                                size={16}
                                className="text-amber-400"
                              />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </GlassCard>
            )}

            {results.length === 0 && !running && (
              <GlassCard>
                <p className="text-white/50 text-center py-8">
                  Click &quot;Run Extraction&quot; to begin multi-LLM parallel
                  extraction with consensus validation.
                </p>
              </GlassCard>
            )}
          </>
        )}
      </div>
    </>
  )
}
