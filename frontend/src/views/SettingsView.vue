<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Settings</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Configure API keys and view available models</p>

    <!-- API Keys -->
    <div class="glass-card">
      <div class="section-title">API Keys</div>
      <div v-if="saveSuccess" class="alert alert-success">✓ Settings saved successfully</div>
      <div v-if="saveError" class="alert alert-danger">{{ saveError }}</div>

      <div class="form-group">
        <label class="form-label">OpenRouter API Key</label>
        <div style="display: flex; gap: 0.5rem;">
          <input
            v-model="settings.openrouter_api_key"
            :type="showOpenRouter ? 'text' : 'password'"
            class="form-control"
            placeholder="sk-or-..."
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showOpenRouter = !showOpenRouter" style="white-space: nowrap;">
            {{ showOpenRouter ? '🙈 Hide' : '👁 Show' }}
          </button>
          <button class="btn btn-secondary btn-sm" :disabled="testingOR" @click="testKey('openrouter')" style="white-space: nowrap;">
            <span v-if="testingOR">⏳</span>
            <span v-else>Test</span>
          </button>
        </div>
        <div v-if="orTestResult" class="text-muted" style="margin-top: 0.25rem; font-size: 0.8rem;" :class="orTestOk ? 'text-success' : 'text-danger'">
          {{ orTestResult }}
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Together AI API Key</label>
        <div style="display: flex; gap: 0.5rem;">
          <input
            v-model="settings.together_api_key"
            :type="showTogether ? 'text' : 'password'"
            class="form-control"
            placeholder="..."
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showTogether = !showTogether" style="white-space: nowrap;">
            {{ showTogether ? '🙈 Hide' : '👁 Show' }}
          </button>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="saving" @click="doSave">
        <span v-if="saving">⏳ Saving…</span>
        <span v-else>💾 Save Settings</span>
      </button>
    </div>

    <!-- Available Models -->
    <div class="glass-card">
      <div class="section-title">Available Models</div>
      <div v-if="loadingModels" class="text-muted" style="padding: 1rem 0;">Loading models…</div>
      <div v-else style="display: flex; flex-direction: column; gap: 0.75rem;">
        <div
          v-for="m in models"
          :key="m.model_id"
          class="glass-section"
          style="margin-bottom: 0; display: flex; align-items: flex-start; gap: 1rem;"
        >
          <div style="font-size: 1.5rem;">🤖</div>
          <div style="flex: 1;">
            <div style="font-weight: 600; color: var(--text-primary);">{{ m.display_name || m.model_id }}</div>
            <div class="text-muted" style="font-size: 0.8rem;">
              {{ m.provider }} · {{ m.parameters || '' }} · License: {{ m.license || 'unknown' }}
            </div>
          </div>
          <div>
            <span class="badge badge-include">active</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Inference Config -->
    <div class="glass-card">
      <div class="section-title">Inference Configuration</div>
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.5rem;">
        <span class="badge badge-unclear">temperature = 0.0</span>
        <span class="badge badge-unclear">seed = 42</span>
        <span class="badge badge-unclear">timeout = 120s</span>
        <span class="badge badge-unclear">max_retries = 3</span>
      </div>
      <p class="text-muted" style="margin-top: 1rem; font-size: 0.85rem;">
        All inference parameters are fixed for reproducibility (TRIPOD-LLM compliance).
        Temperature=0.0 ensures deterministic outputs.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiGet, apiPut, apiPost } from '@/api'

interface Settings {
  openrouter_api_key?: string
  together_api_key?: string
}

interface ModelInfo {
  model_id: string
  display_name?: string
  provider?: string
  parameters?: string
  license?: string
}

const settings = ref<Settings>({})
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')
const showOpenRouter = ref(false)
const showTogether = ref(false)

const testingOR = ref(false)
const orTestResult = ref('')
const orTestOk = ref(false)

const models = ref<ModelInfo[]>([])
const loadingModels = ref(true)

onMounted(async () => {
  try {
    settings.value = await apiGet<Settings>('/settings')
  } catch { /* no settings yet */ }
  try {
    const data = await apiGet<{ models: ModelInfo[] }>('/settings/models')
    models.value = data.models || []
  } catch { /* no models */ }
  loadingModels.value = false
})

async function doSave() {
  saving.value = true
  saveSuccess.value = false
  saveError.value = ''
  try {
    await apiPut('/settings', settings.value)
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (e: unknown) {
    saveError.value = `Save failed: ${(e as Error).message}`
  } finally {
    saving.value = false
  }
}

async function testKey(provider: string) {
  testingOR.value = true
  orTestResult.value = ''
  try {
    const data = await apiPost<{ ok: boolean; message: string }>('/settings/test-key', {
      provider,
      api_key: provider === 'openrouter' ? settings.value.openrouter_api_key : settings.value.together_api_key,
    })
    orTestOk.value = data.ok
    orTestResult.value = data.message
  } catch (e: unknown) {
    orTestOk.value = false
    orTestResult.value = `Test failed: ${(e as Error).message}`
  } finally {
    testingOR.value = false
  }
}
</script>
