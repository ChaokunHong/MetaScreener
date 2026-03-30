<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">History</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Browse past sessions by module.</p>

    <div v-if="loading" class="glass-card" style="text-align: center; padding: 3rem;">
      <i class="fas fa-spinner fa-spin" style="font-size: 1.5rem; color: var(--primary-purple);"></i>
    </div>

    <template v-else>
      <div v-for="mod in modules" :key="mod.key" class="glass-card" style="margin-bottom: 1rem;">
        <div class="history-section-header" @click="toggleModule(mod.key)">
          <div class="history-section-left">
            <span :class="'history-module-badge history-module-badge--' + mod.key">
              <i :class="mod.icon"></i>
            </span>
            <span class="history-section-title">{{ mod.label }}</span>
            <span class="history-section-count" v-if="moduleCounts[mod.key]">{{ moduleCounts[mod.key] }}</span>
          </div>
          <i class="fas history-section-chevron" :class="expandedModule === mod.key ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
        </div>

        <div v-show="expandedModule === mod.key" class="history-section-body">
          <div v-if="moduleItems[mod.key]?.length" style="display:flex;justify-content:flex-end;margin-bottom:0.5rem;">
            <button class="btn btn-danger btn-sm" @click="confirmClearModule(mod)">
              <i class="fas fa-trash-can"></i> Clear All {{ mod.label }}
            </button>
          </div>
          <div v-if="!moduleItems[mod.key]?.length" class="text-muted" style="padding: 1rem 0; text-align: center; font-size: 0.85rem;">
            No {{ mod.label.toLowerCase() }} history yet.
          </div>
          <div v-else class="history-item-list">
            <div v-for="item in moduleItems[mod.key]" :key="item.id" class="history-item-row">
              <div class="history-item-info">
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
                  <span class="history-item-date">{{ fmtDate(item.created_at) }}</span>
                </template>
              </div>
              <p v-if="item.summary && renamingId !== item.id" class="history-item-summary">{{ item.summary }}</p>
              <div v-if="renamingId !== item.id" class="history-item-actions">
                <button class="btn btn-primary btn-sm" @click="doLoad(item)">
                  <i class="fas fa-arrow-up-right-from-square"></i> Load
                </button>
                <button class="btn btn-secondary btn-sm" @click="startRename(item)">
                  <i class="fas fa-pen"></i>
                </button>
                <button class="btn btn-danger btn-sm" @click="confirmDelete(item)">
                  <i class="fas fa-trash-can"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <Teleport to="body">
      <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
        <div class="modal-glass">
          <div class="modal-header">
            <div class="modal-header-title">
              <div class="modal-header-icon modal-header-icon--danger"><i class="fas fa-trash-can"></i></div>
              <h3>Delete Item</h3>
            </div>
            <button class="modal-close-btn" @click="deleteTarget = null"><i class="fas fa-times"></i></button>
          </div>
          <div class="modal-body">
            <p class="modal-subtitle">Delete <strong>{{ deleteTarget.name }}</strong>?</p>
            <p style="margin-top: 0.5rem; font-size: 0.82rem; color: #64748b;">This cannot be undone.</p>
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

    <Teleport to="body">
      <div v-if="clearModuleTarget" class="modal-overlay" @click.self="clearModuleTarget = null">
        <div class="modal-glass">
          <div class="modal-header">
            <div class="modal-header-title">
              <div class="modal-header-icon modal-header-icon--danger"><i class="fas fa-trash-can"></i></div>
              <h3>Clear All {{ clearModuleTarget.label }}</h3>
            </div>
            <button class="modal-close-btn" @click="clearModuleTarget = null"><i class="fas fa-times"></i></button>
          </div>
          <div class="modal-body">
            <p class="modal-subtitle">Delete all <strong>{{ moduleCounts[clearModuleTarget.key] }}</strong> {{ clearModuleTarget.label.toLowerCase() }} records?</p>
            <p style="margin-top: 0.5rem; font-size: 0.82rem; color: #64748b;">This cannot be undone.</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="clearModuleTarget = null">Cancel</button>
            <button class="btn btn-danger" :disabled="deleting" @click="doClearModule">
              <i v-if="deleting" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-trash-can"></i>
              Clear All
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
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

const modules = [
  { key: 'criteria',   icon: 'fas fa-list-check',      label: 'Criteria' },
  { key: 'screening',  icon: 'fas fa-filter',           label: 'Screening' },
  { key: 'extraction', icon: 'fas fa-table',            label: 'Extraction' },
  { key: 'quality',    icon: 'fas fa-clipboard-check',  label: 'Quality' },
  { key: 'evaluation', icon: 'fas fa-chart-bar',        label: 'Evaluation' },
]

const loading = ref(true)
const allItems = ref<HistoryItem[]>([])
const expandedModule = ref('')

const renamingId = ref('')
const renameValue = ref('')
const renameInput = ref<HTMLInputElement[] | null>(null)

const deleteTarget = ref<HistoryItem | null>(null)
const clearModuleTarget = ref<{ key: string; label: string } | null>(null)
const deleting = ref(false)

const moduleItems = computed(() => {
  const grouped: Record<string, HistoryItem[]> = {}
  for (const mod of modules) grouped[mod.key] = []
  for (const item of allItems.value) {
    if (grouped[item.module]) grouped[item.module].push(item)
  }
  return grouped
})

const moduleCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const mod of modules) {
    counts[mod.key] = moduleItems.value[mod.key]?.length || 0
  }
  return counts
})

