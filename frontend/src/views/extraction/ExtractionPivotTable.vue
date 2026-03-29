<template>
  <div>
    <!-- Controls bar -->
    <div class="pivot-controls">
      <div class="view-toggle">
        <button
          :class="['btn', 'btn-sm', viewMode === 'pivot' ? 'btn-primary' : 'btn-secondary']"
          @click="viewMode = 'pivot'"
        >
          <i class="fas fa-th"></i> Pivot
        </button>
        <button
          :class="['btn', 'btn-sm', viewMode === 'flat' ? 'btn-primary' : 'btn-secondary']"
          @click="viewMode = 'flat'"
        >
          <i class="fas fa-list"></i> Flat
        </button>
      </div>
      <div class="filter-group">
        <label class="filter-label">Filter:</label>
        <select v-model="confidenceFilter" class="filter-select">
          <option value="">All confidence</option>
          <option value="VERIFIED">Verified only</option>
          <option value="HIGH">High only</option>
          <option value="MEDIUM">Medium only</option>
          <option value="LOW">Low only</option>
          <option value="FAILED">Failed only</option>
          <option value="LOW_FAILED">Low + Failed</option>
        </select>
      </div>
    </div>

    <!-- Pivot View -->
    <div v-if="viewMode === 'pivot'" class="pivot-scroll">
      <table class="pivot-table">
        <thead>
          <tr>
            <th class="sticky-col">PDF</th>
            <th v-for="field in pivotData.fieldNames" :key="field">{{ field }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pdfId in pivotData.pdfIds" :key="pdfId">
            <td class="sticky-col pdf-name-cell" :title="pdfId">{{ pdfId.slice(0, 10) }}</td>
            <td
              v-for="field in pivotData.fieldNames"
              :key="`${pdfId}::${field}`"
              :class="[
                'pivot-cell',
                { 'pivot-selected': selectedKey === `${pdfId}::${field}` },
              ]"
              :style="cellBg(pivotData.cellMap.get(`${pdfId}::${field}`))"
              @click="onCellClick(pivotData.cellMap.get(`${pdfId}::${field}`))"
            >
              <span v-if="pivotData.cellMap.has(`${pdfId}::${field}`)">
                {{ displayValue(pivotData.cellMap.get(`${pdfId}::${field}`)!.value) }}
              </span>
              <span v-else class="text-muted">--</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Flat View (original table) -->
    <div v-else style="overflow-x: auto;">
      <table class="results-table">
        <thead>
          <tr>
            <th>PDF</th>
            <th>Field</th>
            <th>Value</th>
            <th>Confidence</th>
            <th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(cell, i) in filteredResults"
            :key="i"
            @click="onCellClick(cell)"
            :class="{ 'selected-row': selectedKey === `${cell.pdf_id}::${cell.field_name}` }"
            style="cursor: pointer;"
          >
            <td class="text-muted" style="font-size: 0.8rem;">{{ cell.pdf_id?.slice(0, 8) }}</td>
            <td><strong>{{ cell.field_name }}</strong></td>
            <td>
              <span v-if="editingCell === cell">
                <input
                  v-model="editValue"
                  @keyup.enter="$emit('save-edit', cell, editValue)"
                  @keyup.escape="editingCell = null"
                  class="edit-input"
                  @click.stop
                />
              </span>
              <span v-else @dblclick.stop="startEdit(cell)">{{ cell.value }}</span>
            </td>
            <td>
              <span :class="['confidence-badge', `confidence-${cell.confidence?.toLowerCase()}`]">
                {{ cell.confidence }}
              </span>
            </td>
            <td class="text-muted" style="font-size: 0.8rem;">{{ cell.strategy }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

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
  selectedCell: ResultCell | null
}>()

const emit = defineEmits<{
  (e: 'select-cell', cell: ResultCell): void
  (e: 'save-edit', cell: ResultCell, newValue: string): void
}>()

const viewMode = ref<'pivot' | 'flat'>('pivot')
const confidenceFilter = ref('')
const editingCell = ref<ResultCell | null>(null)
const editValue = ref('')

const selectedKey = computed(() => {
  if (!props.selectedCell) return ''
  return `${props.selectedCell.pdf_id}::${props.selectedCell.field_name}`
})

