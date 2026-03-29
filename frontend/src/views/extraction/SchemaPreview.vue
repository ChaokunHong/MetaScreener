<template>
  <div v-if="sheets.length > 0" class="schema-preview fade-in">
    <div v-for="sheet in localSheets" :key="sheet.name" class="schema-sheet">
      <div class="schema-sheet-header" @click="sheet.expanded = !sheet.expanded">
        <i :class="['fas', sheet.expanded ? 'fa-chevron-down' : 'fa-chevron-right']"></i>
        <strong>{{ sheet.name }}</strong>
        <span class="text-muted">({{ sheet.fields.length }} fields)</span>
      </div>
      <table v-if="sheet.expanded" class="schema-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Type</th>
            <th>Role</th>
            <th>Required</th>
            <th>Semantic Tag</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="field in sheet.fields" :key="field.name">
            <td>{{ field.name }}</td>
            <td><span class="badge-type">{{ field.field_type }}</span></td>
            <td><span class="badge-role">{{ field.role }}</span></td>
            <td>
              <i v-if="field.required" class="fas fa-check" style="color: #16a34a;"></i>
              <span v-else class="text-muted">--</span>
            </td>
            <td>
              <span v-if="field.semantic_tag" class="badge-tag">{{ field.semantic_tag }}</span>
              <span v-else class="text-muted">--</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

export interface SchemaField {
  name: string
  field_type: string
  role: string
  required: boolean
  semantic_tag?: string
}

export interface SchemaSheet {
  name: string
  fields: SchemaField[]
  expanded: boolean
}

const props = defineProps<{
  sheets: SchemaSheet[]
}>()

// Local reactive copy so we can toggle expanded without mutating props
const localSheets = ref<SchemaSheet[]>([])

watch(
  () => props.sheets,
  (val) => {
    localSheets.value = val.map((s) => ({ ...s, expanded: s.expanded ?? false }))
  },
  { immediate: true }
)
</script>

<style scoped>
.fade-in {
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.schema-preview {
  margin-top: 0.75rem;
}

.schema-sheet {
  margin-bottom: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.schema-sheet-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  background: #f9fafb;
  cursor: pointer;
  font-size: 0.875rem;
  user-select: none;
}

.schema-sheet-header:hover {
  background: #f3f4f6;
}

.schema-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.schema-table th,
.schema-table td {
  padding: 0.35rem 0.6rem;
  border-top: 1px solid #e5e7eb;
  text-align: left;
}

.schema-table th {
  background: #f9fafb;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #6b7280;
}

.badge-type,
.badge-role,
.badge-tag {
  display: inline-block;
  padding: 0.05rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.badge-type {
  background: #e0f2fe;
  color: #0369a1;
}

.badge-role {
  background: #fef3c7;
  color: #92400e;
}

.badge-tag {
  background: #f0fdf4;
  color: #15803d;
}
</style>