function toggleModule(key: string) {
  expandedModule.value = expandedModule.value === key ? '' : key
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

async function fetchAll() {
  loading.value = true
  try {
    const res = await apiGet<{ items: HistoryItem[] }>('/history')
    allItems.value = res.items || []
  } catch { allItems.value = [] }
  finally { loading.value = false }
}

function startRename(item: HistoryItem) {
  renamingId.value = item.id
  renameValue.value = item.name
  nextTick(() => { renameInput.value?.[0]?.focus() })
}

async function doRename(item: HistoryItem) {
  if (!renameValue.value.trim()) return
  try {
    await apiPut(`/history/${item.module}/${item.id}/rename`, { name: renameValue.value.trim() })
    item.name = renameValue.value.trim()
  } catch { /* ignore */ }
  renamingId.value = ''
}

function confirmDelete(item: HistoryItem) { deleteTarget.value = item }
function confirmClearModule(mod: { key: string; label: string }) { clearModuleTarget.value = mod }

async function doClearModule() {
  if (!clearModuleTarget.value) return
  deleting.value = true
  try {
    await apiDelete(`/history/${clearModuleTarget.value.key}`)
    allItems.value = allItems.value.filter(i => i.module !== clearModuleTarget.value!.key)
    clearModuleTarget.value = null
  } catch { /* ignore */ }
  deleting.value = false
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await apiDelete(`/history/${deleteTarget.value.module}/${deleteTarget.value.id}`)
    allItems.value = allItems.value.filter(i => i.id !== deleteTarget.value!.id)
    deleteTarget.value = null
  } catch { /* ignore */ }
  deleting.value = false
}

async function doLoad(item: HistoryItem) {
  if (item.module === 'criteria') {
    try {
      const full = await apiGet<{ data: SavedCriteria }>(`/history/${item.module}/${item.id}`)
      criteriaStore.setCriteria(full.data)
      router.push('/criteria')
    } catch { router.push('/criteria') }
    return
  }

  if (item.module === 'screening') {
    try {
      const full = await apiGet<{ data: { stage?: string; results?: unknown[] } }>(`/history/${item.module}/${item.id}`)
      const stage = full.data?.stage === 'ft' ? 'ft' : 'ta'
      // Store in sessionStorage for the target view to pick up
      sessionStorage.setItem('metascreener_history_results', JSON.stringify(full.data))
      router.push(`/screening/${stage}`)
    } catch {
      router.push('/screening')
    }
    return
  }

  const routes: Record<string, string> = {
    evaluation: '/evaluation',
    extraction: '/extraction',
    quality: '/quality',
  }
  router.push({ path: routes[item.module] || '/', query: { historyId: item.id } })
}

onMounted(fetchAll)
</script>

<style scoped>
.history-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  padding: 0.25rem 0;
}
.history-section-header:hover { opacity: 0.85; }
.history-section-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.history-section-title {
  font-weight: 600;
  font-size: 1rem;
}
.history-section-count {
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: rgba(139,92,246,0.1);
  color: var(--primary-purple, #8b5cf6);
}
.history-section-chevron {
  font-size: 0.75rem;
  color: var(--text-secondary, #999);
  transition: transform 0.2s;
}
.history-module-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  font-size: 0.85rem;
}
.history-module-badge--criteria { background: rgba(139,92,246,0.12); color: #a78bfa; }
.history-module-badge--screening { background: rgba(6,182,212,0.12); color: #67e8f9; }
.history-module-badge--evaluation { background: rgba(245,158,11,0.12); color: #fbbf24; }
.history-module-badge--extraction { background: rgba(16,185,129,0.12); color: #6ee7b7; }
.history-module-badge--quality { background: rgba(239,68,68,0.12); color: #fca5a5; }

.history-section-body {
  margin-top: 0.75rem;
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-top: 0.75rem;
}
.history-item-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.history-item-row {
  padding: 0.7rem 0.85rem;
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(0,0,0,0.25);
}
.history-item-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.history-item-name {
  font-weight: 600;
  font-size: 0.88rem;
  flex: 1;
}
.history-item-date {
  font-size: 0.72rem;
  color: var(--text-secondary, #999);
  white-space: nowrap;
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
.history-rename-input:focus { border-color: var(--primary-purple, #8b5cf6); }
.btn-icon {
  background: none;
  border: none;
  color: var(--text-secondary, #999);
  cursor: pointer;
  padding: 0.25rem;
  font-size: 0.85rem;
}
.btn-icon:hover { color: var(--text-primary, #fff); }
.history-item-summary {
  font-size: 0.78rem;
  color: var(--text-secondary, #999);
  margin: 0 0 0.5rem 0;
  line-height: 1.4;
}
.history-item-actions {
  display: flex;
  gap: 0.35rem;
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
  background:
    radial-gradient(120% 100% at 0% 0%, rgba(129,216,208,0.14) 0%, transparent 48%),
    radial-gradient(120% 110% at 100% 100%, rgba(139,92,246,0.14) 0%, transparent 52%),
    rgba(255, 255, 255, 0.92);
  -webkit-backdrop-filter: blur(24px) saturate(145%);
  backdrop-filter: blur(24px) saturate(145%);
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 16px;
  padding: 1.75rem;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 24px 56px rgba(15,23,42,0.22), inset 0 1px 0 rgba(255,255,255,0.94);
  color: #1e293b;
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
  color: #1e293b;
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
  color: #334155;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
