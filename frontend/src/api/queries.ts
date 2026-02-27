import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from './client.ts'
import type {
  SettingsResponse,
  ModelInfo,
  TestKeyResponse,
  ScreeningResultsResponse,
  ScreeningSessionInfo,
  EvaluationResponse,
  ExtractionResultsResponse,
  QualityResultsResponse,
} from './types.ts'

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet<SettingsResponse>('/settings'),
  })
}

export function useModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: () => apiGet<ModelInfo[]>('/settings/models'),
  })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<SettingsResponse>) =>
      apiPut<SettingsResponse>('/settings', data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}

export function useTestKey() {
  return useMutation({
    mutationFn: (data: { provider: string; api_key: string }) =>
      apiPost<TestKeyResponse>('/settings/test-key', data),
  })
}

export function useScreeningResults(sessionId: string | null) {
  return useQuery({
    queryKey: ['screening-results', sessionId],
    queryFn: () =>
      apiGet<ScreeningResultsResponse>(`/screening/results/${sessionId}`),
    enabled: !!sessionId,
  })
}

export function useScreeningSessions() {
  return useQuery({
    queryKey: ['screening-sessions'],
    queryFn: () => apiGet<ScreeningSessionInfo[]>('/screening/sessions'),
  })
}

export function useEvaluationResults(sessionId: string | null) {
  return useQuery({
    queryKey: ['evaluation-results', sessionId],
    queryFn: () =>
      apiGet<EvaluationResponse>(`/evaluation/results/${sessionId}`),
    enabled: !!sessionId,
  })
}

export function useExtractionResults(sessionId: string | null) {
  return useQuery({
    queryKey: ['extraction-results', sessionId],
    queryFn: () =>
      apiGet<ExtractionResultsResponse>(`/extraction/results/${sessionId}`),
    enabled: !!sessionId,
  })
}

export function useQualityResults(sessionId: string | null) {
  return useQuery({
    queryKey: ['quality-results', sessionId],
    queryFn: () =>
      apiGet<QualityResultsResponse>(`/quality/results/${sessionId}`),
    enabled: !!sessionId,
  })
}
