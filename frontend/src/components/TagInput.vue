<template>
  <div class="tag-input-wrap">
    <div class="tag-list" v-if="modelValue.length">
      <span v-for="tag in modelValue" :key="tag" class="tag-chip">
        {{ tag }}
        <button class="tag-remove" @click="removeTag(tag)" type="button">
          <i class="fas fa-times"></i>
        </button>
      </span>
    </div>

    <div class="tag-suggestions" v-if="unusedSuggestions.length">
      <span class="tag-suggestions-label">Suggestions:</span>
      <button
        v-for="s in unusedSuggestions"
        :key="s"
        class="tag-suggestion-btn"
        @click="addTag(s)"
        type="button"
      >+ {{ s }}</button>
    </div>

    <div class="tag-free-input">
      <input
        v-model="inputValue"
        :placeholder="placeholder"
        class="form-control form-control-sm"
        @keydown.enter.prevent="addFromInput"
      />
      <button
        class="btn btn-secondary btn-sm"
        @click="addFromInput"
        :disabled="!inputValue.trim()"
        type="button"
      >Add</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string[]
  suggestions?: string[]
  placeholder?: string
}>(), {
  suggestions: () => [],
  placeholder: 'Type a tag and press Enter',
})

const emit = defineEmits<{
  'update:modelValue': [tags: string[]]
}>()

const inputValue = ref('')

const unusedSuggestions = computed(() =>
  props.suggestions.filter(s => !props.modelValue.includes(s))
)

function addTag(tag: string) {
  const normalized = tag.trim().toLowerCase()
  if (normalized && !props.modelValue.includes(normalized)) {
    emit('update:modelValue', [...props.modelValue, normalized])
  }
}

function removeTag(tag: string) {
  emit('update:modelValue', props.modelValue.filter(t => t !== tag))
}

function addFromInput() {
  const val = inputValue.value.trim()
  if (val) {
    addTag(val)
    inputValue.value = ''
  }
}
</script>

<style scoped>
.tag-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.78rem;
  background: rgba(139, 92, 246, 0.15);
  color: var(--primary-purple, #8b5cf6);
  border: 1px solid rgba(139, 92, 246, 0.3);
}
.tag-remove {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0;
  font-size: 0.65rem;
  opacity: 0.6;
}
.tag-remove:hover { opacity: 1; }
.tag-suggestions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
}
.tag-suggestions-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #999);
}
.tag-suggestion-btn {
  background: rgba(255,255,255,0.05);
  border: 1px dashed rgba(255,255,255,0.15);
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary, #999);
  cursor: pointer;
  transition: all 0.15s;
}
.tag-suggestion-btn:hover {
  background: rgba(139, 92, 246, 0.1);
  border-color: rgba(139, 92, 246, 0.3);
  color: var(--primary-purple, #8b5cf6);
}
.tag-free-input {
  display: flex;
  gap: 0.4rem;
}
.tag-free-input input {
  flex: 1;
}
</style>
