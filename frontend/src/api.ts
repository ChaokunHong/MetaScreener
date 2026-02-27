import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export async function apiGet<T>(path: string): Promise<T> {
  const { data } = await api.get<T>(path)
  return data
}

export async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const { data } = await api.post<T>(path, payload)
  return data
}

export async function apiPut<T>(path: string, payload?: unknown): Promise<T> {
  const { data } = await api.put<T>(path, payload)
  return data
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const { data } = await api.post<T>(path, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export function decisionBadgeClass(decision: string): string {
  switch (decision) {
    case 'INCLUDE': return 'badge badge-include'
    case 'EXCLUDE': return 'badge badge-exclude'
    case 'HUMAN_REVIEW': return 'badge badge-review'
    default: return 'badge badge-unclear'
  }
}

export function fmtScore(v: unknown): string {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(2)
}
