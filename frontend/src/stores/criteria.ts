/**
 * Simple reactive store for sharing criteria state between CriteriaView and ScreeningView.
 * Persists to localStorage so criteria survive page navigation.
 */
import { reactive, toRefs } from 'vue'

export interface CriteriaElements {
  [key: string]: { name?: string; include: string[]; exclude: string[] }
}

export interface SavedCriteria {
  framework: string
  research_question?: string
  detected_language?: string
  elements: CriteriaElements
  study_design_include?: string[]
  study_design_exclude?: string[]
  publication_type_exclude?: string[]
  language_restriction?: string[] | null
  date_from?: string | null
  date_to?: string | null
}

const STORAGE_KEY = 'metascreener_criteria'
const TOPIC_KEY = 'metascreener_criteria_topic'

function loadFromStorage(): SavedCriteria | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function loadTopic(): string {
  return localStorage.getItem(TOPIC_KEY) || ''
}

const state = reactive({
  criteria: loadFromStorage() as SavedCriteria | null,
  topic: loadTopic(),
})

export function useCriteriaStore() {
  function setCriteria(c: SavedCriteria) {
    state.criteria = c
    localStorage.setItem(STORAGE_KEY, JSON.stringify(c))
  }

  function setTopic(t: string) {
    state.topic = t
    localStorage.setItem(TOPIC_KEY, t)
  }

  function clearCriteria() {
    state.criteria = null
    state.topic = ''
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(TOPIC_KEY)
  }

  return {
    ...toRefs(state),
    setCriteria,
    setTopic,
    clearCriteria,
  }
}
