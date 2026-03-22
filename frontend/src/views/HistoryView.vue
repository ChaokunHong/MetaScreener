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

<style scoped>
.history-filter-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 1.5rem;
}
.history-filter-tab {
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--text-secondary, #999);
  cursor: pointer;
  transition: all 0.15s;
}
.history-filter-tab:hover {
  border-color: rgba(139,92,246,0.3);
  color: var(--text-primary, #fff);
}
.history-filter-tab.active {
  background: rgba(139,92,246,0.15);
  border-color: rgba(139,92,246,0.4);
  color: var(--primary-purple, #8b5cf6);
  font-weight: 600;
}
.history-tab-count {
  margin-left: 0.3rem;
  font-size: 0.7rem;
  opacity: 0.7;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.history-item-card {
  padding: 1.25rem 1.5rem;
}
.history-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
}
.history-module-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: capitalize;
}
.history-module-badge--criteria {
  background: rgba(139,92,246,0.12);
  color: #a78bfa;
}
.history-module-badge--screening {
  background: rgba(6,182,212,0.12);
  color: #67e8f9;
}
.history-module-badge--evaluation {
  background: rgba(245,158,11,0.12);
  color: #fbbf24;
}
.history-module-badge--extraction {
  background: rgba(16,185,129,0.12);
  color: #6ee7b7;
}
.history-module-badge--quality {
  background: rgba(239,68,68,0.12);
  color: #fca5a5;
}
.history-stage-badge {
  margin-left: 0.3rem;
  font-size: 0.65rem;
  opacity: 0.7;
}
.history-item-date {
  font-size: 0.75rem;
  color: var(--text-secondary, #999);
}
.history-item-name-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.35rem;
}
.history-item-name {
  font-weight: 600;
  font-size: 0.95rem;
}
.history-rename-input {
  flex: 1;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  border: 1px solid rgba(139,92,246,0.4);
  background: rgba(255,255,255,0.05);
  color: inherit;
  font-size: 0.85rem;
  outline: none;
}
.history-rename-input:focus {
  border-color: var(--primary-purple, #8b5cf6);
}
.btn-icon {
  background: none;
  border: none;
  color: var(--text-secondary, #999);
  cursor: pointer;
  padding: 0.25rem;
  font-size: 0.85rem;
}
.btn-icon:hover {
  color: var(--text-primary, #fff);
}
.history-item-summary {
  font-size: 0.8rem;
  color: var(--text-secondary, #999);
  margin: 0 0 0.75rem 0;
  line-height: 1.4;
}
.history-item-actions {
  display: flex;
  gap: 0.4rem;
}
</style>

<style>
/* Modal styles (unscoped — Teleport renders outside component tree) */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}
.modal-glass {
  background: linear-gradient(160deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.06) 100%);
  backdrop-filter: blur(20px) saturate(160%);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 16px;
  padding: 1.75rem;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 16px 40px rgba(0,0,0,0.2);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.modal-header-title {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.modal-header-title h3 {
  margin: 0;
  font-size: 1.1rem;
}
.modal-header-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}
.modal-header-icon--danger {
  background: rgba(239,68,68,0.15);
  color: #ef4444;
}
.modal-close-btn {
  background: rgba(255,255,255,0.08);
  border: none;
  border-radius: 50%;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary, #999);
  transition: all 0.15s;
}
.modal-close-btn:hover {
  background: rgba(255,255,255,0.15);
  color: var(--text-primary, #fff);
}
.modal-body {
  margin-bottom: 1.25rem;
}
.modal-subtitle {
  font-size: 0.9rem;
  margin: 0;
  line-height: 1.5;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
