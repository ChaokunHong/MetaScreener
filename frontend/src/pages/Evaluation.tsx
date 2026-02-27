import { useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'
import { GlassButton } from '../components/glass/GlassButton'
import { apiUpload, apiPost } from '../api/client'
import { useEvaluationResults, useScreeningSessions } from '../api/queries'
import type { EvaluationUploadResponse, EvaluationMetrics } from '../api/types'
import {
  Upload,
  FileUp,
  Play,
  BarChart3,
  Copy,
  Check,
  Download,
  Loader2,
  Image as ImageIcon,
  FileCode,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  ReferenceLine,
  Area,
  AreaChart,
} from 'recharts'

type ChartTab = 'roc' | 'calibration' | 'distribution'

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  downloadBinaryBlob(blob, filename)
}

function downloadBinaryBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function chartFilename(tab: ChartTab, ext: 'png' | 'svg'): string {
  const base =
    tab === 'roc'
      ? 'roc_curve'
      : tab === 'calibration'
        ? 'calibration_plot'
        : 'score_distribution'
  return `evaluation_${base}.${ext}`
}

function parseSvgPxDimension(value: string | null): number | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed || trimmed.endsWith('%')) return null
  const n = Number.parseFloat(trimmed)
  return Number.isFinite(n) ? n : null
}

function serializeChartSvg(container: HTMLDivElement): { svgText: string; width: number; height: number } {
  const svg = container.querySelector('svg')
  if (!(svg instanceof SVGSVGElement)) {
    throw new Error('No chart SVG found to export')
  }

  const rect = container.getBoundingClientRect()
  const attrWidth = parseSvgPxDimension(svg.getAttribute('width'))
  const attrHeight = parseSvgPxDimension(svg.getAttribute('height'))
  const widthFallback = rect.width > 0 ? rect.width : 800
  const heightFallback = rect.height > 0 ? rect.height : 320
  const width = Math.max(1, Math.round(attrWidth ?? widthFallback))
  const height = Math.max(1, Math.round(attrHeight ?? heightFallback))

  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  if (!clone.getAttribute('viewBox')) {
    clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  }

  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('x', '0')
  bg.setAttribute('y', '0')
  bg.setAttribute('width', String(width))
  bg.setAttribute('height', String(height))
  bg.setAttribute('fill', '#080b12')
  clone.insertBefore(bg, clone.firstChild)

  const svgText = new XMLSerializer().serializeToString(clone)
  return { svgText, width, height }
}

function loadImageFromUrl(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Failed to render chart image'))
    img.src = url
  })
}

async function exportChartAsSvg(container: HTMLDivElement, filename: string): Promise<void> {
  const { svgText } = serializeChartSvg(container)
  const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' })
  downloadBinaryBlob(blob, filename)
}

async function exportChartAsPng(container: HTMLDivElement, filename: string): Promise<void> {
  const { svgText, width, height } = serializeChartSvg(container)
  const svgBlob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' })
  const svgUrl = URL.createObjectURL(svgBlob)

  try {
    const img = await loadImageFromUrl(svgUrl)
    const scale = 300 / 96 // Approximate 300 DPI raster output from CSS px units.
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('Canvas rendering context unavailable')
    }

    ctx.fillStyle = '#080b12'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

    const pngBlob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/png')
    })
    if (!pngBlob) {
      throw new Error('Failed to encode PNG export')
    }
    downloadBinaryBlob(pngBlob, filename)
  } finally {
    URL.revokeObjectURL(svgUrl)
  }
}

const METRIC_CARDS: { key: keyof EvaluationMetrics; label: string; description: string }[] = [
  { key: 'sensitivity', label: 'Sensitivity', description: 'True positive rate (recall)' },
  { key: 'specificity', label: 'Specificity', description: 'True negative rate' },
  { key: 'f1', label: 'F1 Score', description: 'Harmonic mean of precision and recall' },
  { key: 'wss_at_95', label: 'WSS@95', description: 'Work saved over sampling at 95% recall' },
  { key: 'auroc', label: 'AUROC', description: 'Area under the ROC curve' },
  { key: 'ece', label: 'ECE', description: 'Expected calibration error' },
]

