import React, { useState, useCallback, useEffect } from 'react'
import AppShell from './components/layout/AppShell.jsx'
import LoginPage from './components/LoginPage.jsx'
import Dashboard from './components/Dashboard.jsx'
import ReviewPage from './components/ReviewPage.jsx'
import TocAnnotator from './components/TocAnnotator.jsx'
import AnnotationWorkflow from './components/annotation-workflow/AnnotationWorkflow.jsx'
import ElementBrowserTabs from './components/element-browser/ElementBrowserTabs.jsx'
import TagLogPage from './components/TagLogPage.jsx'
import DocumentsPage from './components/DocumentsPage.jsx'
import OntologyPage from './components/OntologyPage.jsx'
import GroundTruthPage from './components/GroundTruthPage.jsx'
import DocumentEdgesPage from './components/DocumentEdgesPage.jsx'
import TrainingPage from './components/TrainingPage.jsx'
import PdfPane from './components/PdfPane.jsx'
import SearchBar from './components/SearchBar.jsx'
import { useStats, useDocuments, useConcept, useConceptPages } from './api.js'
import { useAuth } from './auth.jsx'
import { useNavigation } from './lib/hooks/useNavigation.jsx'

function PageContent() {
  const { view, navigate, params } = useNavigation()
  const [selectedId, setSelectedId] = useState(null)
  const [activeDoc, setActiveDoc] = useState(null)
  const [pdfPage, setPdfPage] = useState(1)

  const { data: stats } = useStats()
  const { data: documents = [] } = useDocuments()
  const { data: selected } = useConcept(selectedId)
  const { data: conceptPages = [] } = useConceptPages(selectedId)

  useEffect(() => {
    if (!activeDoc && documents.length > 0) {
      const first = documents.find(d => d.has_pdf)
      if (first) setActiveDoc(first.id)
    }
  }, [documents, activeDoc])

  useEffect(() => {
    if (!selected || !conceptPages.length) return
    const match = conceptPages.find(p => p.doc_id === activeDoc)
    if (match) {
      setPdfPage(match.page)
    } else {
      const docWithPdf = conceptPages.find(p => documents.find(d => d.id === p.doc_id && d.has_pdf))
      if (docWithPdf) {
        setActiveDoc(docWithPdf.doc_id)
        setPdfPage(docWithPdf.page)
      }
    }
  }, [selected, conceptPages])

  const selectConcept = useCallback((conceptId) => {
    setSelectedId(conceptId)
  }, [])

  const onSearchSelect = useCallback((result) => {
    selectConcept(result.id)
  }, [selectConcept])

  const onDocChange = useCallback((docId) => {
    setActiveDoc(docId)
    if (selected) {
      const match = conceptPages.find(p => p.doc_id === docId)
      if (match) setPdfPage(match.page)
      else setPdfPage(1)
    }
  }, [selected, conceptPages])

  switch (view) {
    case 'dashboard':
      return <Dashboard />

    case 'review':
      return (
        <div className="flex flex-col flex-1 h-full overflow-hidden">
          <ReviewPage documents={documents} onBack={() => navigate('dashboard')} />
        </div>
      )

    case 'annotate':
      return (
        <div className="flex flex-col flex-1 h-full overflow-hidden">
          <AnnotationWorkflow initialDocId={params.docId || null} />
        </div>
      )

    case 'annotate-legacy':
      return (
        <div className="flex flex-col flex-1 h-full overflow-hidden">
          <TocAnnotator onBack={() => navigate('dashboard')} />
        </div>
      )

    case 'documents':
      return <DocumentsPage />

    case 'elements':
      return <ElementBrowserTabs />

    case 'tag-log':
      return <TagLogPage />

    case 'ontology':
      return <OntologyPage />

    case 'ground-truth':
      return <GroundTruthPage />

    case 'edges':
      return <DocumentEdgesPage />

    case 'training':
      return <TrainingPage />

    default:
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <PdfPane
            documents={documents}
            activeDoc={activeDoc}
            page={pdfPage}
            conceptPages={conceptPages}
            selected={selected}
            onDocChange={onDocChange}
            onPageClick={(docId, page) => { setActiveDoc(docId); setPdfPage(page) }}
          />
        </div>
      )
  }
}

export default function App() {
  const { user, loading: authLoading } = useAuth()

  if (authLoading) return <div className="text-muted-foreground p-10 bg-background h-screen">Loading...</div>
  if (!user) return <LoginPage />

  return (
    <AppShell>
      <PageContent />
    </AppShell>
  )
}
