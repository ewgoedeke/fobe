import { useState, useMemo, useCallback, useEffect } from 'react'
import { Allotment } from 'allotment'
import { cn } from '@/lib/utils'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Badge } from '../ui/badge.jsx'
import { Skeleton } from '../ui/skeleton.jsx'
import { Save, Loader2, Search, Sparkles, BookOpen, CheckCircle2, Info } from 'lucide-react'
import {
  useAnnotateDocuments, useAnnotateToc, usePageFeatures,
  useAnnotateDetect, useDocEdges, useValidateEdge, useDeleteEdge,
  useTocEntries, useCreateEdge, useMarkComplete,
} from '../../api.js'
import { useAnnotationState } from './useAnnotationState.js'
import { resolveTransitions, resolveMultiTags } from './resolveTransitions.js'
import { CoverageStrip } from './CoverageStrip.jsx'
import { TransitionList } from './TransitionList.jsx'
import { ActionToolbar } from './ActionToolbar.jsx'
import { PageStripGallery } from './PageStripGallery.jsx'
import { SideBySideCompare } from './SideBySideCompare.jsx'
import { PageModal } from './PageModal.jsx'

// Keyboard shortcut → section type mapping
const KEY_TO_TYPE = {
  g: 'GENERAL_REPORTING', t: 'TOC', p: 'PNL', s: 'SFP',
  c: 'CFS', o: 'OCI', e: 'SOCIE', n: 'NOTES',
  f: 'FRONT_MATTER', a: 'APPENDIX', r: 'AUDITOR_REPORT',
}

