import { useState, useMemo, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog.jsx'
import { Button } from '../ui/button.jsx'
import { Badge } from '../ui/badge.jsx'
import PageWithOverlays from '../PageWithOverlays.jsx'
import { useDocOverlayTables } from '../../api.js'
import {
  ALL_SECTION_TYPES,
  TYPE_TO_GROUP,
  typeLabel,
} from '../section-hierarchy.js'
import { cn } from '@/lib/utils'
import { ChevronLeft, ChevronRight, Check, X, Trash2, Layers } from 'lucide-react'

// Broad categories for tagging (same as ActionToolbar / PageModal)
const CATEGORIES = [
  { key: 'FRONT_MATTER', short: 'FM', types: [] },
  { key: 'TOC', short: 'TOC', types: [] },
  {
    key: 'GENERAL_REPORTING', short: 'GEN',
    types: [
      'MANAGEMENT_REPORT', 'ESG', 'CORPORATE_GOVERNANCE',
      'RISK_REPORT', 'REMUNERATION_REPORT', 'SUPERVISORY_BOARD',
      'AUDITOR_REPORT', 'RESPONSIBILITY_STATEMENT',
    ],
  },
  {
    key: 'PRIMARY_FINANCIALS', short: 'AFS',
    types: ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'],
  },
  {
    key: 'NOTES', short: 'NOTES',
    types: [
      'NOTES_GENERAL', 'NOTES_PPE', 'NOTES_INTANGIBLES',
      'NOTES_FIN_INST', 'NOTES_TAX', 'NOTES_REVENUE',
      'NOTES_PERSONNEL', 'NOTES_PROVISIONS', 'NOTES_LEASES',
      'NOTES_SEGMENT', 'NOTES_RELATED_PARTIES', 'NOTES_OTHER',
    ],
  },
  { key: 'APPENDIX', short: 'APPX', types: [] },
]

/**
 * Side-by-side TOC review modal.
 * Left: fixed TOC page.
 * Right: navigable target page with tagging rows and prev/next arrows.
 *
 * tocEntries: [{page, label, section_type}, ...]
 * transitions: current transition markers
 */
export function SideBySideCompare({
  open,
  onOpenChange,
  docId,
  tocPage,
  tocEntries = [],
  totalPages,
  pageDims,
  transitions = [],
  multiTags = [],
  onAddTransition,
  onRemoveTransition,
  onToggleMultiTag,
  onCreateEdge,
  initialTargetPage,
}) {
  // Left panel page — defaults to tocPage but navigable
  const [leftPage, setLeftPage] = useState(tocPage || 1)
  // Right panel page — starts at first TOC entry or initialTargetPage
  const [rightPage, setRightPage] = useState(1)
  const [expandedCat, setExpandedCat] = useState(null)
  const [tagMenuExpanded, setTagMenuExpanded] = useState(false)

  // Current TOC entry index for TOC-entry-level navigation
  const [tocIndex, setTocIndex] = useState(0)

  // Resolve the navigation page for a TOC entry (internal_page if available)
  const navPage = useCallback((entry) => entry?.internal_page ?? entry?.page, [])

  useEffect(() => {
    if (!open) return
    setLeftPage(tocPage || 1)
    if (initialTargetPage) {
      setRightPage(initialTargetPage)
      const idx = tocEntries.findIndex(e => (e.internal_page ?? e.page) === initialTargetPage)
      setTocIndex(idx >= 0 ? idx : 0)
    } else if (tocEntries.length > 0) {
      setRightPage(navPage(tocEntries[0]))
      setTocIndex(0)
    }
  }, [open, initialTargetPage, tocEntries, tocPage, navPage])

  const { data: allTables = [] } = useDocOverlayTables(docId, open)

  const leftDims = pageDims?.[leftPage] || pageDims?.[String(leftPage)] || { width: 595, height: 842 }
  const rightDims = pageDims?.[rightPage] || pageDims?.[String(rightPage)] || { width: 595, height: 842 }

  const leftTables = useMemo(
    () => allTables.filter(t => t.pageNo === leftPage),
    [allTables, leftPage],
  )
  const rightTables = useMemo(
    () => allTables.filter(t => t.pageNo === rightPage),
    [allTables, rightPage],
  )

  // Current transition on right page
  const rightTransition = useMemo(
    () => transitions.find(t => t.page === rightPage) || null,
    [transitions, rightPage],
  )
  const currentType = rightTransition?.section_type || null

  // Pages that already have transitions (for TOC entry check marks)
  const transitionPages = useMemo(
    () => new Set(transitions.map(t => t.page)),
    [transitions],
  )

  // Multi-tags on the right page
  const rightPageMultiTags = useMemo(
    () => multiTags.filter(mt => mt.page === rightPage),
    [multiTags, rightPage],
  )

  // Current TOC entry for the right page
  const currentTocEntry = tocEntries[tocIndex] || null

  // Sync expanded category from current transition
  useEffect(() => {
    if (!currentType) { setExpandedCat(null); return }
    const cat = CATEGORIES.find(c => c.key === currentType)
    if (cat && cat.types.length > 0) { setExpandedCat(cat.key); return }
    const parent = CATEGORIES.find(c => c.types.includes(currentType))
    if (parent) { setExpandedCat(parent.key); return }
    setExpandedCat(null)
  }, [currentType, rightPage])

  const activeCat = CATEGORIES.find(c => c.key === expandedCat) || null

  // Reset tag menu when navigating to a new page
  useEffect(() => { setTagMenuExpanded(false) }, [rightPage])

  // Show full category menu when no tag exists or user clicked "+ Add Tag"
  const showFullMenu = !rightTransition || tagMenuExpanded

  // Navigate to TOC entry by index
  const goToTocEntry = useCallback((idx) => {
    if (idx >= 0 && idx < tocEntries.length) {
      setTocIndex(idx)
      setRightPage(navPage(tocEntries[idx]))
    }
  }, [tocEntries, navPage])

  // Navigate to a TOC entry — updates right page and index
  const goToTocEntryByPage = useCallback((internalPage) => {
    setRightPage(internalPage)
    const idx = tocEntries.findIndex(e => (e.internal_page ?? e.page) === internalPage)
    if (idx >= 0) setTocIndex(idx)
  }, [tocEntries])

  // Page-level nav
  const goLeftPage = useCallback((page) => {
    if (page >= 1 && page <= totalPages) setLeftPage(page)
  }, [totalPages])

  const goRightPage = useCallback((page) => {
    if (page >= 1 && page <= totalPages) setRightPage(page)
  }, [totalPages])

  // If page already has a primary tag, add as multi-tag instead of replacing
  const tagOrMultiTag = useCallback((type) => {
    if (rightTransition && rightTransition.section_type !== type) {
      // Already has a different primary tag → add as multi-tag
      onToggleMultiTag?.(rightPage, type)
    } else {
      onAddTransition?.({
        page: rightPage,
        section_type: type,
        label: '',
        note_number: null,
        source: 'manual',
        validated: true,
      })
    }
  }, [rightPage, rightTransition, onAddTransition, onToggleMultiTag])

  const handleCategoryClick = (cat) => {
    if (cat.types.length === 0) {
      tagOrMultiTag(cat.key)
      setExpandedCat(null)
    } else {
      if (expandedCat === cat.key) {
        tagOrMultiTag(cat.key)
      } else {
        setExpandedCat(cat.key)
      }
    }
  }

  const handleSubTypeClick = (type) => {
    tagOrMultiTag(type)
  }

  // Accept current TOC entry as transition + create edge
  const handleAcceptTocEntry = useCallback(() => {
    if (!currentTocEntry?.section_type) return
    const intPage = currentTocEntry.internal_page ?? currentTocEntry.page
    onAddTransition?.({
      page: intPage,
      section_type: currentTocEntry.section_type,
      label: currentTocEntry.label || '',
      note_number: null,
      source: 'toc',
      validated: false,
    })
    if (onCreateEdge && tocPage) {
      onCreateEdge({
        source_type: 'toc_page',
        source_page: tocPage,
        target_type: 'section_start',
        target_page: intPage,
        edge_type: 'toc_ref',
        label: currentTocEntry.label || '',
        confidence: 1.0,
        status: 'confirmed',
      })
    }
  }, [currentTocEntry, tocPage, onAddTransition, onCreateEdge])

  // Accept a specific TOC entry as a transition
  const acceptEntry = useCallback((entry) => {
    if (!entry?.section_type) return
    const intPage = entry.internal_page ?? entry.page
    onAddTransition?.({
      page: intPage,
      section_type: entry.section_type,
      label: entry.label || '',
      note_number: null,
      source: 'toc',
      validated: true,
    })
  }, [onAddTransition])

  // Reject a TOC entry suggestion (remove its transition if present)
  const rejectEntry = useCallback((entry) => {
    const intPage = entry.internal_page ?? entry.page
    onRemoveTransition?.(intPage)
  }, [onRemoveTransition])

  const hasTransitionOnRight = !!rightTransition

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[95vw] w-[95vw] h-[93vh] flex flex-col p-0 gap-0">
        {/* Header */}
        <DialogHeader className="px-3 py-1.5 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <DialogTitle className="text-sm font-semibold">
              TOC Review
            </DialogTitle>
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 tabular-nums">
              {tocIndex + 1} / {tocEntries.length}
            </Badge>
            {currentTocEntry && (
              <span className="text-xs text-sky-400 truncate max-w-[300px]">
                {currentTocEntry.label}
              </span>
            )}
            {currentTocEntry?.section_type && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0"
                style={{ color: ALL_SECTION_TYPES[currentTocEntry.section_type]?.hex }}>
                {typeLabel(currentTocEntry.section_type)}
              </Badge>
            )}
            <div className="ml-auto flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-6 text-xs gap-1"
                onClick={() => goToTocEntry(tocIndex - 1)} disabled={tocIndex <= 0}>
                <ChevronLeft className="size-3" /> Prev
              </Button>
              <Button variant="outline" size="sm" className="h-6 text-xs gap-1"
                onClick={() => goToTocEntry(tocIndex + 1)} disabled={tocIndex >= tocEntries.length - 1}>
                Next <ChevronRight className="size-3" />
              </Button>
              {currentTocEntry?.section_type && !hasTransitionOnRight && (
                <Button size="sm" className="h-6 text-xs gap-1 bg-sky-600 hover:bg-sky-700"
                  onClick={handleAcceptTocEntry}>
                  <Check className="size-3" /> Accept
                </Button>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Side-by-side panels */}
        <div className="flex-1 min-h-0 flex">
          {/* Left: TOC page + entry list */}
          <div className="w-[45%] shrink-0 flex flex-col border-r border-border">
            {/* Nav bar */}
            <div className="px-2 py-1 text-[10px] font-medium text-muted-foreground flex items-center gap-1 shrink-0 border-b border-border/50">
              <Button variant="ghost" size="sm" className="h-5 px-1"
                onClick={() => goLeftPage(leftPage - 1)} disabled={leftPage <= 1}>
                <ChevronLeft className="size-3" />
              </Button>
              <span className="tabular-nums">p.{leftPage}</span>
              <Button variant="ghost" size="sm" className="h-5 px-1"
                onClick={() => goLeftPage(leftPage + 1)} disabled={leftPage >= totalPages}>
                <ChevronRight className="size-3" />
              </Button>
              {tocPage && leftPage !== tocPage && (
                <button
                  className="text-[10px] px-1 rounded bg-sky-500/15 text-sky-400 hover:bg-sky-500/25 ml-1"
                  onClick={() => setLeftPage(tocPage)}
                >
                  TOC p.{tocPage}
                </button>
              )}
            </div>

            {/* Page image */}
            <div className="flex-[3] min-h-0 overflow-auto p-1 bg-muted/20">
              <PageWithOverlays
                docId={docId}
                pageNo={leftPage}
                pageDims={leftDims}
                tables={leftTables}
                showDoclingElements={false}
              />
            </div>

            {/* TOC entry list */}
            {tocEntries.length > 0 && (
              <div className="flex-[2] min-h-0 flex flex-col border-t border-border">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground shrink-0">
                  TOC Entries ({tocEntries.length})
                </div>
                <div className="flex-1 overflow-y-auto">
                  {tocEntries.map((entry, i) => {
                    const intPage = entry.internal_page ?? entry.page
                    const extPage = entry.external_page ?? entry.page
                    const hasOffset = intPage !== extPage
                    const isActive = intPage === rightPage
                    const hasTransition = transitionPages.has(intPage)
                    const typeMeta = entry.section_type ? ALL_SECTION_TYPES[entry.section_type] : null
                    return (
                      <button
                        key={`${intPage}-${i}`}
                        className={cn(
                          'flex items-center gap-1.5 w-full px-2 py-0.5 text-left hover:bg-accent/50 rounded-sm',
                          isActive && 'bg-accent',
                        )}
                        onClick={() => goToTocEntryByPage(intPage)}
                      >
                        <span className="text-[11px] tabular-nums w-10 shrink-0 text-right" title={hasOffset ? `PDF p.${extPage} → fixture p.${intPage}` : undefined}>
                          <span className="text-foreground">{intPage}</span>
                          {hasOffset && (
                            <span className="text-muted-foreground/40 text-[9px] ml-0.5">({extPage})</span>
                          )}
                        </span>
                        <span className={cn(
                          'text-xs truncate flex-1',
                          isActive ? 'text-foreground' : 'text-muted-foreground',
                        )}>
                          {entry.label}
                        </span>
                        {typeMeta && (
                          <span className="text-[9px] px-1 rounded shrink-0"
                            style={{ color: typeMeta.hex }}>
                            {typeLabel(entry.section_type)}
                          </span>
                        )}
                        {hasTransition ? (
                          <span className="flex items-center gap-0.5 shrink-0"
                            onClick={e => e.stopPropagation()}>
                            <Check className="size-3 text-green-500" />
                            <span
                              className="size-4 flex items-center justify-center rounded hover:bg-destructive/20 cursor-pointer"
                              title="Remove transition"
                              onClick={() => rejectEntry(entry)}
                            >
                              <X className="size-2.5 text-muted-foreground hover:text-destructive" />
                            </span>
                          </span>
                        ) : entry.section_type ? (
                          <span className="flex items-center gap-0.5 shrink-0"
                            onClick={e => e.stopPropagation()}>
                            <span
                              className="size-4 flex items-center justify-center rounded hover:bg-green-500/20 cursor-pointer"
                              title={`Accept as ${typeLabel(entry.section_type)}`}
                              onClick={() => acceptEntry(entry)}
                            >
                              <Check className="size-2.5 text-muted-foreground hover:text-green-500" />
                            </span>
                            <span
                              className="size-4 flex items-center justify-center rounded hover:bg-destructive/20 cursor-pointer"
                              title="Dismiss suggestion"
                              onClick={() => rejectEntry(entry)}
                            >
                              <X className="size-2.5 text-muted-foreground hover:text-destructive" />
                            </span>
                          </span>
                        ) : null}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right: target page with tagging */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Right page nav + tagging */}
            <div className="flex items-center gap-1 px-2 py-1 border-b border-border/50 shrink-0">
              <Button variant="outline" size="sm" className="h-6 px-1.5"
                onClick={() => goRightPage(rightPage - 1)} disabled={rightPage <= 1}>
                <ChevronLeft className="size-3" />
              </Button>
              <span className="text-xs font-medium tabular-nums w-16 text-center">
                p.{rightPage}
              </span>
              <Button variant="outline" size="sm" className="h-6 px-1.5"
                onClick={() => goRightPage(rightPage + 1)} disabled={rightPage >= totalPages}>
                <ChevronRight className="size-3" />
              </Button>

              <span className="text-muted-foreground/30 mx-1">|</span>

              {showFullMenu ? (
                <>
                  {/* Full category buttons */}
                  {CATEGORIES.map(cat => {
                    const meta = ALL_SECTION_TYPES[cat.key]
                    const isTagged = currentType === cat.key
                    const hasTaggedChild = cat.types.includes(currentType)
                    const isExpanded = expandedCat === cat.key
                    const isMultiTagged = rightPageMultiTags.some(
                      mt => mt.section_type === cat.key || cat.types.includes(mt.section_type)
                    )
                    return (
                      <button
                        key={cat.key}
                        className={cn(
                          'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium transition-colors',
                          isExpanded ? 'bg-accent ring-1 ring-primary/30' :
                          (isTagged || hasTaggedChild) ? 'bg-accent/40' :
                          isMultiTagged ? 'bg-amber-500/10' :
                          'hover:bg-accent/50',
                        )}
                        onClick={() => handleCategoryClick(cat)}
                      >
                        <span className="size-1.5 rounded-full shrink-0"
                          style={{ backgroundColor: meta?.hex || '#71717a' }} />
                        <span className={cn(
                          isTagged || hasTaggedChild || isExpanded || isMultiTagged
                            ? 'text-foreground' : 'text-muted-foreground',
                        )}>
                          {cat.short}
                        </span>
                        {isTagged && <Check className="size-2.5 text-primary" />}
                        {isMultiTagged && <Layers className="size-2.5 text-amber-400" />}
                      </button>
                    )
                  })}
                  {rightTransition && (
                    <Button variant="destructive" size="sm" className="h-5 px-1 ml-1"
                      onClick={() => onRemoveTransition?.(rightPage)}>
                      <Trash2 className="size-3" />
                    </Button>
                  )}
                </>
              ) : (
                <>
                  {/* Collapsed: show current tag + multi-tags + add button */}
                  <button
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:opacity-80"
                    style={{
                      backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}22`,
                      color: ALL_SECTION_TYPES[currentType]?.hex,
                    }}
                    onClick={() => onRemoveTransition?.(rightPage)}
                    title="Remove tag"
                  >
                    <span className="size-2 rounded-full shrink-0"
                      style={{ backgroundColor: ALL_SECTION_TYPES[currentType]?.hex }} />
                    {typeLabel(currentType)}
                    <X className="size-3" />
                  </button>

                  {rightPageMultiTags.map(mt => {
                    const meta = ALL_SECTION_TYPES[mt.section_type]
                    return (
                      <button
                        key={mt.section_type}
                        className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium hover:opacity-80"
                        style={{
                          backgroundColor: `${meta?.hex}18`,
                          color: meta?.hex,
                        }}
                        onClick={() => onToggleMultiTag?.(rightPage, mt.section_type)}
                        title={`Remove ${typeLabel(mt.section_type)}`}
                      >
                        {typeLabel(mt.section_type)}
                        <X className="size-2" />
                      </button>
                    )
                  })}

                  <Button variant="outline" size="sm" className="h-5 text-[10px] px-2 ml-1"
                    onClick={() => setTagMenuExpanded(true)}>
                    + Add Tag
                  </Button>
                </>
              )}
            </div>

            {/* Tagging row 2: sub-types (only in expanded mode) */}
            {showFullMenu && activeCat && activeCat.types.length > 0 && (
              <div className="flex flex-wrap items-center gap-1 px-2 py-0.5 border-b border-border/50 bg-muted/30 shrink-0">
                <button
                  className={cn(
                    'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors',
                    currentType === activeCat.key
                      ? 'bg-accent font-medium' : 'hover:bg-accent/50 text-muted-foreground',
                  )}
                  onClick={() => handleSubTypeClick(activeCat.key)}
                >
                  <span className="size-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: ALL_SECTION_TYPES[activeCat.key]?.hex }} />
                  All
                  {currentType === activeCat.key && <Check className="size-2.5 text-primary" />}
                </button>
                <span className="text-muted-foreground/30 text-[10px]">|</span>
                {activeCat.types.map(type => {
                  const meta = ALL_SECTION_TYPES[type]
                  const isTagged = currentType === type
                  return (
                    <button
                      key={type}
                      className={cn(
                        'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors',
                        isTagged ? 'bg-accent font-medium' : 'hover:bg-accent/50 text-muted-foreground',
                      )}
                      onClick={() => handleSubTypeClick(type)}
                    >
                      <span className="size-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: meta?.hex || '#71717a' }} />
                      {typeLabel(type)}
                      {isTagged && <Check className="size-2.5 text-primary" />}
                    </button>
                  )
                })}
              </div>
            )}

            {/* Page image with green border + inline tag overlay */}
            <div className="flex-1 min-h-0 overflow-auto p-1 bg-muted/20">
              <div className={cn(
                'relative rounded',
                rightTransition && 'ring-2 ring-green-500/70 rounded-lg',
              )}>
                <PageWithOverlays
                  docId={docId}
                  pageNo={rightPage}
                  pageDims={rightDims}
                  tables={rightTables}
                  showDoclingElements={false}
                />
                {/* Inline tag overlay on page */}
                {rightTransition && (
                  <div className="absolute top-2 left-2 z-20 flex items-center gap-1">
                    <button
                      className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold shadow-md backdrop-blur-sm"
                      style={{
                        backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}33`,
                        color: ALL_SECTION_TYPES[currentType]?.hex,
                        border: `1px solid ${ALL_SECTION_TYPES[currentType]?.hex}66`,
                      }}
                      onClick={() => onRemoveTransition?.(rightPage)}
                      title={`Remove ${typeLabel(currentType)} tag`}
                    >
                      {typeLabel(currentType)}
                      <X className="size-2.5" />
                    </button>
                    {rightPageMultiTags.map(mt => {
                      const meta = ALL_SECTION_TYPES[mt.section_type]
                      return (
                        <button
                          key={mt.section_type}
                          className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium shadow-sm backdrop-blur-sm"
                          style={{
                            backgroundColor: `${meta?.hex}22`,
                            color: meta?.hex,
                            border: `1px solid ${meta?.hex}44`,
                          }}
                          onClick={() => onToggleMultiTag?.(rightPage, mt.section_type)}
                        >
                          {typeLabel(mt.section_type)}
                          <X className="size-2.5" />
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
