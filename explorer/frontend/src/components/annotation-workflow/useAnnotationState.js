import { useReducer, useEffect, useRef, useCallback } from 'react'
import { useSaveTransitions, useAnnotateToc } from '../../api.js'

// ── Actions ──────────────────────────────────────────────
const ADD_TRANSITION = 'ADD_TRANSITION'
const REMOVE_TRANSITION = 'REMOVE_TRANSITION'
const UPDATE_TRANSITION = 'UPDATE_TRANSITION'
const SET_PAGE = 'SET_PAGE'
const LOAD = 'LOAD'
const MARK_SAVED = 'MARK_SAVED'
const MERGE_PROVISIONAL = 'MERGE_PROVISIONAL'
const TOGGLE_MULTI_TAG = 'TOGGLE_MULTI_TAG'

function reducer(state, action) {
  switch (action.type) {
    case LOAD:
      return {
        ...state,
        transitions: action.transitions || [],
        multiTags: action.multiTags || [],
        hasToc: action.hasToc ?? state.hasToc,
        tocPages: action.tocPages ?? state.tocPages,
        dirty: false,
        changeCount: 0,
      }

    case ADD_TRANSITION: {
      const t = action.transition
      // Replace if same page already has a transition
      const filtered = state.transitions.filter(x => x.page !== t.page)
      const next = [...filtered, t].sort((a, b) => a.page - b.page)
      return { ...state, transitions: next, dirty: true, changeCount: state.changeCount + 1 }
    }

    case REMOVE_TRANSITION: {
      const next = state.transitions.filter(t => t.page !== action.page)
      return { ...state, transitions: next, dirty: true, changeCount: state.changeCount + 1 }
    }

    case UPDATE_TRANSITION: {
      const next = state.transitions.map(t =>
        t.page === action.page ? { ...t, ...action.updates } : t
      )
      return { ...state, transitions: next, dirty: true, changeCount: state.changeCount + 1 }
    }

    case SET_PAGE:
      return { ...state, selectedPage: action.page }

    case MERGE_PROVISIONAL: {
      // Merge detected markers without overwriting existing manual/validated transitions
      const existingPages = new Set(state.transitions.map(t => t.page))
      const newMarkers = (action.markers || []).filter(m => !existingPages.has(m.page))
      if (newMarkers.length === 0) return state
      const next = [...state.transitions, ...newMarkers].sort((a, b) => a.page - b.page)
      return { ...state, transitions: next, dirty: true }
    }

    case TOGGLE_MULTI_TAG: {
      const { page, section_type } = action
      const existing = state.multiTags.find(
        mt => mt.page === page && mt.section_type === section_type
      )
      const next = existing
        ? state.multiTags.filter(mt => !(mt.page === page && mt.section_type === section_type))
        : [...state.multiTags, { page, section_type }]
      return { ...state, multiTags: next, dirty: true, changeCount: state.changeCount + 1 }
    }

    case MARK_SAVED:
      return { ...state, dirty: false }

    default:
      return state
  }
}

const initialState = {
  transitions: [],
  multiTags: [],
  selectedPage: 1,
  dirty: false,
  hasToc: null,
  tocPages: [],
  changeCount: 0,
}

export function useAnnotationState(docId) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const saveTimer = useRef(null)
  const saveMutation = useSaveTransitions(docId)
  const { data: tocData, isLoading } = useAnnotateToc(docId)

  // Load transitions when doc data arrives
  useEffect(() => {
    if (!tocData) return
    // Prefer v2 format if available (returned as ground_truth_v2 by the API)
    const v2 = tocData.ground_truth_v2
    if (v2 && v2.version === 2 && (v2.transitions?.length > 0 || v2.multi_tags?.length > 0)) {
      dispatch({
        type: LOAD,
        transitions: v2.transitions || [],
        multiTags: v2.multi_tags || [],
        hasToc: v2.has_toc,
        tocPages: v2.toc_pages || [],
      })
      return
    }
    // Fall back to v1 ground_truth
    const gt = tocData.ground_truth
    if (!gt) return
    const transitions = (gt.sections || [])
      .sort((a, b) => a.start_page - b.start_page)
      .map(s => ({
        page: s.start_page,
        section_type: s.statement_type,
        label: s.label || '',
        note_number: s.note_number || null,
        source: 'manual',
        validated: s.validated || false,
      }))
    dispatch({
      type: LOAD,
      transitions,
      hasToc: gt.has_toc,
      tocPages: gt.toc_pages || [],
    })
  }, [tocData])

  // Auto-save with 2s debounce
  useEffect(() => {
    if (!state.dirty || !docId) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      saveMutation.mutate({ transitions: state.transitions, multi_tags: state.multiTags }, {
        onSuccess: () => dispatch({ type: MARK_SAVED }),
      })
    }, 2000)
    return () => clearTimeout(saveTimer.current)
  }, [state.dirty, state.transitions, docId])

  // Flush on unmount
  useEffect(() => {
    return () => {
      clearTimeout(saveTimer.current)
    }
  }, [])

  const addTransition = useCallback((transition) => {
    dispatch({ type: ADD_TRANSITION, transition })
  }, [])

  const removeTransition = useCallback((page) => {
    dispatch({ type: REMOVE_TRANSITION, page })
  }, [])

  const updateTransition = useCallback((page, updates) => {
    dispatch({ type: UPDATE_TRANSITION, page, updates })
  }, [])

  const setPage = useCallback((page) => {
    dispatch({ type: SET_PAGE, page })
  }, [])

  const mergeProvisional = useCallback((markers) => {
    dispatch({ type: MERGE_PROVISIONAL, markers })
  }, [])

  const toggleMultiTag = useCallback((page, section_type) => {
    dispatch({ type: TOGGLE_MULTI_TAG, page, section_type })
  }, [])

  const saveNow = useCallback(() => {
    if (!docId || state.transitions.length === 0) return
    clearTimeout(saveTimer.current)
    saveMutation.mutate({ transitions: state.transitions, multi_tags: state.multiTags }, {
      onSuccess: () => dispatch({ type: MARK_SAVED }),
    })
  }, [state.transitions, state.multiTags, docId])

  return {
    ...state,
    isLoading,
    isSaving: saveMutation.isPending,
    addTransition,
    removeTransition,
    updateTransition,
    mergeProvisional,
    toggleMultiTag,
    setPage,
    saveNow,
    dispatch,
  }
}
