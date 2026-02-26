import { useState, useCallback } from 'react'
import { Upload, FileUp, X } from 'lucide-react'
import { GlassCard } from '../glass/GlassCard'
import { GlassButton } from '../glass/GlassButton'
import { apiUpload } from '../../api/client'
import type { UploadResponse } from '../../api/types'
import { useScreeningStore } from '../../stores/screening'

interface FileUploadProps {
  onComplete: () => void
}

export function FileUpload({ onComplete }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setSession, filename, recordCount } = useScreeningStore()

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      try {
        const formData = new FormData()
        formData.append('file', file)
        const resp = await apiUpload<UploadResponse>('/screening/upload', formData)
        setSession(resp.session_id, resp.record_count, resp.filename)
        onComplete()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [onComplete, setSession],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) void handleFile(file)
    },
    [handleFile],
  )

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => setIsDragging(false)

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void handleFile(file)
  }

  if (filename) {
    return (
      <GlassCard>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileUp size={20} className="text-green-400" />
            <div>
              <p className="text-white font-medium">{filename}</p>
              <p className="text-white/50 text-sm">{recordCount} records loaded</p>
            </div>
          </div>
          <GlassButton variant="ghost" size="sm" onClick={() => useScreeningStore.getState().reset()}>
            <X size={16} />
          </GlassButton>
        </div>
      </GlassCard>
    )
  }

  return (
    <GlassCard>
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
          isDragging ? 'border-purple-400 bg-purple-500/10' : 'border-white/20 hover:border-white/30'
        }`}
      >
        <Upload size={40} className="mx-auto text-white/30 mb-4" />
        <p className="text-white/70 mb-2">Drag & drop your search results file</p>
        <p className="text-white/40 text-sm mb-4">Supports RIS, BibTeX, CSV, Excel</p>
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
      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
    </GlassCard>
  )
}
