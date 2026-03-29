<template>
  <div class="pivot-wrapper" @keydown="handleKeydown" tabindex="0" ref="tableWrapper">
    <!-- Bulk toolbar -->
    <div class="bulk-toolbar" v-if="bulk.selectedCells.value.size > 0">
      <span class="text-muted">{{ bulk.selectedCells.value.size }} cell(s) selected</span>
      <button @click="bulk.bulkAccept()" class="btn btn-sm btn-success"><i class="fas fa-check-double"></i> Accept Selected</button>
      <button @click="bulk.bulkFlag()" class="btn btn-sm btn-warning"><i class="fas fa-flag"></i> Flag for Review</button>
      <button @click="bulk.clearSelection()" class="btn btn-sm btn-secondary"><i class="fas fa-times"></i> Clear</button>
    </div>

    <!-- Sheet tabs -->
    <div class="sheet-tabs" v-if="sheetNames.length > 1">
      <button v-for="sheet in sheetNames" :key="sheet"
              :class="['sheet-tab', { active: activeSheet === sheet }]"
              @click="activeSheet = sheet">
        {{ sheet }}
        <span class="sheet-count">({{ sheetFieldCount(sheet) }})</span>
      </button>
    </div>

    <!-- Controls bar -->
    <div class="pivot-controls">
      <div class="view-toggle">
        <button :class="['btn', 'btn-sm', viewMode === 'pivot' ? 'btn-primary' : 'btn-secondary']" @click="viewMode = 'pivot'"><i class="fas fa-th"></i> Pivot</button>
        <button :class="['btn', 'btn-sm', viewMode === 'flat' ? 'btn-primary' : 'btn-secondary']" @click="viewMode = 'flat'"><i class="fas fa-list"></i> Flat</button>
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
      <div class="filter-group text-muted" style="font-size: 0.75rem; margin-left: auto;">
        <i class="fas fa-keyboard"></i> Arrow / Enter / Space / Esc
      </div>
    </div>

    <!-- Pivot View -->
    <div v-if="viewMode === 'pivot'" class="pivot-scroll">
      <table class="pivot-table">
        <thead>
          <tr>
            <th class="checkbox-col"><input type="checkbox" @change="bulk.toggleSelectAll(pivotData.pdfIds, pivotData.fieldNames, allSelected)" :checked="allSelected" title="Select all" /></th>
            <th class="sticky-col">PDF</th>
            <th v-for="field in pivotData.fieldNames" :key="field">{{ field }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(pdfId, rowIdx) in pivotData.pdfIds" :key="pdfId">
            <td class="checkbox-col"><input type="checkbox" :checked="bulk.isRowSelected(pdfId, pivotData.fieldNames)" @change="bulk.toggleRow(pdfId, pivotData.fieldNames)" @click.stop /></td>
            <td class="sticky-col pdf-name-cell" :title="pdfId">{{ pdfId.slice(0, 10) }}</td>
            <td v-for="(field, colIdx) in pivotData.fieldNames" :key="`${pdfId}::${field}`"
              :class="cellClass(pdfId, field, rowIdx, colIdx)"
              :style="cellBg(pivotData.cellMap.get(`${pdfId}::${field}`))"
              @click="onCellClick(pivotData.cellMap.get(`${pdfId}::${field}`), rowIdx, colIdx)">
              <span v-if="pivotData.cellMap.has(`${pdfId}::${field}`)" class="cell-content">
                {{ displayValue(pivotData.cellMap.get(`${pdfId}::${field}`)!.value) }}
                <i v-if="bulk.reviewedCells.value.has(`${pdfId}::${field}`)" class="fas fa-check cell-reviewed" title="Accepted"></i>
                <i v-if="bulk.flaggedCells.value.has(`${pdfId}::${field}`)" class="fas fa-flag cell-flagged" title="Flagged"></i>
              </span>
              <span v-else class="text-muted">--</span>
              <span v-if="pivotData.cellMap.has(`${pdfId}::${field}`)"
                :class="['conf-dot', `dot-${pivotData.cellMap.get(`${pdfId}::${field}`)!.confidence?.toLowerCase()}`]"
                :title="confTooltip(pivotData.cellMap.get(`${pdfId}::${field}`)!.confidence)"></span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Flat View -->
    <div v-else style="overflow-x: auto;">
      <table class="results-table">
        <thead>
          <tr>
            <th class="checkbox-col"><input type="checkbox" @change="bulk.toggleSelectAllFlat(filteredResults, allFlatSelected)" :checked="allFlatSelected" title="Select all" /></th>
            <th>PDF</th><th>Field</th><th>Value</th><th>Confidence</th><th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(cell, i) in filteredResults" :key="i" @click="onCellClick(cell, i, 0)"
            :class="{ 'selected-row': selectedKey === `${cell.pdf_id}::${cell.field_name}` }" style="cursor: pointer;">
            <td class="checkbox-col" @click.stop><input type="checkbox" :checked="bulk.selectedCells.value.has(`${cell.pdf_id}::${cell.field_name}`)" @change="bulk.toggleCell(`${cell.pdf_id}::${cell.field_name}`)" /></td>
            <td class="text-muted" style="font-size: 0.8rem;">{{ cell.pdf_id?.slice(0, 8) }}</td>
            <td>
              <strong>{{ cell.field_name }}</strong>
              <i v-if="bulk.reviewedCells.value.has(`${cell.pdf_id}::${cell.field_name}`)" class="fas fa-check cell-reviewed" title="Accepted"></i>
              <i v-if="bulk.flaggedCells.value.has(`${cell.pdf_id}::${cell.field_name}`)" class="fas fa-flag cell-flagged" title="Flagged"></i>
            </td>
            <td>
              <span v-if="editingCell === cell"><input v-model="editValue" @keyup.enter="$emit('save-edit', cell, editValue)" @keyup.escape="editingCell = null" class="edit-input" @click.stop /></span>
              <span v-else @dblclick.stop="startEdit(cell)">{{ cell.value }}</span>
            </td>
            <td><span :class="['confidence-badge', `confidence-${cell.confidence?.toLowerCase()}`]" :title="confTooltip(cell.confidence)">{{ cell.confidence }}</span></td>
            <td class="text-muted" style="font-size: 0.8rem;">{{ cell.strategy }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useBulkOperations, confidenceTooltip as confTooltip, confidenceColors } from '../../composables/useBulkOperations'

export interface ResultCell {
  pdf_id: string
  sheet_name: string
  field_name: string
  value: unknown
  confidence: string
  strategy: string
  evidence_json?: string
}

const props = defineProps<{
  results: ResultCell[]
  selectedCell: ResultCell | null
  sheetOrder?: string[]
}>()
const emit = defineEmits<{ (e: 'select-cell', cell: ResultCell): void; (e: 'save-edit', cell: ResultCell, newValue: string): void }>()

const tableWrapper = ref<HTMLElement | null>(null)
const viewMode = ref<'pivot' | 'flat'>('pivot')
const confidenceFilter = ref('')
const editingCell = ref<ResultCell | null>(null)
const editValue = ref('')
const focusRow = ref(0)
const focusCol = ref(0)
const activeSheet = ref('')

const bulk = useBulkOperations()

const selectedKey = computed(() => props.selectedCell ? `${props.selectedCell.pdf_id}::${props.selectedCell.field_name}` : '')

const sheetNames = computed(() => {
  const presentNames = new Set(props.results.map((r) => r.sheet_name || 'Studies'))
  if (props.sheetOrder && props.sheetOrder.length > 0) {
    // Ordered by schema extraction_order; append any unknown sheets at the end
    const ordered = props.sheetOrder.filter((s) => presentNames.has(s))
    const extras = [...presentNames].filter((s) => !props.sheetOrder!.includes(s))
    return [...ordered, ...extras]
  }
  return [...presentNames]
})

// Initialize activeSheet when results arrive; reset only when sheet list changes
watch(sheetNames, (newNames) => {
  if (newNames.length > 0 && !newNames.includes(activeSheet.value)) {
    activeSheet.value = newNames[0]
  }
}, { immediate: true })

function sheetFieldCount(sheet: string): number {
  return new Set(props.results.filter((r) => (r.sheet_name || 'Studies') === sheet).map((r) => r.field_name)).size
}

const filteredResults = computed(() => {
  let filtered = props.results
  // Filter by active sheet when multiple sheets exist
  if (sheetNames.value.length > 1 && activeSheet.value) {
    filtered = filtered.filter((r) => (r.sheet_name || 'Studies') === activeSheet.value)
  }
  if (!confidenceFilter.value) return filtered
  if (confidenceFilter.value === 'LOW_FAILED') return filtered.filter((r) => ['LOW', 'FAILED'].includes(r.confidence?.toUpperCase()))
  return filtered.filter((r) => r.confidence?.toUpperCase() === confidenceFilter.value)
})

const pivotData = computed(() => {
  const src = filteredResults.value
  const fieldNames = [...new Set(src.map((r) => r.field_name))]
  const pdfIds = [...new Set(src.map((r) => r.pdf_id))]
  const cellMap = new Map<string, ResultCell>()
  for (const r of src) cellMap.set(`${r.pdf_id}::${r.field_name}`, r)
  return { fieldNames, pdfIds, cellMap }
})

const allSelected = computed(() => pivotData.value.pdfIds.length > 0 && pivotData.value.pdfIds.every((p) => bulk.isRowSelected(p, pivotData.value.fieldNames)))
const allFlatSelected = computed(() => filteredResults.value.length > 0 && filteredResults.value.every((c) => bulk.selectedCells.value.has(`${c.pdf_id}::${c.field_name}`)))

function cellBg(cell?: ResultCell): Record<string, string> {
  if (!cell) return {}
  const bg = confidenceColors[cell.confidence?.toLowerCase() || '']
  return bg ? { background: bg } : {}
}

function cellClass(pdfId: string, field: string, rowIdx: number, colIdx: number): string[] {
  const key = `${pdfId}::${field}`
  const cls = ['pivot-cell']
  if (selectedKey.value === key) cls.push('pivot-selected')
  if (bulk.selectedCells.value.has(key)) cls.push('pivot-checked')
  if (focusRow.value === rowIdx && focusCol.value === colIdx) cls.push('pivot-focused')
  return cls
}

function displayValue(val: unknown): string {
  if (val === null || val === undefined) return '--'
  const s = String(val)
  return s.length > 40 ? s.slice(0, 37) + '...' : s
}

function onCellClick(cell?: ResultCell, rowIdx?: number, colIdx?: number): void {
  if (cell) emit('select-cell', cell)
  if (rowIdx !== undefined) focusRow.value = rowIdx
  if (colIdx !== undefined) focusCol.value = colIdx
}

function startEdit(cell: ResultCell): void {
  editingCell.value = cell
  editValue.value = String(cell.value ?? '')
  // Switch to flat view so the inline edit input is visible
  viewMode.value = 'flat'
}

defineExpose({ startEdit })

function handleKeydown(e: KeyboardEvent): void {
  if (editingCell.value) return
  const rows = viewMode.value === 'pivot' ? pivotData.value.pdfIds.length : filteredResults.value.length
  const cols = viewMode.value === 'pivot' ? pivotData.value.fieldNames.length : 1
  switch (e.key) {
    case 'ArrowUp': e.preventDefault(); focusRow.value = Math.max(0, focusRow.value - 1); selectFocused(); break
    case 'ArrowDown': e.preventDefault(); focusRow.value = Math.min(rows - 1, focusRow.value + 1); selectFocused(); break
    case 'ArrowLeft': e.preventDefault(); focusCol.value = Math.max(0, focusCol.value - 1); selectFocused(); break
    case 'ArrowRight': e.preventDefault(); focusCol.value = Math.min(cols - 1, focusCol.value + 1); selectFocused(); break
    case 'Enter': e.preventDefault(); if (props.selectedCell) startEdit(props.selectedCell); break
    case 'Escape': e.preventDefault(); editingCell.value = null; break
    case ' ': e.preventDefault(); toggleFocused(); break
  }
}

function selectFocused(): void {
  if (viewMode.value === 'pivot') {
    const p = pivotData.value.pdfIds[focusRow.value], f = pivotData.value.fieldNames[focusCol.value]
    if (p && f) { const c = pivotData.value.cellMap.get(`${p}::${f}`); if (c) emit('select-cell', c) }
  } else {
    const c = filteredResults.value[focusRow.value]; if (c) emit('select-cell', c)
  }
}

function toggleFocused(): void {
  if (viewMode.value === 'pivot') {
    const p = pivotData.value.pdfIds[focusRow.value], f = pivotData.value.fieldNames[focusCol.value]
    if (p && f) bulk.toggleCell(`${p}::${f}`)
  } else {
    const c = filteredResults.value[focusRow.value]; if (c) bulk.toggleCell(`${c.pdf_id}::${c.field_name}`)
  }
}
</script>

<style scoped>
.pivot-wrapper { outline: none; }
.pivot-wrapper:focus { outline: 2px solid #93c5fd; outline-offset: 2px; border-radius: 0.375rem; }
.sheet-tabs { display: flex; gap: 0.25rem; margin-bottom: 0.75rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0; flex-wrap: wrap; }
.sheet-tab { padding: 0.5rem 1rem; border: none; background: none; cursor: pointer; font-size: 0.875rem; color: #6b7280; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.15s; border-radius: 0.25rem 0.25rem 0 0; }
.sheet-tab.active { color: #1d4ed8; border-bottom-color: #1d4ed8; font-weight: 600; }
.sheet-tab:hover:not(.active) { color: #374151; background: #f9fafb; }
.sheet-count { font-size: 0.75rem; color: #9ca3af; margin-left: 0.25rem; }
.bulk-toolbar { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 0.375rem; margin-bottom: 0.5rem; animation: fadeIn 0.2s ease-out; }
.btn-warning { background: #f59e0b; color: white; border: none; padding: 0.25rem 0.6rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.78rem; display: inline-flex; align-items: center; gap: 0.3rem; }
.btn-warning:hover { background: #d97706; }
.btn-success { background: #15803d; color: white; border: none; padding: 0.25rem 0.6rem; border-radius: 0.375rem; cursor: pointer; font-size: 0.78rem; display: inline-flex; align-items: center; gap: 0.3rem; }
.btn-success:hover { background: #166534; }
.pivot-controls { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
.view-toggle { display: flex; gap: 0.25rem; }
.btn-sm { padding: 0.25rem 0.6rem; font-size: 0.78rem; }
.filter-group { display: flex; align-items: center; gap: 0.4rem; }
.filter-label { font-size: 0.8rem; color: #6b7280; }
.filter-select { padding: 0.2rem 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem; font-size: 0.8rem; background: white; color: #374151; }
.checkbox-col { width: 30px; text-align: center; padding: 0.3rem !important; }
.checkbox-col input[type="checkbox"] { cursor: pointer; width: 14px; height: 14px; }
.pivot-scroll { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 0.5rem; }
.pivot-table { width: max-content; min-width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.pivot-table th, .pivot-table td { padding: 0.4rem 0.6rem; border: 1px solid #e5e7eb; text-align: left; vertical-align: top; white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.pivot-table th { background: #f9fafb; font-weight: 600; font-size: 0.75rem; position: sticky; top: 0; z-index: 1; }
.sticky-col { position: sticky; left: 30px; z-index: 2; background: #f9fafb; min-width: 90px; }
.pivot-table thead .sticky-col { z-index: 3; }
.pdf-name-cell { font-family: monospace; font-size: 0.75rem; color: #374151; }
.pivot-cell { cursor: pointer; transition: box-shadow 0.15s; position: relative; }
.pivot-cell:hover { box-shadow: inset 0 0 0 1px #93c5fd; }
.pivot-selected { box-shadow: inset 0 0 0 2px #1d4ed8 !important; }
.pivot-checked { background-image: linear-gradient(135deg, #bfdbfe 10%, transparent 10%) !important; }
.pivot-focused { outline: 2px dashed #6366f1; outline-offset: -2px; }
.cell-content { display: inline-flex; align-items: center; gap: 0.25rem; }
.cell-reviewed { color: #15803d; font-size: 0.65rem; }
.cell-flagged { color: #f59e0b; font-size: 0.65rem; }
.conf-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; position: absolute; top: 3px; right: 3px; cursor: help; }
.dot-verified { background: #15803d; } .dot-high { background: #22c55e; } .dot-medium { background: #eab308; }
.dot-low { background: #f97316; } .dot-single { background: #a3a3a3; } .dot-failed { background: #ef4444; }
.results-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.results-table th, .results-table td { padding: 0.5rem 0.75rem; border: 1px solid #e5e7eb; text-align: left; vertical-align: top; }
.results-table th { background: #f9fafb; font-weight: 600; white-space: nowrap; }
.results-table tr:hover td { background: #f9fafb; }
.selected-row td { background: #eff6ff !important; }
.confidence-badge { padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; white-space: nowrap; cursor: help; }
.confidence-verified { background: #15803d; color: white; } .confidence-high { background: #22c55e; color: white; }
.confidence-medium { background: #eab308; color: white; } .confidence-low { background: #f97316; color: white; }
.confidence-single { background: #a3a3a3; color: white; } .confidence-failed { background: #ef4444; color: white; }
.edit-input { width: 100%; padding: 0.25rem 0.375rem; border: 1px solid #1d4ed8; border-radius: 0.25rem; font-size: 0.875rem; outline: none; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>