export default function AnnotationWorkflow({ initialDocId }) {
  const [docId, setDocId] = useState(initialDocId || null)
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [tier, setTier] = useState('')
  const [showSearch, setShowSearch] = useState(!initialDocId)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareTargetPage, setCompareTargetPage] = useState(null)
  const [detecting, setDetecting] = useState(false)
  const [suggestedType, setSuggestedType] = useState('')
  const [pageModalOpen, setPageModalOpen] = useState(false)

  // Debounce search input for server-side filtering
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 250)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data: documents = [], isLoading: docsLoading } = useAnnotateDocuments(debouncedQuery, tier)
  const { data: tocData } = useAnnotateToc(docId)
  const { data: pageFeatures } = usePageFeatures(docId)
  const { data: edges = [] } = useDocEdges(docId)
  const detectMutation = useAnnotateDetect(docId)
  const createEdgeMutation = useCreateEdge(docId)
  const markCompleteMutation = useMarkComplete(docId)
  const [showKeybindings, setShowKeybindings] = useState(false)

  const totalPages = tocData?.page_count || 0
  const pageDims = tocData?.page_dims || {}

  const {
    transitions,
    multiTags,
    selectedPage,
    dirty,
    changeCount,
    isLoading: stateLoading,
    isSaving,
    addTransition,
    removeTransition,
    updateTransition,
    mergeProvisional,
    toggleMultiTag,
    setPage,
    saveNow,
  } = useAnnotationState(docId)

  // User-tagged TOC page (from transitions) — used to filter API TOC table detection
  const userTocPage = useMemo(() => {
    const tocTransition = transitions.find(t => t.section_type === 'TOC')
    return tocTransition?.page || null
  }, [transitions])

  // Pass user-tagged TOC page to API so it only looks at tables on that page
  const { data: tocEntriesData } = useTocEntries(docId, userTocPage)
  const tocEntries = tocEntriesData?.entries || []
  const apiTocPage = tocEntriesData?.toc_page || null

  // Effective TOC page: prefer user-tagged, fall back to API heuristic
  const tocPage = userTocPage || apiTocPage

  // Resolve transitions → page map (for coverage strip coloring)
  const pageMap = useMemo(
    () => resolveTransitions(transitions, totalPages),
    [transitions, totalPages],
  )

  // Resolve multi-tags with carry-forward within transition spans
  const resolvedMultiTags = useMemo(
    () => resolveMultiTags(multiTags, transitions, totalPages),
    [multiTags, transitions, totalPages],
  )

  // TOC entry pages for coverage strip markers
  const tocEntryPages = useMemo(
    () => new Set(tocEntries.map(e => e.page)),
    [tocEntries],
  )

  // Find current transition for selected page
  const currentTransition = useMemo(
    () => transitions.find(t => t.page === selectedPage) || null,
    [transitions, selectedPage],
  )

  // Documents are already filtered server-side
  const filteredDocs = documents

  const selectDoc = useCallback((id) => {
    setDocId(id)
    setShowSearch(false)
    setSearchQuery('')
  }, [])

  // Reset page when doc changes
  useEffect(() => {
    setPage(1)
    setSuggestedType('')
  }, [docId])

  // Clear suggested type when page changes
  useEffect(() => {
    setSuggestedType('')
  }, [selectedPage])

  const handlePageClick = useCallback((page) => {
    setPage(page)
  }, [setPage])

  const handleThumbnailClick = useCallback((page) => {
    setPage(page)
    setPageModalOpen(true)
  }, [setPage])

  const handlePageModalPageChange = useCallback((page) => {
    if (page >= 1 && page <= totalPages) {
      setPage(page)
    }
  }, [setPage, totalPages])

  // Auto-detect: call API, merge provisional markers
  const handleDetect = useCallback(async () => {
    if (!docId || detecting) return
    setDetecting(true)
    try {
      const result = await detectMutation.mutateAsync()
      let raw = result.markers || result.transitions || []
      if (raw.length === 0 && result.sections?.length > 0) {
        raw = result.sections.map(s => ({
          page: s.start_page,
          section_type: s.statement_type,
          label: s.label || '',
          note_number: s.note_number || null,
        }))
      }
      const markers = raw.map(m => ({
        ...m,
        source: m.source || 'detected',
        validated: false,
      }))
      mergeProvisional(markers)
    } finally {
      setDetecting(false)
    }
  }, [docId, detecting, detectMutation, mergeProvisional])

  // TOC Review — open side-by-side with optional target page
  const handleOpenTocReview = useCallback((targetPage) => {
    setCompareTargetPage(targetPage || null)
    setCompareOpen(true)
  }, [])

  const handleCreateEdge = useCallback((edgeData) => {
    createEdgeMutation.mutate(edgeData)
  }, [createEdgeMutation])

  // TOC suggestion → pre-populate toolbar type
  const handleSuggestType = useCallback((type) => {
    setSuggestedType(type)
  }, [])

  // Mark Complete: save if dirty, mark complete, advance to next incomplete doc
  const handleMarkComplete = useCallback(async () => {
    if (!docId) return
    // Save first if there are unsaved changes
    if (dirty) await saveNow()
    // Mark complete
    await markCompleteMutation.mutateAsync(true)
    // Find next incomplete document
    const currentIdx = filteredDocs.findIndex(d => d.doc_id === docId)
    const isIncomplete = d => !d.completed_at && d.annotation_status !== 'complete'
    const nextDoc = filteredDocs.find((d, i) => i > currentIdx && isIncomplete(d))
      || filteredDocs.find((d, i) => i < currentIdx && isIncomplete(d))
    if (nextDoc) {
      selectDoc(nextDoc.doc_id)
    }
  }, [docId, dirty, saveNow, markCompleteMutation, filteredDocs, selectDoc])

  // Keyboard shortcuts (landing page — not inside modal)
  useEffect(() => {
    if (!docId || !totalPages) return

    const handler = (e) => {
      // Skip when modal is open — modal has its own key handler
      if (pageModalOpen) return

      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

      const key = e.key.toLowerCase()

      // Arrow keys / [ ] : navigate pages
      if (e.key === 'ArrowLeft' || key === '[') {
        e.preventDefault()
        if (selectedPage > 1) setPage(selectedPage - 1)
        return
      }
      if (e.key === 'ArrowRight' || key === ']') {
        e.preventDefault()
        if (selectedPage < totalPages) setPage(selectedPage + 1)
        return
      }

      // Space: open page modal
      if (e.key === ' ') {
        e.preventDefault()
        setPageModalOpen(true)
        return
      }

      // Letter keys: tag current page
      if (KEY_TO_TYPE[key]) {
        e.preventDefault()
        addTransition({
          page: selectedPage,
          section_type: KEY_TO_TYPE[key],
          label: '',
          note_number: null,
          source: 'manual',
          validated: true,
        })
        return
      }

      // Delete/Backspace: remove tag
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const hasTransition = transitions.some(t => t.page === selectedPage)
        if (hasTransition) {
          e.preventDefault()
          removeTransition(selectedPage)
        }
        return
      }

      // V: validate provisional tag
      if (key === 'v') {
        const t = transitions.find(t => t.page === selectedPage)
        if (t && !t.validated) {
          e.preventDefault()
          updateTransition(selectedPage, { validated: true, source: 'manual' })
        }
        return
      }

      // Tab: jump to next provisional
      if (e.key === 'Tab') {
        const provisionals = transitions
          .filter(t => !t.validated && t.source !== 'manual')
          .sort((a, b) => a.page - b.page)
        if (provisionals.length > 0) {
          e.preventDefault()
          const next = provisionals.find(t => t.page > selectedPage) || provisionals[0]
          setPage(next.page)
        }
        return
      }

      // Escape: close search if open
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false)
        return
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [docId, totalPages, selectedPage, transitions, addTransition, removeTransition, updateTransition, setPage, pageModalOpen, showSearch])

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
                filteredDocs.map(d => (
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
                    {(d.completed_at || d.annotation_status === 'complete') && (
                      <CheckCircle2 className="size-3 text-green-500 shrink-0" title="Complete" />
                    )}
                    {!d.completed_at && d.annotation_status !== 'complete' && d.has_ground_truth && (
                      <span className="size-1.5 rounded-full bg-green-500 shrink-0" title="Has GT" />
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Tier selector */}
        <select
          className="h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
          value={tier}
          onChange={e => setTier(e.target.value)}
        >
          <option value="">Test Set (22)</option>
          <option value="UGB20">UGB20</option>
          <option value="UGB50">UGB50</option>
          <option value="UGB100">UGB100</option>
          <option value="UGB200">UGB200</option>
          <option value="UGB500">UGB500</option>
          <option value="UGB_ALL">UGB All</option>
        </select>

        {/* Doc info */}
        {docId && (
          <>
            <span className="text-sm font-semibold truncate max-w-[200px]">{docId}</span>
            {totalPages > 0 && (
              <span className="text-[11px] text-muted-foreground tabular-nums">{totalPages}p</span>
            )}
          </>
        )}

        {/* Status + TOC review + detect + save */}
        <div className="ml-auto flex items-center gap-2">
          {transitions.length > 0 && (() => {
            const manual = transitions.filter(t => t.source === 'manual' || t.validated).length
            const provisional = transitions.filter(t => !t.validated && t.source !== 'manual').length
            const inferred = pageMap.size - transitions.length
            return (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-green-500/15 text-green-400 tabular-nums">
                {manual} manual{provisional > 0 ? ` · ${provisional} prov.` : ''}{inferred > 0 ? ` · ${inferred} inferred` : ''}
              </Badge>
            )
          })()}
          {dirty && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-yellow-500/15 text-yellow-500">
              Unsaved
            </Badge>
          )}
          {isSaving && (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
          )}
          {docId && tocEntries.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={() => handleOpenTocReview()}
            >
              <BookOpen className="size-3" />
              TOC ({tocEntries.length})
            </Button>
          )}
          {docId && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={handleDetect}
              disabled={detecting}
            >
              {detecting
                ? <Loader2 className="size-3 animate-spin" />
                : <Sparkles className="size-3" />
              }
              Detect
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={saveNow}
            disabled={!docId || !dirty || isSaving}
          >
            <Save className="size-3" />
            Save
          </Button>
          {docId && transitions.length > 0 && (
            <Button
              variant="default"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={handleMarkComplete}
              disabled={markCompleteMutation.isPending}
            >
              <CheckCircle2 className="size-3" />
              Complete
            </Button>
          )}
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setShowKeybindings(v => !v)}
              title="Keyboard shortcuts"
            >
              <Info className="size-3.5" />
            </Button>
            {showKeybindings && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowKeybindings(false)} />
                <div className="absolute right-0 top-full mt-1 z-50 w-72 rounded-md border border-border bg-popover shadow-lg p-3 text-xs">
                  <h4 className="font-semibold mb-2">Keyboard Shortcuts</h4>
                  <div className="space-y-1.5 text-muted-foreground">
                    <p className="font-medium text-foreground">Navigation</p>
                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                      <kbd className="font-mono bg-muted px-1 rounded">←/→</kbd><span>Previous / Next page</span>
                      <kbd className="font-mono bg-muted px-1 rounded">Space</kbd><span>Open page modal</span>
                      <kbd className="font-mono bg-muted px-1 rounded">Esc</kbd><span>Close modal / search</span>
                    </div>
                    <p className="font-medium text-foreground mt-2">Tagging</p>
                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                      <kbd className="font-mono bg-muted px-1 rounded">G</kbd><span>General Reporting</span>
                      <kbd className="font-mono bg-muted px-1 rounded">T</kbd><span>TOC</span>
                      <kbd className="font-mono bg-muted px-1 rounded">P</kbd><span>PNL</span>
                      <kbd className="font-mono bg-muted px-1 rounded">S</kbd><span>SFP</span>
                      <kbd className="font-mono bg-muted px-1 rounded">C</kbd><span>CFS</span>
                      <kbd className="font-mono bg-muted px-1 rounded">O</kbd><span>OCI</span>
                      <kbd className="font-mono bg-muted px-1 rounded">E</kbd><span>SOCIE</span>
                      <kbd className="font-mono bg-muted px-1 rounded">N</kbd><span>Notes</span>
                      <kbd className="font-mono bg-muted px-1 rounded">F</kbd><span>Front Matter</span>
                      <kbd className="font-mono bg-muted px-1 rounded">A</kbd><span>Appendix</span>
                      <kbd className="font-mono bg-muted px-1 rounded">R</kbd><span>Auditor Report</span>
                    </div>
                    <p className="font-medium text-foreground mt-2">Actions</p>
                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                      <kbd className="font-mono bg-muted px-1 rounded">Del</kbd><span>Remove tag</span>
                      <kbd className="font-mono bg-muted px-1 rounded">V</kbd><span>Validate provisional</span>
                      <kbd className="font-mono bg-muted px-1 rounded">Tab</kbd><span>Jump to next provisional</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground/60 mt-2">In modal: same keys apply. Already-tagged pages get multi-tags.</p>
                  </div>
                </div>
              </>
            )}
          </div>
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
            tocEntryPages={tocEntryPages}
            resolvedMultiTags={resolvedMultiTags}
          />
        </div>
      )}

      {/* Action toolbar */}
      {docId && totalPages > 0 && (
        <ActionToolbar
          selectedPage={selectedPage}
          totalPages={totalPages}
          currentTransition={currentTransition}
          pageInfo={pageMap.get(selectedPage)}
          suggestedType={suggestedType}
          onAddTransition={addTransition}
          onRemoveTransition={removeTransition}
          multiTags={multiTags}
          resolvedMultiTags={resolvedMultiTags}
          onToggleMultiTag={toggleMultiTag}
          onCompareClick={tocEntries.length > 0 ? () => handleOpenTocReview(selectedPage) : undefined}
          hasEdges={tocEntries.length > 0}
        />
      )}

      {/* Main 2-pane layout */}
      {!docId ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
          Select a document to begin annotation
        </div>
      ) : isLoading ? (
        <div className="flex-1 flex gap-4 p-4">
          <div className="w-56 flex flex-col gap-2">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-6 w-full" />)}
          </div>
          <div className="flex-1 flex flex-wrap gap-3">
            {Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-32 w-40 rounded" />)}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <Allotment>
            {/* Left: Transition list */}
            <Allotment.Pane minSize={200} preferredSize={260} maxSize={320}>
              <TransitionList
                transitions={transitions}
                totalPages={totalPages}
                selectedPage={selectedPage}
                onPageClick={handlePageClick}
                onSuggestType={handleSuggestType}
              />
            </Allotment.Pane>

            {/* Right: Page gallery */}
            <Allotment.Pane minSize={300}>
              <PageStripGallery
                docId={docId}
                totalPages={totalPages}
                pageDims={pageDims}
                pageMap={pageMap}
                pageFeatures={pageFeatures}
                transitions={transitions}
                selectedPage={selectedPage}
                onPageClick={handleThumbnailClick}
                resolvedMultiTags={resolvedMultiTags}
                onRefBadgeClick={tocEntries.length > 0 ? (page) => handleOpenTocReview(page) : undefined}
              />
            </Allotment.Pane>
          </Allotment>
        </div>
      )}

      {/* Page detail modal */}
      {docId && totalPages > 0 && (
        <PageModal
          open={pageModalOpen}
          onOpenChange={setPageModalOpen}
          docId={docId}
          pageNo={selectedPage}
          totalPages={totalPages}
          pageDims={pageDims}
          pageMap={pageMap}
          pageFeatures={pageFeatures}
          transition={currentTransition}
          onAddTransition={addTransition}
          onRemoveTransition={removeTransition}
          onPageChange={handlePageModalPageChange}
          multiTags={multiTags}
          resolvedMultiTags={resolvedMultiTags}
          onToggleMultiTag={toggleMultiTag}
        />
      )}

      {/* TOC Review side-by-side modal */}
      {docId && tocEntries.length > 0 && (
        <SideBySideCompare
          open={compareOpen}
          onOpenChange={setCompareOpen}
          docId={docId}
          tocPage={tocPage}
          tocEntries={tocEntries}
          totalPages={totalPages}
          pageDims={pageDims}
          transitions={transitions}
          multiTags={multiTags}
          onAddTransition={addTransition}
          onRemoveTransition={removeTransition}
          onToggleMultiTag={toggleMultiTag}
          onCreateEdge={handleCreateEdge}
          initialTargetPage={compareTargetPage}
        />
      )}
    </div>
  )
}
