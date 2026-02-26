import { Fragment, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'
import { GlassButton } from '../components/glass/GlassButton'
import { apiUpload, apiPost } from '../api/client'
import { useQualityResults } from '../api/queries'
import type { QualityUploadResponse } from '../api/types'
import {
  Shield,
  Upload,
  FileUp,
  FileText,
  Play,
  Loader2,
  AlertTriangle,
  Download,
  ChevronDown,
  ChevronRight,
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

type RoBTool = 'rob2' | 'robins_i' | 'quadas2'

interface ToolOption {
  id: RoBTool
  name: string
  description: string
  domains: string
}

const TOOL_OPTIONS: ToolOption[] = [
  {
    id: 'rob2',
    name: 'RoB 2',
    description: 'Randomized controlled trials',
    domains: '5 domains',
  },
  {
    id: 'robins_i',
    name: 'ROBINS-I',
    description: 'Non-randomized studies of interventions',
    domains: '7 domains',
  },
  {
    id: 'quadas2',
    name: 'QUADAS-2',
    description: 'Diagnostic accuracy studies',
    domains: '4 domains',
  },
]

function judgementColor(judgement: string): string {
  const j = judgement.toUpperCase()
  if (j === 'LOW') return 'bg-green-400'
  if (j === 'SOME_CONCERNS' || j === 'MODERATE') return 'bg-yellow-400'
  if (j === 'HIGH' || j === 'SERIOUS' || j === 'CRITICAL') return 'bg-red-400'
  return 'bg-gray-400' // UNCLEAR
}

function judgementLabel(judgement: string): string {
  return judgement.replace(/_/g, ' ').toLowerCase()
}

interface UploadedFile {
  name: string
  size: number
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function Quality() {
  const queryClient = useQueryClient()
  const [selectedTool, setSelectedTool] = useState<RoBTool>('rob2')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [pdfCount, setPdfCount] = useState(0)
  const [pdfFiles, setPdfFiles] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())
  const [hasRun, setHasRun] = useState(false)

  const { data: qualityData } = useQualityResults(hasRun ? sessionId : null)

  const handlePdfUpload = useCallback(async (files: FileList) => {
    setError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i])
      }
      const resp = await apiUpload<QualityUploadResponse>(
        '/quality/upload-pdfs',
        formData,
      )
      setSessionId(resp.session_id)
      setPdfCount(resp.pdf_count)
      setPdfFiles(
        Array.from(files).map((f) => ({ name: f.name, size: f.size })),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const files = e.dataTransfer.files
      if (files.length > 0) void handlePdfUpload(files)
    },
    [handlePdfUpload],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) void handlePdfUpload(files)
  }

  const handleRun = async () => {
    if (!sessionId) return
    setRunning(true)
    setError(null)
    try {
      await apiPost(`/quality/run/${sessionId}?tool=${selectedTool}`)
      setHasRun(true)
      void queryClient.invalidateQueries({ queryKey: ['quality-results'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Assessment failed')
    } finally {
      setRunning(false)
    }
  }

  const toggleRow = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) {
        next.delete(idx)
      } else {
        next.add(idx)
      }
      return next
    })
  }

  const results = qualityData?.results ?? []

  // Extract domain columns from first result
  const domainColumns: string[] = []
  if (results.length > 0) {
    const first = results[0]
    const domains = first['domains']
    if (domains && typeof domains === 'object' && !Array.isArray(domains)) {
      domainColumns.push(...Object.keys(domains as Record<string, unknown>))
    }
  }

  const handleExportJSON = () => {
    if (results.length === 0) return
    downloadBlob(JSON.stringify(results, null, 2), 'quality_results.json', 'application/json')
  }

  const handleExportExcel = () => {
    // Excel export requires xlsx library; fall back to CSV download
    if (results.length === 0) return
    const header = ['Study', ...domainColumns, 'Overall'].join(',')
    const rows = results.map((row, idx) => {
      const domains = (row['domains'] as Record<string, Record<string, string>> | undefined) ?? {}
      const overall = String(row['overall'] ?? 'UNCLEAR')
      const studyId = String(row['record_id'] ?? row['study_id'] ?? `Study ${idx + 1}`)
      const domainValues = domainColumns.map((domain) => {
        const domainData = domains[domain]
        return typeof domainData === 'object' && domainData !== null
          ? String(domainData['judgement'] ?? 'UNCLEAR')
          : typeof domainData === 'string'
            ? domainData
            : 'UNCLEAR'
      })
      return [studyId, ...domainValues, overall].join(',')
    })
    alert('Excel export requires the xlsx library. Downloading as CSV instead.')
    downloadBlob([header, ...rows].join('\n'), 'quality_results.csv', 'text/csv')
  }

  return (
    <>
      <Header
        title="Quality Assessment"
        description="Risk of bias assessment using RoB 2, ROBINS-I, and QUADAS-2"
      />

      <div className="space-y-6">
        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 px-4 py-2 rounded-xl">
            <AlertTriangle size={16} />
            {error}
          </div>
        )}

        {/* Step 1: Configuration */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Shield size={20} className="text-amber-400" />
            <h3 className="text-lg font-semibold text-white">
              Assessment Tool
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {TOOL_OPTIONS.map((tool) => (
              <button
                key={tool.id}
                onClick={() => setSelectedTool(tool.id)}
                className={`p-4 rounded-xl text-left transition-all border ${
                  selectedTool === tool.id
                    ? 'border-purple-500/50 bg-purple-500/10'
                    : 'border-white/10 bg-white/5 hover:bg-white/10'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className={`w-3 h-3 rounded-full border-2 ${
                      selectedTool === tool.id
                        ? 'border-purple-400 bg-purple-400'
                        : 'border-white/30'
                    }`}
                  />
                  <span className="text-white font-medium">{tool.name}</span>
                </div>
                <p className="text-white/50 text-sm ml-5">
                  {tool.description}
                </p>
                <p className="text-white/30 text-xs ml-5 mt-0.5">
                  {tool.domains}
                </p>
              </button>
            ))}
          </div>
        </GlassCard>

        {/* PDF Upload */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Upload size={20} className="text-amber-400" />
            <h3 className="text-lg font-semibold text-white">Upload PDFs</h3>
          </div>

          {pdfCount > 0 ? (
            <>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <FileUp size={20} className="text-green-400" />
                  <div>
                    <p className="text-white font-medium">
                      {pdfCount} PDFs uploaded
                    </p>
                    <p className="text-white/50 text-sm">
                      Tool:{' '}
                      {TOOL_OPTIONS.find((t) => t.id === selectedTool)?.name}
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
                        Assessing...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> Run Assessment
                      </>
                    )}
                  </span>
                </GlassButton>
              </div>

              {/* File list */}
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
            </>
          ) : (
            <div
              onDrop={handleDrop}
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
                Select multiple PDFs for batch assessment
              </p>
              <label>
                <input
                  type="file"
                  accept=".pdf"
                  multiple
                  onChange={handleInputChange}
                  className="hidden"
                />
                <GlassButton variant="outline" disabled={uploading}>
                  {uploading ? 'Uploading...' : 'Browse PDFs'}
                </GlassButton>
              </label>
            </div>
          )}
        </GlassCard>

        {/* Step 2: Results - Traffic Light Table */}
        {results.length > 0 && (
          <GlassCard>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">
                Risk of Bias Results ({qualityData?.tool?.toUpperCase()})
              </h3>
              <div className="flex gap-2">
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

            {/* Legend */}
            <div className="flex items-center gap-4 mb-4 text-xs text-white/50">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-green-400" />
                Low
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-yellow-400" />
                Some concerns
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-red-400" />
                High
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-gray-400" />
                Unclear
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-white/50 text-xs uppercase tracking-wider py-2 px-3 w-8" />
                    <th className="text-left text-white/50 text-xs uppercase tracking-wider py-2 px-3">
                      Study
                    </th>
                    {domainColumns.map((domain) => (
                      <th
                        key={domain}
                        className="text-center text-white/50 text-xs uppercase tracking-wider py-2 px-3"
                      >
                        {domain.replace(/_/g, ' ')}
                      </th>
                    ))}
                    <th className="text-center text-white/50 text-xs uppercase tracking-wider py-2 px-3">
                      Overall
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, idx) => {
                    const domains =
                      (row['domains'] as Record<string, Record<string, string>> | undefined) ?? {}
                    const overall = String(row['overall'] ?? 'UNCLEAR')
                    const studyId = String(row['record_id'] ?? row['study_id'] ?? `Study ${idx + 1}`)
                    const isExpanded = expandedRows.has(idx)

                    return (
                      <Fragment key={idx}>
                        <tr
                          className="border-b border-white/5 hover:bg-white/5 cursor-pointer"
                          onClick={() => toggleRow(idx)}
                        >
                          <td className="py-2 px-3 text-white/40">
                            {isExpanded ? (
                              <ChevronDown size={14} />
                            ) : (
                              <ChevronRight size={14} />
                            )}
                          </td>
                          <td className="py-2 px-3 text-white/80 font-medium">
                            {studyId}
                          </td>
                          {domainColumns.map((domain) => {
                            const domainData = domains[domain]
                            const judgement =
                              typeof domainData === 'object' && domainData !== null
                                ? String(domainData['judgement'] ?? 'UNCLEAR')
                                : typeof domainData === 'string'
                                  ? domainData
                                  : 'UNCLEAR'
                            return (
                              <td
                                key={domain}
                                className="py-2 px-3 text-center"
                              >
                                <div
                                  className={`w-4 h-4 rounded-full mx-auto ${judgementColor(judgement)}`}
                                  title={judgementLabel(judgement)}
                                />
                              </td>
                            )
                          })}
                          <td className="py-2 px-3 text-center">
                            <div
                              className={`w-4 h-4 rounded-full mx-auto ${judgementColor(overall)}`}
                              title={judgementLabel(overall)}
                            />
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="border-b border-white/5">
                            <td />
                            <td
                              colSpan={domainColumns.length + 1}
                              className="py-3 px-3"
                            >
                              <div className="space-y-2">
                                {domainColumns.map((domain) => {
                                  const domainData = domains[domain]
                                  const rationale =
                                    typeof domainData === 'object' && domainData !== null
                                      ? String(domainData['rationale'] ?? 'No rationale provided')
                                      : 'No rationale provided'
                                  const judgement =
                                    typeof domainData === 'object' && domainData !== null
                                      ? String(domainData['judgement'] ?? 'UNCLEAR')
                                      : typeof domainData === 'string'
                                        ? domainData
                                        : 'UNCLEAR'
                                  return (
                                    <div
                                      key={domain}
                                      className="flex gap-3 p-2 rounded-lg bg-white/5"
                                    >
                                      <div
                                        className={`w-3 h-3 rounded-full mt-1 shrink-0 ${judgementColor(judgement)}`}
                                      />
                                      <div>
                                        <p className="text-white/70 text-xs font-medium uppercase tracking-wider">
                                          {domain.replace(/_/g, ' ')} &mdash;{' '}
                                          {judgementLabel(judgement)}
                                        </p>
                                        <p className="text-white/50 text-xs mt-0.5">
                                          {rationale}
                                        </p>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </GlassCard>
        )}

        {/* Empty state */}
        {hasRun && results.length === 0 && !running && (
          <GlassCard>
            <p className="text-white/50 text-center py-8">
              No results yet. The assessment may still be processing.
            </p>
          </GlassCard>
        )}
      </div>
    </>
  )
}
