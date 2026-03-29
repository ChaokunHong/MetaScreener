/**
 * Composable: bulk selection, accept, flag operations for pivot table.
 */
import { ref, computed } from 'vue'

export function useBulkOperations() {
  const selectedCells = ref(new Set<string>())
  const reviewedCells = ref(new Set<string>())
  const flaggedCells = ref(new Set<string>())

  function isRowSelected(pdfId: string, fieldNames: string[]): boolean {
    return fieldNames.every((f) => selectedCells.value.has(`${pdfId}::${f}`))
  }

  function toggleRow(pdfId: string, fieldNames: string[]): void {
    const allIn = isRowSelected(pdfId, fieldNames)
    for (const f of fieldNames) {
      const key = `${pdfId}::${f}`
      if (allIn) selectedCells.value.delete(key)
      else selectedCells.value.add(key)
    }
    selectedCells.value = new Set(selectedCells.value)
  }

  function toggleSelectAll(pdfIds: string[], fieldNames: string[], allSelected: boolean): void {
    if (allSelected) {
      selectedCells.value.clear()
    } else {
      for (const pid of pdfIds) {
        for (const f of fieldNames) {
          selectedCells.value.add(`${pid}::${f}`)
        }
      }
    }
    selectedCells.value = new Set(selectedCells.value)
  }

  function toggleSelectAllFlat(cells: { pdf_id: string; field_name: string }[], allFlatSel: boolean): void {
    if (allFlatSel) {
      selectedCells.value.clear()
    } else {
      for (const c of cells) {
        selectedCells.value.add(`${c.pdf_id}::${c.field_name}`)
      }
    }
    selectedCells.value = new Set(selectedCells.value)
  }

  function toggleCell(key: string): void {
    if (selectedCells.value.has(key)) selectedCells.value.delete(key)
    else selectedCells.value.add(key)
    selectedCells.value = new Set(selectedCells.value)
  }

  function bulkAccept(): void {
    for (const key of selectedCells.value) {
      reviewedCells.value.add(key)
      flaggedCells.value.delete(key)
    }
    reviewedCells.value = new Set(reviewedCells.value)
    flaggedCells.value = new Set(flaggedCells.value)
    selectedCells.value = new Set()
  }

  function bulkFlag(): void {
    for (const key of selectedCells.value) {
      flaggedCells.value.add(key)
      reviewedCells.value.delete(key)
    }
    flaggedCells.value = new Set(flaggedCells.value)
    reviewedCells.value = new Set(reviewedCells.value)
    selectedCells.value = new Set()
  }

  function clearSelection(): void {
    selectedCells.value = new Set()
  }

  return {
    selectedCells,
    reviewedCells,
    flaggedCells,
    isRowSelected,
    toggleRow,
    toggleSelectAll,
    toggleSelectAllFlat,
    toggleCell,
    bulkAccept,
    bulkFlag,
    clearSelection,
  }
}

/** Confidence tooltips for badges. */
export const confidenceDescriptions: Record<string, string> = {
  verified: 'Extracted directly from table structure, fully validated',
  high: 'Both models agree on this value',
  medium: 'Resolved through model arbitration',
  low: 'Models disagree -- please review',
  single: 'Single model extraction, no cross-validation',
  failed: 'Extraction failed -- manual entry needed',
}

export function confidenceTooltip(conf?: string): string {
  if (!conf) return ''
  return confidenceDescriptions[conf.toLowerCase()] || conf
}

export const confidenceColors: Record<string, string> = {
  verified: 'rgba(21, 128, 61, 0.2)',
  high: 'rgba(34, 197, 94, 0.2)',
  medium: 'rgba(234, 179, 8, 0.2)',
  low: 'rgba(249, 115, 22, 0.2)',
  single: 'rgba(163, 163, 163, 0.2)',
  failed: 'rgba(239, 68, 68, 0.2)',
}
