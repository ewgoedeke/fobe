import { createContext, useContext, useState, useCallback } from 'react'

const NavigationContext = createContext(null)

const VIEW_LABELS = {
  dashboard: 'Dashboard',
  documents: 'Documents',
  elements: 'Element Browser',
  ontology: 'Ontology',
  edges: 'Document Edges',
  'ground-truth': 'Ground Truth',
  review: 'Review',
  annotate: 'Annotate',
  training: 'Training',
  'tag-log': 'Tag Log',
  activity: 'Activity',
}

export function NavigationProvider({ children }) {
  const [view, setView] = useState('dashboard')
  const [params, setParams] = useState({})

  const navigate = useCallback((target, navParams = {}) => {
    setView(target)
    setParams(navParams)
  }, [])

  const breadcrumbs = [
    { label: VIEW_LABELS[view] || view, view }
  ]

  return (
    <NavigationContext.Provider value={{ view, navigate, params, breadcrumbs, VIEW_LABELS }}>
      {children}
    </NavigationContext.Provider>
  )
}

export function useNavigation() {
  const ctx = useContext(NavigationContext)
  if (!ctx) throw new Error('useNavigation must be used within NavigationProvider')
  return ctx
}
