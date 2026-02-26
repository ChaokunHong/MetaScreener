import { create } from 'zustand'

interface ScreeningState {
  sessionId: string | null
  recordCount: number
  filename: string | null
  isScreening: boolean
  progress: number
  setSession: (sessionId: string, recordCount: number, filename: string) => void
  setScreening: (isScreening: boolean) => void
  setProgress: (progress: number) => void
  reset: () => void
}

export const useScreeningStore = create<ScreeningState>((set) => ({
  sessionId: null,
  recordCount: 0,
  filename: null,
  isScreening: false,
  progress: 0,
  setSession: (sessionId, recordCount, filename) =>
    set({ sessionId, recordCount, filename }),
  setScreening: (isScreening) => set({ isScreening }),
  setProgress: (progress) => set({ progress }),
  reset: () =>
    set({
      sessionId: null,
      recordCount: 0,
      filename: null,
      isScreening: false,
      progress: 0,
    }),
}))