const filteredResults = computed(() => {
  if (!confidenceFilter.value) return props.results
  if (confidenceFilter.value === 'LOW_FAILED') {
    return props.results.filter((r) =>
      ['LOW', 'FAILED'].includes(r.confidence?.toUpperCase())
    )
  }
  return props.results.filter(
    (r) => r.confidence?.toUpperCase() === confidenceFilter.value
  )
})

const pivotData = computed(() => {
  const source = filteredResults.value
  const fieldNames = [...new Set(source.map((r) => r.field_name))]
  const pdfIds = [...new Set(source.map((r) => r.pdf_id))]
  const cellMap = new Map<string, ResultCell>()
  for (const r of source) {
    cellMap.set(`${r.pdf_id}::${r.field_name}`, r)
  }
  return { fieldNames, pdfIds, cellMap }
})

const confidenceColors: Record<string, string> = {
  verified: 'rgba(21, 128, 61, 0.2)',
  high: 'rgba(34, 197, 94, 0.2)',
  medium: 'rgba(234, 179, 8, 0.2)',
  low: 'rgba(249, 115, 22, 0.2)',
  single: 'rgba(163, 163, 163, 0.2)',
  failed: 'rgba(239, 68, 68, 0.2)',
}

function cellBg(cell?: ResultCell): Record<string, string> {
  if (!cell) return {}
  const key = cell.confidence?.toLowerCase() || ''
  const bg = confidenceColors[key]
  return bg ? { background: bg } : {}
}

function displayValue(val: unknown): string {
  if (val === null || val === undefined) return '--'
  const s = String(val)
  return s.length > 40 ? s.slice(0, 37) + '...' : s
}

function onCellClick(cell?: ResultCell) {
  if (cell) emit('select-cell', cell)
}

function startEdit(cell: ResultCell) {
  editingCell.value = cell
  editValue.value = String(cell.value ?? '')
}
</script>

<style scoped>
.pivot-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.view-toggle {
  display: flex;
  gap: 0.25rem;
}

.btn-sm {
  padding: 0.25rem 0.6rem;
  font-size: 0.78rem;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.filter-label {
  font-size: 0.8rem;
  color: #6b7280;
}

.filter-select {
  padding: 0.2rem 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  background: white;
  color: #374151;
}

/* Pivot table */
.pivot-scroll {
  overflow-x: auto;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
}

.pivot-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.pivot-table th,
.pivot-table td {
  padding: 0.4rem 0.6rem;
  border: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pivot-table th {
  background: #f9fafb;
  font-weight: 600;
  font-size: 0.75rem;
  position: sticky;
  top: 0;
  z-index: 1;
}

.sticky-col {
  position: sticky;
  left: 0;
  z-index: 2;
  background: #f9fafb;
  min-width: 90px;
}

.pivot-table thead .sticky-col {
  z-index: 3;
}

.pdf-name-cell {
  font-family: monospace;
  font-size: 0.75rem;
  color: #374151;
}

.pivot-cell {
  cursor: pointer;
  transition: box-shadow 0.15s;
}

.pivot-cell:hover {
  box-shadow: inset 0 0 0 1px #93c5fd;
}

.pivot-selected {
  box-shadow: inset 0 0 0 2px #1d4ed8 !important;
}

/* Flat table (re-use existing styles) */
.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.results-table th,
.results-table td {
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
}

.results-table th {
  background: #f9fafb;
  font-weight: 600;
  white-space: nowrap;
}

.results-table tr:hover td {
  background: #f9fafb;
}

.selected-row td {
  background: #eff6ff !important;
}

.confidence-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.confidence-verified { background: #15803d; color: white; }
.confidence-high { background: #22c55e; color: white; }
.confidence-medium { background: #eab308; color: white; }
.confidence-low { background: #f97316; color: white; }
.confidence-single { background: #a3a3a3; color: white; }
.confidence-failed { background: #ef4444; color: white; }

.edit-input {
  width: 100%;
  padding: 0.25rem 0.375rem;
  border: 1px solid #1d4ed8;
  border-radius: 0.25rem;
  font-size: 0.875rem;
  outline: none;
}
</style>