function formatMetric(value: number | null): string {
  if (value === null || value === undefined) return '\u2014'
  return value.toFixed(2)
}

function formatLancet(label: string, value: number | null): string {
  if (value === null || value === undefined) return `${label} \u2014`
  const formatted = value.toFixed(2).replace('.', '\u00B7')
  return `${label} ${formatted}`
}

export function Evaluation() {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [goldLabelCount, setGoldLabelCount] = useState(0)
  const [totalRecords, setTotalRecords] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ChartTab>('roc')
  const [copied, setCopied] = useState(false)
  const [selectedScreeningSessionId, setSelectedScreeningSessionId] = useState('')
  const chartContainerRef = useRef<HTMLDivElement | null>(null)

  const { data: screeningSessions = [] } = useScreeningSessions()
  const { data: evalData } = useEvaluationResults(sessionId)

  const metrics = evalData?.metrics ?? null
  const rocData = evalData?.charts?.roc ?? []
  const calibrationData = evalData?.charts?.calibration ?? []
  const distributionData = evalData?.charts?.distribution ?? []
  const hasEvaluationResults = (evalData?.total_records ?? 0) > 0
  const hasChartData =
    rocData.length > 0 || calibrationData.length > 0 || distributionData.length > 0
  const runnableScreeningSessions = screeningSessions.filter(
    (session) => session.completed_records > 0,
  )

  const handleUpload = useCallback(async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await apiUpload<EvaluationUploadResponse>(
        '/evaluation/upload-labels',
        formData,
      )
      const resolvedGoldCount = resp.gold_label_count ?? resp.label_count ?? 0
      const resolvedTotalRecords = resp.total_records ?? resp.label_count ?? 0
      setSessionId(resp.session_id)
      setGoldLabelCount(resolvedGoldCount)
      setTotalRecords(resolvedTotalRecords)
      setUploadedFilename(resp.filename ?? file.name)
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
      const file = e.dataTransfer.files[0]
      if (file) void handleUpload(file)
    },
    [handleUpload],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void handleUpload(file)
  }

  const handleRun = async () => {
    if (!sessionId) return
    setRunning(true)
    setError(null)
    try {
      const body = selectedScreeningSessionId
        ? { screening_session_id: selectedScreeningSessionId }
        : undefined
      await apiPost(`/evaluation/run/${sessionId}`, body)
      void queryClient.invalidateQueries({ queryKey: ['evaluation-results'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Evaluation failed')
    } finally {
      setRunning(false)
    }
  }

  const handleExportCSV = () => {
    if (!metrics) return
    const header = 'Metric,Value'
    const rows = METRIC_CARDS.map(
      (card) => `${card.label},${formatMetric(metrics[card.key])}`,
    )
    const csv = [header, ...rows].join('\n')
    downloadBlob(csv, 'evaluation_metrics.csv', 'text/csv')
  }

  const handleExportPNG = async () => {
    const container = chartContainerRef.current
    if (!container || !hasChartData) return
    setError(null)
    try {
      await exportChartAsPng(container, chartFilename(activeTab, 'png'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PNG export failed')
    }
  }

  const handleExportSVG = async () => {
    const container = chartContainerRef.current
    if (!container || !hasChartData) return
    setError(null)
    try {
      await exportChartAsSvg(container, chartFilename(activeTab, 'svg'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SVG export failed')
    }
  }

  const lancetText = metrics
    ? [
        formatLancet('Sensitivity', metrics.sensitivity),
        formatLancet('Specificity', metrics.specificity),
        formatLancet('F1', metrics.f1),
        formatLancet('WSS@95', metrics.wss_at_95),
        formatLancet('AUROC', metrics.auroc),
        formatLancet('ECE', metrics.ece),
        formatLancet('Brier', metrics.brier),
        formatLancet('Kappa', metrics.kappa),
      ].join('\n')
    : ''

  const handleCopy = () => {
    void navigator.clipboard.writeText(lancetText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <Header
        title="Evaluation"
        description="Performance metrics, calibration, and threshold optimization"
      />

      <div className="space-y-6">
        {/* Section 1: Upload Gold Standard */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Upload size={20} className="text-green-400" />
            <h3 className="text-lg font-semibold text-white">
              Upload Gold Standard Labels
            </h3>
          </div>

          {uploadedFilename ? (
            <>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileUp size={20} className="text-green-400" />
                  <div>
                    <p className="text-white font-medium">{uploadedFilename}</p>
                    <p className="text-white/50 text-sm">
                      {goldLabelCount} gold labels across {totalRecords} records
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
                        Running...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> Run Evaluation
                      </>
                    )}
                  </span>
                </GlassButton>
              </div>
              <div className="mt-4 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-3 items-end">
                <div>
                  <label className="block text-white/60 text-xs uppercase tracking-wider mb-2">
                    Screening Session Source
                  </label>
                  <select
                    value={selectedScreeningSessionId}
                    onChange={(e) => setSelectedScreeningSessionId(e.target.value)}
                    className="glass-input w-full text-sm"
                  >
                    <option value="">Automatic (best `record_id` overlap)</option>
                    {runnableScreeningSessions.map((session) => (
                      <option key={session.session_id} value={session.session_id}>
                        {session.filename} | {session.completed_records}/{session.total_records} screened
                      </option>
                    ))}
                  </select>
                  <p className="text-white/40 text-xs mt-2">
                    {runnableScreeningSessions.length > 0
                      ? 'Select a screening run explicitly to avoid ambiguity when multiple runs exist.'
                      : 'No completed screening sessions found yet. Run Screening first, or use automatic and evaluate later.'}
                  </p>
                </div>
                {evalData?.screening_session_id && (
                  <div className="text-white/50 text-xs">
                    Using session: <span className="font-mono">{evalData.screening_session_id}</span>
                  </div>
                )}
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
                Drag & drop your gold standard file
              </p>
              <p className="text-white/40 text-sm mb-4">
                Supports RIS, BibTeX, CSV, Excel, XML (labels are read from CSV/Excel label columns)
              </p>
              <label>
                <input
                  type="file"
                  accept=".ris,.bib,.csv,.xlsx,.xml"
                  onChange={handleInputChange}
                  className="hidden"
                />
                <GlassButton variant="outline" disabled={uploading}>
                  {uploading ? 'Uploading...' : 'Browse Files'}
                </GlassButton>
              </label>
            </div>
          )}

          {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
        </GlassCard>

        {evalData && !hasEvaluationResults && (
          <GlassCard variant="subtle">
            <p className="text-white/70 text-sm">
              No matched screening results were found for these labels (matching is based on
              `record_id`), or the uploaded file did not contain parseable gold-label columns.
            </p>
          </GlassCard>
        )}

        {/* Section 2: Metrics Summary Cards */}
        {metrics && hasEvaluationResults && (
          <div>
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <BarChart3 size={20} className="text-purple-400" />
              Performance Metrics
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {METRIC_CARDS.map((card) => (
                <GlassCard key={card.key} variant="subtle">
                  <p className="text-white/50 text-xs uppercase tracking-wider">
                    {card.label}
                  </p>
                  <p className="text-3xl font-bold text-white mt-1">
                    {formatMetric(metrics[card.key])}
                  </p>
                  <p className="text-white/40 text-xs mt-1">
                    {card.description}
                  </p>
                </GlassCard>
              ))}
            </div>
          </div>
        )}

        {/* Section 3: Interactive Charts */}
        {metrics && hasEvaluationResults && (
          <GlassCard>
            <div className="flex items-center gap-4 mb-6">
              <button
                onClick={() => setActiveTab('roc')}
                className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
                  activeTab === 'roc'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'text-white/50 hover:text-white/70'
                }`}
              >
                ROC Curve
              </button>
              <button
                onClick={() => setActiveTab('calibration')}
                className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
                  activeTab === 'calibration'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'text-white/50 hover:text-white/70'
                }`}
              >
                Calibration Plot
              </button>
              <button
                onClick={() => setActiveTab('distribution')}
                className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
                  activeTab === 'distribution'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'text-white/50 hover:text-white/70'
                }`}
              >
                Score Distribution
              </button>
            </div>

            <div ref={chartContainerRef} className="h-80">
              {!hasChartData && (
                <div className="h-full flex items-center justify-center text-white/50 text-sm">
                  Chart data unavailable for this run.
                </div>
              )}

              {activeTab === 'roc' && hasChartData && (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={rocData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis
                      dataKey="fpr"
                      label={{ value: 'False Positive Rate', position: 'bottom', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <YAxis
                      dataKey="tpr"
                      label={{ value: 'True Positive Rate', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <Tooltip
                      contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                    />
                    <ReferenceLine
                      segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                      stroke="rgba(255,255,255,0.2)"
                      strokeDasharray="5 5"
                    />
                    <Area
                      type="monotone"
                      dataKey="tpr"
                      stroke="#8B5CF6"
                      fill="rgba(139,92,246,0.15)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}

              {activeTab === 'calibration' && hasChartData && (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={calibrationData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis
                      dataKey="predicted"
                      label={{ value: 'Predicted Probability', position: 'bottom', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <YAxis
                      label={{ value: 'Actual Probability', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <Tooltip
                      contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                    />
                    <ReferenceLine
                      segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                      stroke="rgba(255,255,255,0.2)"
                      strokeDasharray="5 5"
                    />
                    <Line
                      type="monotone"
                      dataKey="actual"
                      stroke="#06B6D4"
                      strokeWidth={2}
                      dot={{ fill: '#06B6D4', r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}

              {activeTab === 'distribution' && hasChartData && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={distributionData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis
                      dataKey="bin"
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <YAxis
                      label={{ value: 'Count', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
                      tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                      stroke="rgba(255,255,255,0.2)"
                    />
                    <Tooltip
                      contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                    />
                    <Bar dataKey="include" fill="#8B5CF6" radius={[4, 4, 0, 0]} name="Include" />
                    <Bar dataKey="exclude" fill="#06B6D4" radius={[4, 4, 0, 0]} name="Exclude" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </GlassCard>
        )}

        {/* Section 4: Lancet-Formatted Text */}
        {metrics && hasEvaluationResults && (
          <GlassCard>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-white">
                Lancet Digital Health Format
              </h3>
              <GlassButton variant="outline" size="sm" onClick={handleCopy}>
                <span className="flex items-center gap-2">
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? 'Copied' : 'Copy to Clipboard'}
                </span>
              </GlassButton>
            </div>
            <textarea
              readOnly
              value={lancetText}
              rows={8}
              className="glass-input w-full font-mono text-sm text-white/80 resize-none"
            />
            <p className="text-white/40 text-xs mt-2">
              Uses middle dot (\u00B7) for decimal separators per Lancet style
            </p>
          </GlassCard>
        )}

        {/* Section 5: Export */}
        {metrics && hasEvaluationResults && (
          <GlassCard variant="subtle">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-white font-medium">Export Charts</h3>
                <p className="text-white/40 text-sm mt-0.5">
                  Export charts for publication (\u2265300 DPI)
                </p>
              </div>
              <div className="flex gap-2">
                <GlassButton
                  variant="outline"
                  size="sm"
                  onClick={() => { void handleExportPNG() }}
                  disabled={!hasChartData}
                >
                  <span className="flex items-center gap-2">
                    <ImageIcon size={14} /> Export PNG (300 DPI)
                  </span>
                </GlassButton>
                <GlassButton
                  variant="outline"
                  size="sm"
                  onClick={() => { void handleExportSVG() }}
                  disabled={!hasChartData}
                >
                  <span className="flex items-center gap-2">
                    <FileCode size={14} /> Export SVG
                  </span>
                </GlassButton>
                <GlassButton variant="outline" size="sm" onClick={handleExportCSV}>
                  <span className="flex items-center gap-2">
                    <Download size={14} /> Export CSV
                  </span>
                </GlassButton>
              </div>
            </div>
          </GlassCard>
        )}
      </div>
    </>
  )
}
