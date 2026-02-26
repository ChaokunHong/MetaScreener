export interface APIKeysConfig {
  openrouter: string
  together: string
}

export interface InferenceSettings {
  temperature: number
  seed: number
  timeout_s: number
  max_retries: number
}

export interface SettingsResponse {
  api_keys: APIKeysConfig
  inference: InferenceSettings
  enabled_models: string[]
}

export interface ModelInfo {
  model_id: string
  name: string
  provider: string
  version: string
  license: string
  enabled: boolean
}

export interface TestKeyResponse {
  valid: boolean
  message: string
}

export interface UploadResponse {
  session_id: string
  record_count: number
  filename: string
}

export interface ScreeningRecordSummary {
  record_id: string
  title: string
  decision: string
  tier: string
  score: number
  confidence: number
}

export interface ScreeningResultsResponse {
  session_id: string
  total: number
  completed: number
  results: ScreeningRecordSummary[]
}

export interface EvaluationMetrics {
  sensitivity: number | null
  specificity: number | null
  f1: number | null
  wss_at_95: number | null
  auroc: number | null
  ece: number | null
  brier: number | null
  kappa: number | null
}

export interface EvaluationResponse {
  session_id: string
  metrics: EvaluationMetrics
  total_records: number
  gold_label_count: number
}
