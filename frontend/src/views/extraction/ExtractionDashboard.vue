<template>
  <div v-if="results.length > 0" class="glass-card fade-in" style="margin-top: 1rem;">
    <div class="section-title"><i class="fas fa-chart-pie"></i> Extraction Summary</div>

    <!-- Summary stats row -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ totalFields }}</div>
        <div class="stat-label">Total Fields</div>
      </div>
      <div class="stat-card stat-verified">
        <div class="stat-value">{{ countByConfidence('VERIFIED') }}</div>
        <div class="stat-label">Verified</div>
      </div>
      <div class="stat-card stat-high">
        <div class="stat-value">{{ countByConfidence('HIGH') }}</div>
        <div class="stat-label">High</div>
      </div>
      <div class="stat-card stat-medium">
        <div class="stat-value">{{ countByConfidence('MEDIUM') }}</div>
        <div class="stat-label">Medium</div>
      </div>
      <div class="stat-card stat-low">
        <div class="stat-value">{{ countByConfidence('LOW') }}</div>
        <div class="stat-label">Low</div>
      </div>
      <div class="stat-card stat-failed">
        <div class="stat-value">{{ countByConfidence('FAILED') }}</div>
        <div class="stat-label">Failed</div>
      </div>
    </div>

    <!-- Confidence distribution bar -->
    <div class="confidence-bar">
      <div
        v-for="level in confidenceLevels"
        :key="level.name"
        :class="['conf-segment', `bg-${level.name.toLowerCase()}`]"
        :style="{ width: level.pct + '%' }"
        :title="`${level.name}: ${level.count} (${level.pct.toFixed(1)}%)`"
      ></div>
    </div>

    <!-- Per-PDF health -->
    <div class="section-title" style="margin-top: 1rem; font-size: 0.9rem;">
      <i class="fas fa-file-pdf"></i> Per-PDF Quality
    </div>
    <div class="pdf-health-list">
      <div v-for="pdf in pdfHealthScores" :key="pdf.pdf_id" class="pdf-health-item">
        <span class="pdf-health-name">{{ pdf.filename }}</span>
        <div class="pdf-health-bar">
          <div
            class="pdf-health-fill"
            :style="{ width: pdf.healthPct + '%', background: pdf.healthColor }"
          ></div>
        </div>
        <span class="pdf-health-score">{{ pdf.healthPct }}%</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface ResultCell {
  pdf_id: string
  field_name: string
  value: unknown
  confidence: string
  strategy: string
  evidence_json?: string
}

const props = defineProps<{
  results: ResultCell[]
}>()

const totalFields = computed(() => props.results.length)

function countByConfidence(level: string): number {
  return props.results.filter((r) => r.confidence?.toUpperCase() === level).length
}

const confidenceLevels = computed(() => {
  const levels = ['VERIFIED', 'HIGH', 'MEDIUM', 'LOW', 'SINGLE', 'FAILED']
  const total = props.results.length || 1
  return levels.map((name) => ({
    name,
    count: countByConfidence(name),
    pct: (countByConfidence(name) / total) * 100,
  }))
})

const pdfHealthScores = computed(() => {
  const byPdf = new Map<string, { filename: string; cells: ResultCell[] }>()
  for (const r of props.results) {
    if (!byPdf.has(r.pdf_id)) {
      byPdf.set(r.pdf_id, { filename: r.pdf_id.slice(0, 8), cells: [] })
    }
    byPdf.get(r.pdf_id)!.cells.push(r)
  }
  return [...byPdf.entries()].map(([pdf_id, { filename, cells }]) => {
    const good = cells.filter((c) =>
      ['VERIFIED', 'HIGH'].includes(c.confidence?.toUpperCase())
    ).length
    const pct = Math.round((good / (cells.length || 1)) * 100)
    return {
      pdf_id,
      filename,
      healthPct: pct,
      healthColor: pct >= 80 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444',
    }
  })
})
</script>

<style scoped>
.fade-in {
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.stats-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.stat-card {
  flex: 1 1 0;
  min-width: 80px;
  text-align: center;
  padding: 0.5rem 0.4rem;
  border-radius: 0.5rem;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.15rem;
}

.stat-verified .stat-value { color: #15803d; }
.stat-verified { border-color: #bbf7d0; background: #f0fdf4; }
.stat-high .stat-value { color: #22c55e; }
.stat-high { border-color: #bbf7d0; background: #f0fdf4; }
.stat-medium .stat-value { color: #eab308; }
.stat-medium { border-color: #fef08a; background: #fefce8; }
.stat-low .stat-value { color: #f97316; }
.stat-low { border-color: #fed7aa; background: #fff7ed; }
.stat-failed .stat-value { color: #ef4444; }
.stat-failed { border-color: #fecaca; background: #fef2f2; }

/* Confidence distribution bar */
.confidence-bar {
  display: flex;
  height: 0.5rem;
  border-radius: 0.25rem;
  overflow: hidden;
  background: #e5e7eb;
}

.conf-segment {
  transition: width 0.3s ease;
  min-width: 0;
}

.bg-verified { background: #15803d; }
.bg-high { background: #22c55e; }
.bg-medium { background: #eab308; }
.bg-low { background: #f97316; }
.bg-single { background: #a3a3a3; }
.bg-failed { background: #ef4444; }

/* Per-PDF health */
.pdf-health-list {
  max-height: 200px;
  overflow-y: auto;
}

.pdf-health-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  font-size: 0.8rem;
}

.pdf-health-name {
  width: 80px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #374151;
  font-family: monospace;
  font-size: 0.75rem;
}

.pdf-health-bar {
  flex: 1;
  height: 0.4rem;
  background: #e5e7eb;
  border-radius: 0.2rem;
  overflow: hidden;
}

.pdf-health-fill {
  height: 100%;
  border-radius: 0.2rem;
  transition: width 0.3s ease;
}

.pdf-health-score {
  width: 36px;
  text-align: right;
  font-size: 0.75rem;
  font-weight: 600;
  color: #374151;
}
</style>
