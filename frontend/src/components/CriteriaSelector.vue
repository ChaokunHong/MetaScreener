<template>
  <div class="criteria-selector">
    <!-- Loading -->
    <div v-if="loading" style="text-align: center; padding: 2rem;">
      <i class="fas fa-spinner fa-spin"></i> Loading saved criteria...
    </div>

    <!-- Empty state -->
    <div v-else-if="criteriaList.length === 0" class="criteria-empty">
      <i class="fas fa-list-check" style="font-size: 2rem; opacity: 0.3;"></i>
      <p style="margin-top: 0.75rem; font-weight: 600;">No saved criteria</p>
      <p class="text-muted">Create criteria in the Criteria Wizard first.</p>
      <router-link to="/criteria" class="btn btn-primary" style="margin-top: 0.75rem;">
        <i class="fas fa-wand-magic-sparkles"></i> Open Criteria Wizard
      </router-link>
    </div>

    <!-- Criteria list -->
    <template v-else>
      <!-- Tag filter -->
      <div v-if="allTags.length" class="criteria-tag-filter">
        <button
          class="tag-filter-btn"
          :class="{ active: !activeTag }"
          @click="activeTag = ''"
        >All</button>
        <button
          v-for="tag in allTags"
          :key="tag"
          class="tag-filter-btn"
          :class="{ active: activeTag === tag }"
          @click="activeTag = activeTag === tag ? '' : tag"
        >{{ tag }}</button>
      </div>

      <!-- Cards -->
      <div class="criteria-card-list">
        <div
          v-for="item in filteredList"
          :key="item.id"
          class="criteria-card"
          :class="{ selected: selectedId === item.id }"
          @click="selectCriteria(item)"
        >
          <div class="criteria-card-header">
            <span class="criteria-card-name">{{ item.name }}</span>
            <span class="criteria-card-date">{{ fmtDate(item.created_at) }}</span>
          </div>
          <p v-if="item.summary" class="criteria-card-summary">{{ item.summary }}</p>
          <div v-if="item.tags?.length" class="criteria-card-tags">
            <span v-for="tag in item.tags" :key="tag" class="tag-chip-sm">{{ tag }}</span>
          </div>
          <div v-if="selectedId === item.id" class="criteria-card-check">
            <i class="fas fa-check-circle"></i>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiGet } from '@/api'

interface CriteriaListItem {
  id: string
  name: string
  created_at: string
  summary: string
  tags: string[]
}

const props = defineProps<{
  modelValue?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [id: string | null]
  'select': [item: CriteriaListItem]
}>()

const loading = ref(true)
const criteriaList = ref<CriteriaListItem[]>([])
const selectedId = ref<string | null>(props.modelValue || null)
const activeTag = ref('')

onMounted(async () => {
  try {
    const resp = await apiGet<{ items: CriteriaListItem[] }>('/history?module=criteria')
    criteriaList.value = resp.items || []
  } catch {
    criteriaList.value = []
  } finally {
    loading.value = false
  }
})

const allTags = computed(() => {
  const set = new Set<string>()
  criteriaList.value.forEach(c => c.tags?.forEach(t => set.add(t)))
  return Array.from(set).sort()
})

const filteredList = computed(() => {
  if (!activeTag.value) return criteriaList.value
  return criteriaList.value.filter(c => c.tags?.includes(activeTag.value))
})

function selectCriteria(item: CriteriaListItem) {
  selectedId.value = item.id
  emit('update:modelValue', item.id)
  emit('select', item)
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.criteria-selector {
  min-height: 120px;
}
.criteria-empty {
  text-align: center;
  padding: 2rem;
}
.criteria-tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 1rem;
}
.tag-filter-btn {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--text-secondary, #999);
  cursor: pointer;
  transition: all 0.15s;
}
.tag-filter-btn.active {
  background: rgba(139, 92, 246, 0.15);
  border-color: rgba(139, 92, 246, 0.4);
  color: var(--primary-purple, #8b5cf6);
}
.criteria-card-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.criteria-card {
  position: relative;
  padding: 0.85rem 1rem;
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.criteria-card:hover {
  border-color: rgba(139, 92, 246, 0.3);
  background: rgba(139, 92, 246, 0.05);
}
.criteria-card.selected {
  border-color: rgba(139, 92, 246, 0.5);
  background: rgba(139, 92, 246, 0.08);
}
.criteria-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}
.criteria-card-name {
  font-weight: 600;
  font-size: 0.9rem;
}
.criteria-card-date {
  font-size: 0.72rem;
  color: var(--text-secondary, #999);
}
.criteria-card-summary {
  font-size: 0.8rem;
  color: var(--text-secondary, #999);
  margin: 0;
}
.criteria-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.4rem;
}
.tag-chip-sm {
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  font-size: 0.68rem;
  background: rgba(139, 92, 246, 0.1);
  color: var(--primary-purple, #8b5cf6);
  border: 1px solid rgba(139, 92, 246, 0.2);
}
.criteria-card-check {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  color: var(--primary-purple, #8b5cf6);
  font-size: 1.1rem;
}
</style>
