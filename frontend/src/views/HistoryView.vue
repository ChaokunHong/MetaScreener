<template>
  <div>
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem;">
      <h1 class="page-title" style="margin-bottom: 0;">History</h1>
      <button
        v-if="items.length > 0"
        class="btn btn-danger btn-sm"
        @click="showClearModal = true"
      >
        <i class="fas fa-trash-can"></i>
        {{ activeFilter ? `Clear ${activeFilter}` : 'Clear All' }}
      </button>
    </div>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Browse past sessions across all modules.</p>

    <!-- Module filter tabs -->
    <div class="history-filter-tabs">
      <button
        v-for="tab in filterTabs"
        :key="tab.value"
        class="history-filter-tab"
        :class="{ active: activeFilter === tab.value }"
        @click="activeFilter = tab.value; fetchItems()"
      >
        <i :class="tab.icon"></i> {{ tab.label }}
        <span v-if="tab.value === '' && items.length" class="history-tab-count">{{ totalCount }}</span>
      </button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="glass-card" style="text-align: center; padding: 3rem;">
      <i class="fas fa-spinner fa-spin" style="font-size: 1.5rem; color: var(--primary-purple);"></i>
      <p class="text-muted" style="margin-top: 0.75rem;">Loading history...</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="items.length === 0" class="glass-card" style="text-align: center; padding: 3rem;">
      <i class="fas fa-clock-rotate-left" style="font-size: 2.5rem; color: var(--text-secondary); opacity: 0.4;"></i>
      <p style="margin-top: 1rem; font-weight: 600; color: var(--text-primary);">No history yet</p>
      <p class="text-muted" style="margin-top: 0.25rem;">Sessions will appear here automatically after you run criteria, screening, evaluation, extraction, or quality assessment.</p>
    </div>

    <!-- History item list -->
    <div v-else class="history-list">
      <div v-for="item in items" :key="item.id" class="glass-card history-item-card">
        <div class="history-item-header">
          <span :class="'history-module-badge history-module-badge--' + item.module">
            <i :class="moduleIcon(item.module)"></i>
            {{ item.module }}
            <span v-if="item.module === 'screening' && screeningStage(item)" class="history-stage-badge">
              {{ screeningStage(item) }}
            </span>
          </span>
          <span class="history-item-date">{{ fmtDate(item.created_at) }}</span>
        </div>

        <div class="history-item-name-row">
          <!-- Inline rename -->
          <template v-if="renamingId === item.id">
            <input
              v-model="renameValue"
              class="history-rename-input"
              @keyup.enter="doRename(item)"
              @keyup.escape="renamingId = ''"
              ref="renameInput"
            />
            <button class="btn-icon" @click="doRename(item)" title="Save"><i class="fas fa-check"></i></button>
            <button class="btn-icon" @click="renamingId = ''" title="Cancel"><i class="fas fa-times"></i></button>
          </template>
          <template v-else>
            <span class="history-item-name">{{ item.name }}</span>
          </template>
        </div>

        <p v-if="item.summary" class="history-item-summary">{{ item.summary }}</p>

        <div class="history-item-actions">
          <button class="btn btn-primary btn-sm" @click="doLoad(item)">
            <i class="fas fa-arrow-up-right-from-square"></i> Load
          </button>
          <button class="btn btn-secondary btn-sm" @click="startRename(item)">
            <i class="fas fa-pen"></i> Rename
          </button>
          <button class="btn btn-danger btn-sm" @click="confirmDelete(item)">
            <i class="fas fa-trash-can"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
        <div class="modal-glass">
          <div class="modal-header">
            <div class="modal-header-title">
              <div class="modal-header-icon modal-header-icon--danger"><i class="fas fa-trash-can"></i></div>
              <h3>Delete History Item</h3>
            </div>
            <button class="modal-close-btn" @click="deleteTarget = null"><i class="fas fa-times"></i></button>
          </div>
          <div class="modal-body">
            <p class="modal-subtitle">Are you sure you want to delete <strong>{{ deleteTarget.name }}</strong>?</p>
            <p class="text-muted" style="margin-top: 0.5rem;">This action cannot be undone.</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="deleteTarget = null">Cancel</button>
            <button class="btn btn-danger" :disabled="deleting" @click="doDelete">
              <i v-if="deleting" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-trash-can"></i>
              Delete
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Batch clear confirmation modal -->
    <Teleport to="body">
      <div v-if="showClearModal" class="modal-overlay" @click.self="showClearModal = false">
        <div class="modal-glass">
          <div class="modal-header">
            <div class="modal-header-title">
              <div class="modal-header-icon modal-header-icon--danger"><i class="fas fa-trash-can"></i></div>
              <h3>{{ activeFilter ? `Clear ${activeFilter} History` : 'Clear All History' }}</h3>
            </div>
            <button class="modal-close-btn" @click="showClearModal = false"><i class="fas fa-times"></i></button>
          </div>
          <div class="modal-body">
            <p class="modal-subtitle">
              Are you sure you want to delete
              <strong>{{ activeFilter ? `all ${items.length} ${activeFilter} entries` : `all ${totalCount} history entries` }}</strong>?
            </p>
            <p class="text-muted" style="margin-top: 0.5rem;">This action cannot be undone.</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showClearModal = false">Cancel</button>
            <button class="btn btn-danger" :disabled="clearing" @click="doClear">
              <i v-if="clearing" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-trash-can"></i>
              Delete All
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPut, apiDelete } from '@/api'
import { useCriteriaStore, type SavedCriteria } from '@/stores/criteria'

