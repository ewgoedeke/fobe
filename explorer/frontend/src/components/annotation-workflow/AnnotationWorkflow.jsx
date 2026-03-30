import { useState, useMemo, useCallback, useEffect } from 'react'
import { Allotment } from 'allotment'
import { cn } from '@/lib/utils'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Badge } from '../ui/badge.jsx'
import { Skeleton } from '../ui/skeleton.jsx'
import { Save, Loader2, Search } from 'lucide-react'
import { useAnnotateDocuments, useAnnotateToc, usePageFeatures } from '../../api.js'
import { useAnnotationState } from './useAnnotationState.js'
import { resolveTransitions, buildHierarchyGroups } from './resolveTransitions.js'
import { CoverageStrip } from './CoverageStrip.jsx'
import { HierarchyOutline } from './HierarchyOutline.jsx'
import { PageStripGallery } from './PageStripGallery.jsx'
import { PageDetail } from './PageDetail.jsx'

export default function AnnotationWorkflow({ initialDocId }) {
  const [docId, setDocId] = useState(initialDocId || null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearch, setShowSearch] = useState(!initialDocId)

  const { data: documents = [], isLoading: docsLoading } = useAnnotateDocuments()
  const { data: tocData } = useAnnotateToc(docId)
  const { data: pageFeatures } = usePageFeatures(docId)

  const totalPages = tocData?.page_count || 0
  const pageDims = tocData?.page_dims || {}
  const gaap = tocData?.gaap || ''

  const {
    transitions,
    selectedPage,
    dirty,
    isLoading: stateLoading,
    isSaving,
    addTransition,
    removeTransition,
    updateTransition,
    setPage,
    saveNow,
  } = useAnnotationState(docId)

  // Resolve transitions → page map
  const pageMap = useMemo(
    () => resolveTransitions(transitions, totalPages),
    [transitions, totalPages],
  )

  // Build hierarchy groups for outline
  const groups = useMemo(
    () => buildHierarchyGroups(pageMap, transitions),
    [pageMap, transitions],
  )

  // Find current transition for selected page
  const currentTransition = useMemo(
    () => transitions.find(t => t.page === selectedPage) || null,
    [transitions, selectedPage],
  )

  // Filtered doc list for search
  const filteredDocs = useMemo(() => {
    if (!searchQuery) return documents
    const q = searchQuery.toLowerCase()
    return documents.filter(d => d.doc_id.toLowerCase().includes(q))
  }, [documents, searchQuery])

  const selectDoc = useCallback((id) => {
    setDocId(id)
    setShowSearch(false)
    setSearchQuery('')
  }, [])

  // Reset page when doc changes
  useEffect(() => {
    setPage(1)
  }, [docId])

  const handlePageClick = useCallback((page) => {
    setPage(page)
  }, [setPage])

  const isLoading = stateLoading || docsLoading

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background text-foreground">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border shrink-0 h-10">
        {/* Document search / selector */}
        <div className="relative w-72">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <Input
            className="h-8 pl-7 text-xs"
            placeholder="Search document..."
            value={showSearch ? searchQuery : (docId || '')}
            onChange={e => { setSearchQuery(e.target.value); setShowSearch(true) }}
            onFocus={() => setShowSearch(true)}
          />
          {showSearch && (
            <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-64 overflow-y-auto rounded-md border border-border bg-popover shadow-md">
              {filteredDocs.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">No documents found</div>
              ) : (
                filteredDocs.slice(0, 20).map(d => (
                  <button
                    key={d.doc_id}
                    className={cn(
                      'w-full text-left px-3 py-1.5 text-xs hover:bg-accent flex items-center gap-2',
                      d.doc_id === docId && 'bg-accent',
                    )}
                    onClick={() => selectDoc(d.doc_id)}
                  >
                    <span className="truncate flex-1">{d.doc_id}</span>
                    <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                      {d.page_count || 0}p
                    </span>
                    {d.gaap && (
                      <span className="text-[10px] text-muted-foreground shrink-0">{d.gaap}</span>
                    )}
                    {d.has_ground_truth && (
                      <span className="size-1.5 rounded-full bg-green-500 shrink-0" title="Has GT" />
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Doc info */}
        {docId && (
          <>
            <span className="text-sm font-semibold truncate max-w-[200px]">{docId}</span>
            {gaap && <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{gaap}</Badge>}
            {totalPages > 0 && (
              <span className="text-[11px] text-muted-foreground tabular-nums">{totalPages}p</span>
            )}
          </>
        )}

        {/* Status + save */}
        <div className="ml-auto flex items-center gap-2">
          {dirty && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-yellow-500/15 text-yellow-500">
              Unsaved
            </Badge>
          )}
          {isSaving && (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
          )}
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={saveNow}
            disabled={!dirty || isSaving}
          >
            <Save className="size-3" />
            Save
          </Button>
        </div>
      </div>

      {/* Close search dropdown on outside click */}
      {showSearch && (
        <div className="fixed inset-0 z-40" onClick={() => setShowSearch(false)} />
      )}

      {/* Coverage strip */}
      {docId && totalPages > 0 && (
        <div className="px-4 py-1 border-b border-border shrink-0">
          <CoverageStrip
            totalPages={totalPages}
            pageMap={pageMap}
            selectedPage={selectedPage}
            onPageClick={handlePageClick}
          />
        </div>
      )}

      {/* Main 3-pane layout */}
      {!docId ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
          Select a document to begin annotation
        </div>
      ) : isLoading ? (
        <div className="flex-1 flex gap-4 p-4">
          <div className="w-48 flex flex-col gap-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-6 w-full" />)}
          </div>
          <div className="flex-1 flex flex-wrap gap-3">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-32 w-40 rounded" />)}
          </div>
          <div className="w-80">
            <Skeleton className="h-96 w-full rounded" />
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <Allotment>
            {/* Left: Hierarchy outline */}
            <Allotment.Pane minSize={160} preferredSize={200} maxSize={280}>
              <HierarchyOutline
                groups={groups}
                selectedPage={selectedPage}
                onPageClick={handlePageClick}
              />
            </Allotment.Pane>

            {/* Center: Page gallery */}
            <Allotment.Pane minSize={300}>
              <PageStripGallery
                docId={docId}
                totalPages={totalPages}
                pageMap={pageMap}
                pageFeatures={pageFeatures}
                selectedPage={selectedPage}
                onPageClick={handlePageClick}
              />
            </Allotment.Pane>

            {/* Right: Page detail */}
            <Allotment.Pane minSize={280} preferredSize={400} maxSize={500}>
              <PageDetail
                docId={docId}
                pageNo={selectedPage}
                pageDims={pageDims}
                pageMap={pageMap}
                pageFeatures={pageFeatures}
                transition={currentTransition}
                onAddTransition={addTransition}
                onRemoveTransition={removeTransition}
                onUpdateTransition={updateTransition}
                totalPages={totalPages}
              />
            </Allotment.Pane>
          </Allotment>
        </div>
      )}
    </div>
  )
}
