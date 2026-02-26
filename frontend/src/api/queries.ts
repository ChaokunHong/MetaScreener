import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from './client.ts'
import type {
  SettingsResponse,
  ModelInfo,
  TestKeyResponse,
  ScreeningResultsResponse,
  EvaluationResponse,
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

export function useEvaluationResults(sessionId: string | null) {
  return useQuery({
    queryKey: ['evaluation-results', sessionId],
    queryFn: () =>
      apiGet<EvaluationResponse>(`/evaluation/results/${sessionId}`),
    enabled: !!sessionId,
  })
}
