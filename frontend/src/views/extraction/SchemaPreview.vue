<template>
  <div v-if="sheets.length > 0" class="schema-preview fade-in">
    <div v-for="sheet in localSheets" :key="sheet.name" class="schema-sheet">
      <div class="schema-sheet-header" @click="sheet.expanded = !sheet.expanded">
        <i :class="['fas', sheet.expanded ? 'fa-chevron-down' : 'fa-chevron-right']"></i>
        <strong>{{ sheet.name }}</strong>
        <span class="text-muted">({{ sheet.fields.length }} fields)</span>

        <select
          v-if="editable"
          class="cardinality-select"
          :value="sheet.cardinality || 'one_per_study'"
          @change="onCardinalityChange(sheet, ($event.target as HTMLSelectElement).value)"
          @click.stop
        >
          <option value="one_per_study">One per study</option>
          <option value="many_per_study">Many per study</option>
        </select>
        <span v-else-if="sheet.cardinality" class="badge-cardinality">
          {{ sheet.cardinality === 'many_per_study' ? 'Many/study' : 'One/study' }}
        </span>
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
            <td>
              <span>{{ field.name }}</span>
              <span v-if="field.description && editable" class="field-desc">{{ field.description }}</span>
            </td>
            <td><span class="badge-type">{{ field.field_type }}</span></td>
            <td>
              <select
                v-if="editable"
                class="role-select"
                :value="field.role"
                @change="onFieldChange(sheet, field, 'role', ($event.target as HTMLSelectElement).value)"
              >
                <option value="extract">extract</option>
                <option value="auto_calc">auto_calc</option>
                <option value="lookup">lookup</option>
                <option value="override">override</option>
                <option value="metadata">metadata</option>
                <option value="qc_flag">qc_flag</option>
              </select>
              <span v-else class="badge-role">{{ field.role }}</span>
            </td>
            <td>
              <input
                v-if="editable"
                type="checkbox"
                :checked="field.required"
                @change="onFieldChange(sheet, field, 'required', ($event.target as HTMLInputElement).checked)"
              />
              <template v-else>
                <i v-if="field.required" class="fas fa-check" style="color: #16a34a;"></i>
                <span v-else class="text-muted">--</span>
              </template>
            </td>
            <td>
              <span v-if="field.semantic_tag" class="badge-tag">{{ field.semantic_tag }}</span>
              <span v-else class="text-muted">--</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="editable && isDirty" class="save-bar">
      <span class="save-hint">Unsaved changes</span>
      <button class="btn-save" :disabled="saving" @click="saveChanges">
        <i v-if="saving" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-save"></i>
        {{ saving ? 'Saving...' : 'Save Schema' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'

export interface SchemaField {
  name: string
  field_type: string
  role: string
  required: boolean
  semantic_tag?: string
  description?: string
}

export interface SchemaSheet {
  name: string
  fields: SchemaField[]
  expanded: boolean
  role?: string
  cardinality?: string
  extraction_order?: number
}

const props = defineProps<{
  sheets: SchemaSheet[]
  sessionId?: string
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'schema-saved'): void
}>()

const localSheets = ref<SchemaSheet[]>([])
const saving = ref(false)

const pendingPatches = ref<Record<string, Record<string, any>>>({})
const isDirty = computed(() => Object.keys(pendingPatches.value).length > 0)

watch(
  () => props.sheets,
  (val) => {
    localSheets.value = val.map((s) => ({ ...s, expanded: s.expanded ?? false }))
    pendingPatches.value = {}
  },
  { immediate: true }
)

function onCardinalityChange(sheet: SchemaSheet, value: string) {
  sheet.cardinality = value
  if (!pendingPatches.value[sheet.name]) {
    pendingPatches.value[sheet.name] = {}
  }
  pendingPatches.value[sheet.name].cardinality = value
  pendingPatches.value = { ...pendingPatches.value }
}

function onFieldChange(
  sheet: SchemaSheet,
  field: SchemaField,
  prop: 'role' | 'required' | 'description' | 'field_type',
  value: string | boolean
) {
  ;(field as any)[prop] = value
  if (!pendingPatches.value[sheet.name]) {
    pendingPatches.value[sheet.name] = {}
  }
  if (!pendingPatches.value[sheet.name].fields) {
    pendingPatches.value[sheet.name].fields = {}
  }
  if (!pendingPatches.value[sheet.name].fields[field.name]) {
    pendingPatches.value[sheet.name].fields[field.name] = {}
  }
  pendingPatches.value[sheet.name].fields[field.name][prop] = value
  pendingPatches.value = { ...pendingPatches.value }
}

async function saveChanges() {
  if (!props.sessionId || !isDirty.value) return
  saving.value = true

  try {
    const resp = await fetch(
      `/api/extraction/v3/sessions/${props.sessionId}/schema`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sheets: pendingPatches.value }),
      }
    )
    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail || 'Failed to save schema')
    }
    pendingPatches.value = {}
    emit('schema-saved')
  } catch (e: any) {
    alert(`Schema save failed: ${e.message}`)
  } finally {
    saving.value = false
  }
}
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

.cardinality-select {
  margin-left: auto;
  font-size: 0.75rem;
  padding: 0.15rem 0.4rem;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  background: white;
  cursor: pointer;
}

.badge-cardinality {
  margin-left: auto;
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
  background: #ede9fe;
  color: #6d28d9;
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

.field-desc {
  display: block;
  font-size: 0.7rem;
  color: #9ca3af;
  margin-top: 0.1rem;
}

.role-select {
  font-size: 0.75rem;
  padding: 0.1rem 0.25rem;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  background: #fffbeb;
  cursor: pointer;
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

.save-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 0.5rem 0;
  margin-top: 0.5rem;
}

.save-hint {
  font-size: 0.75rem;
  color: #f59e0b;
}

.btn-save {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: white;
  background: #2563eb;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-save:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
