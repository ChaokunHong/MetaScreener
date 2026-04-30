<template>
  <div class="glass-card" style="margin-bottom: 1.5rem;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div class="section-title" style="margin-bottom: 0;">
        <i class="fas fa-history"></i> Sessions
      </div>
      <button class="btn btn-primary btn-sm" @click="$emit('new-session')">
        <i class="fas fa-plus"></i> New Session
      </button>
    </div>

    <div v-if="loading" class="text-muted" style="margin-top: 0.5rem;">
      <i class="fas fa-spinner fa-spin"></i> Loading sessions...
    </div>

    <div v-else-if="sessions.length === 0" class="text-muted" style="margin-top: 0.5rem;">
      No previous sessions. Create a new one to get started.
    </div>

    <div v-else class="session-list">
      <div
        v-for="s in sessions"
        :key="s.id"
        class="session-item"
        @click="$emit('resume', s.id)"
      >
        <div class="session-info">
          <strong>{{ s.id.slice(0, 8) }}</strong>
          <span :class="['session-status', `status-${s.status}`]">{{ s.status }}</span>
        </div>
        <div class="session-meta text-muted">
          Created: {{ formatDate(s.created_at) }}
        </div>
        <button
          class="btn-icon-danger"
          @click.stop="confirmDelete(s.id)"
          title="Delete session"
        >
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = '/api/extraction/v3'

const emit = defineEmits<{
  (e: 'resume', sessionId: string): void
  (e: 'new-session'): void
}>()

interface Session {
  id: string
  session_id?: string
  status: string
  created_at: string
}

const sessions = ref<Session[]>([])
const loading = ref(false)

function formatDate(iso: string): string {
  if (!iso) return 'N/A'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function fetchSessions(): Promise<void> {
  loading.value = true
  try {
    const resp = await fetch(`${API_BASE}/sessions`)
    if (!resp.ok) return
    const data = await resp.json()
    sessions.value = (data as any[]).map((s) => ({
      id: s.session_id ?? s.id,
      status: s.status ?? 'unknown',
      created_at: s.created_at ?? '',
    }))
  } catch {
    sessions.value = []
  } finally {
    loading.value = false
  }
}

async function confirmDelete(sessionId: string): Promise<void> {
  const ok = window.confirm(`Delete session ${sessionId.slice(0, 8)}...? This cannot be undone.`)
  if (!ok) return
  try {
    const resp = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' })
    if (resp.ok) {
      sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    }
  } catch {
  }
}

/** Allow parent to trigger a refresh after session creation. */
defineExpose({ fetchSessions })

onMounted(fetchSessions)
</script>

<style scoped>
.session-list {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 260px;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #f9fafb;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.session-item:hover {
  background: #eff6ff;
  border-color: #93c5fd;
}

.session-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.session-meta {
  flex: 1;
  font-size: 0.8rem;
}

.session-status {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}

.status-created {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-running {
  background: #fef3c7;
  color: #92400e;
}

.status-completed {
  background: #d1fae5;
  color: #065f46;
}

.status-failed {
  background: #fef2f2;
  color: #b91c1c;
}

.status-unknown {
  background: #f3f4f6;
  color: #6b7280;
}

.btn-icon-danger {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  padding: 0.25rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.8rem;
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
}

.btn-icon-danger:hover {
  color: #dc2626;
  background: #fef2f2;
}

.btn-sm {
  padding: 0.3rem 0.75rem;
  font-size: 0.8rem;
}
</style>
