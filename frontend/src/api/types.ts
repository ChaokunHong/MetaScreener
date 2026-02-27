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

export interface ScreeningSessionInfo {
  session_id: string
  filename: string
  total_records: number
  completed_records: number
  has_criteria: boolean
  created_at?: string | null
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

export interface EvaluationROCPoint {
  fpr: number
  tpr: number
}

export interface EvaluationCalibrationPoint {
  predicted: number
  actual: number
}

export interface EvaluationDistributionBin {
  bin: string
  include: number
  exclude: number
}

export interface EvaluationCharts {
  roc: EvaluationROCPoint[]
  calibration: EvaluationCalibrationPoint[]
  distribution: EvaluationDistributionBin[]
}

export interface EvaluationUploadResponse {
  session_id: string
  total_records?: number
  gold_label_count?: number
  label_count?: number
  filename?: string
}

export interface EvaluationResponse {
  session_id: string
  metrics: EvaluationMetrics
  total_records: number
  gold_label_count: number
  charts?: EvaluationCharts | null
  screening_session_id?: string | null
}

export interface ExtractionUploadResponse {
  session_id: string
  pdf_count: number
}

export interface ExtractionResultsResponse {
  session_id: string
  results: Record<string, unknown>[]
}

export interface QualityUploadResponse {
  session_id: string
  pdf_count: number
}

export interface QualityResultsResponse {
  session_id: string
  tool: string
  results: Record<string, unknown>[]
}