interface HistoryItem {
  id: string
  module: string
  name: string
  created_at: string
  updated_at: string
  summary: string
}

const router = useRouter()
const criteriaStore = useCriteriaStore()

const filterTabs = [
  { value: '',           icon: 'fas fa-layer-group',       label: 'All' },
  { value: 'criteria',   icon: 'fas fa-filter',            label: 'Criteria' },
  { value: 'screening',  icon: 'fas fa-search',            label: 'Screening' },
  { value: 'evaluation', icon: 'fas fa-chart-bar',         label: 'Evaluation' },
  { value: 'extraction', icon: 'fas fa-table',             label: 'Extraction' },
  { value: 'quality',    icon: 'fas fa-clipboard-check',   label: 'Quality' },
]

const activeFilter = ref('')
const items = ref<HistoryItem[]>([])
const totalCount = ref(0)
const loading = ref(false)

// Rename state
const renamingId = ref('')
const renameValue = ref('')
const renameInput = ref<HTMLInputElement[] | null>(null)

// Delete state
const deleteTarget = ref<HistoryItem | null>(null)
const deleting = ref(false)

// Batch clear state
const showClearModal = ref(false)
const clearing = ref(false)

function moduleIcon(module: string): string {
  const map: Record<string, string> = {
    criteria: 'fas fa-filter',
    screening: 'fas fa-search',
    evaluation: 'fas fa-chart-bar',
    extraction: 'fas fa-table',
    quality: 'fas fa-clipboard-check',
  }
  return map[module] || 'fas fa-clock-rotate-left'
}

function screeningStage(item: HistoryItem): string {
  // Extract stage from name pattern: "Screening (Title/Abstract)" or "Screening (Full-text)"
  if (item.name.includes('Title/Abstract') || item.name.includes('(TA)')) return 'TA'
  if (item.name.includes('Full-text') || item.name.includes('(FT)')) return 'FT'
  return ''  // legacy entries without stage
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

async function fetchItems() {
  loading.value = true
  try {
    const params = activeFilter.value ? `?module=${activeFilter.value}` : ''
    const res = await apiGet<{ items: HistoryItem[]; total: number }>(`/history${params}`)
    items.value = res.items
    totalCount.value = res.total
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function startRename(item: HistoryItem) {
  renamingId.value = item.id
  renameValue.value = item.name
  nextTick(() => {
    if (renameInput.value && renameInput.value.length > 0) {
      renameInput.value[0].focus()
    }
  })
}

async function doRename(item: HistoryItem) {
  if (!renameValue.value.trim()) return
  try {
    await apiPut(`/history/${item.module}/${item.id}/rename`, { name: renameValue.value.trim() })
    item.name = renameValue.value.trim()
  } catch { /* ignore */ }
  renamingId.value = ''
}

function confirmDelete(item: HistoryItem) {
  deleteTarget.value = item
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await apiDelete(`/history/${deleteTarget.value.module}/${deleteTarget.value.id}`)
    items.value = items.value.filter(i => i.id !== deleteTarget.value!.id)
    totalCount.value = items.value.length
    deleteTarget.value = null
  } catch { /* ignore */ }
  deleting.value = false
}

async function doClear() {
  clearing.value = true
  try {
    if (activeFilter.value) {
      await apiDelete(`/history/${activeFilter.value}`)
    } else {
      await apiDelete('/history')
    }
    items.value = []
    totalCount.value = 0
    showClearModal.value = false
  } catch { /* ignore */ }
  clearing.value = false
}

async function doLoad(item: HistoryItem) {
  if (item.module === 'criteria') {
    // Load criteria data into store, then navigate
    try {
      const full = await apiGet<{ data: SavedCriteria }>(`/history/${item.module}/${item.id}`)
      criteriaStore.setCriteria(full.data)
      router.push('/criteria')
    } catch {
      router.push('/criteria')
    }
    return
  }
  // For other modules, navigate with historyId query param
  const routes: Record<string, string> = {
    screening: '/screening',
    evaluation: '/evaluation',
    extraction: '/extraction',
    quality: '/quality',
  }
  const path = routes[item.module] || '/'
  router.push({ path, query: { historyId: item.id } })
}

onMounted(fetchItems)
</script>
