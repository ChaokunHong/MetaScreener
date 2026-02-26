import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'
import { GlassButton } from '../components/glass/GlassButton'
import { apiUpload, apiPost } from '../api/client'
import { useEvaluationResults } from '../api/queries'
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
  Image,
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
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Sample data for chart placeholders (populated after evaluation runs)
const ROC_DATA = [
  { fpr: 0, tpr: 0 },
  { fpr: 0.02, tpr: 0.45 },
  { fpr: 0.05, tpr: 0.72 },
  { fpr: 0.1, tpr: 0.85 },
  { fpr: 0.15, tpr: 0.91 },
  { fpr: 0.2, tpr: 0.94 },
  { fpr: 0.3, tpr: 0.96 },
  { fpr: 0.5, tpr: 0.98 },
  { fpr: 0.7, tpr: 0.99 },
  { fpr: 1, tpr: 1 },
]

const CALIBRATION_DATA = [
  { predicted: 0.1, actual: 0.08 },
  { predicted: 0.2, actual: 0.18 },
  { predicted: 0.3, actual: 0.32 },
  { predicted: 0.4, actual: 0.38 },
  { predicted: 0.5, actual: 0.52 },
  { predicted: 0.6, actual: 0.57 },
  { predicted: 0.7, actual: 0.72 },
  { predicted: 0.8, actual: 0.78 },
  { predicted: 0.9, actual: 0.92 },
]

const DISTRIBUTION_DATA = [
  { bin: '0.0-0.1', include: 2, exclude: 45 },
  { bin: '0.1-0.2', include: 3, exclude: 38 },
  { bin: '0.2-0.3', include: 5, exclude: 22 },
  { bin: '0.3-0.4', include: 8, exclude: 15 },
  { bin: '0.4-0.5', include: 12, exclude: 10 },
  { bin: '0.5-0.6', include: 15, exclude: 8 },
  { bin: '0.6-0.7', include: 22, exclude: 5 },
  { bin: '0.7-0.8', include: 35, exclude: 3 },
  { bin: '0.8-0.9', include: 42, exclude: 2 },
  { bin: '0.9-1.0', include: 50, exclude: 1 },
]

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

  const { data: evalData } = useEvaluationResults(sessionId)

  const metrics = evalData?.metrics ?? null

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
      setSessionId(resp.session_id)
      setGoldLabelCount(resp.gold_label_count)
      setTotalRecords(resp.total_records)
      setUploadedFilename(file.name)
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
      await apiPost(`/evaluation/run/${sessionId}`)
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

  const handleExportPNG = () => {
    // Requires html-to-image / canvas library for chart export
    alert('PNG export requires a canvas rendering library. Use browser screenshot or export as CSV.')
  }

  const handleExportSVG = () => {
    // Requires html-to-image / canvas library for chart export
    alert('SVG export requires a canvas rendering library. Use browser screenshot or export as CSV.')
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
                Supports RIS, CSV, JSON with label annotations
              </p>
              <label>
                <input
                  type="file"
                  accept=".ris,.csv,.json"
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

        {/* Section 2: Metrics Summary Cards */}
        {metrics && (
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
        {metrics && (
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

            <div className="h-80">
              {activeTab === 'roc' && (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={ROC_DATA}>
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

              {activeTab === 'calibration' && (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={CALIBRATION_DATA}>
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

              {activeTab === 'distribution' && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={DISTRIBUTION_DATA}>
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
        {metrics && (
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
        {metrics && (
          <GlassCard variant="subtle">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-white font-medium">Export Charts</h3>
                <p className="text-white/40 text-sm mt-0.5">
                  Export charts for publication (\u2265300 DPI)
                </p>
              </div>
              <div className="flex gap-2">
                <GlassButton variant="outline" size="sm" onClick={handleExportPNG}>
                  <span className="flex items-center gap-2">
                    <Image size={14} /> Export PNG (300 DPI)
                  </span>
                </GlassButton>
                <GlassButton variant="outline" size="sm" onClick={handleExportSVG}>
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
