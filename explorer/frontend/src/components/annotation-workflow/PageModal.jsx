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
import { ChevronLeft, ChevronRight, Check, X, Trash2 } from 'lucide-react'
// Keyboard shortcut → section type mapping (same as AnnotationWorkflow)
const KEY_TO_TYPE = {
  g: 'GENERAL_REPORTING', t: 'TOC', p: 'PNL', s: 'SFP',
  c: 'CFS', o: 'OCI', e: 'SOCIE', n: 'NOTES',
  f: 'FRONT_MATTER', a: 'APPENDIX', r: 'AUDITOR_REPORT',
}

// Broad categories — same structure as ActionToolbar
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
 * Modal showing a larger page render with two-row tagging above the page.
 * Row 1: broad categories (FM, TOC, GEN, AFS, NOTES, APPX)
 * Row 2: specific sub-types for the expanded category
 * Below: full-width page image
 */
export function PageModal({
  open,
  onOpenChange,
  docId,
  pageNo,
  totalPages,
  pageDims,
  pageMap,
  pageFeatures,
  transition,
  onAddTransition,
  onRemoveTransition,
  onPageChange,
  multiTags = [],
  resolvedMultiTags = new Map(),
  onToggleMultiTag,
}) {
  const { data: allTables = [] } = useDocOverlayTables(docId, open)
  const tablesOnPage = useMemo(
    () => allTables.filter(t => t.pageNo === pageNo),
    [allTables, pageNo],
  )

  const dims = pageDims?.[pageNo] || pageDims?.[String(pageNo)] || { width: 595, height: 842 }
  const info = pageMap?.get(pageNo)
  const typeMeta = info ? ALL_SECTION_TYPES[info.type] : null
  const features = pageFeatures?.features?.[pageNo] || pageFeatures?.features?.[String(pageNo)]

  const hasPrev = pageNo > 1
  const hasNext = pageNo < totalPages
  const currentType = transition?.section_type || null

  // Track which category is expanded
  const [expandedCat, setExpandedCat] = useState(null)
  const [tagMenuExpanded, setTagMenuExpanded] = useState(false)

  // Reset tag menu when page changes
  useEffect(() => { setTagMenuExpanded(false) }, [pageNo])

  const showFullMenu = !transition || tagMenuExpanded

  // Sync expanded category from current transition
  useEffect(() => {
    if (!currentType) { setExpandedCat(null); return }
    const cat = CATEGORIES.find(c => c.key === currentType)
    if (cat && cat.types.length > 0) { setExpandedCat(cat.key); return }
    const parent = CATEGORIES.find(c => c.types.includes(currentType))
    if (parent) { setExpandedCat(parent.key); return }
    setExpandedCat(null)
  }, [currentType, pageNo])

  const activeCat = CATEGORIES.find(c => c.key === expandedCat) || null

  // Whether clicks should add multi-tags (menu expanded on already-tagged page)
  const addingMultiTag = tagMenuExpanded && !!transition

  // Use resolved (carry-forward) multi-tags for display
  const resolvedTypes = resolvedMultiTags.get(pageNo) || []
  const pageMultiTags = resolvedTypes.map(st => ({ page: pageNo, section_type: st }))

  const tagOrMultiTag = useCallback((type) => {
    if (addingMultiTag && type !== currentType) {
      onToggleMultiTag?.(pageNo, type)
      setTagMenuExpanded(false)
    } else if (!transition || type === currentType) {
      onAddTransition({
        page: pageNo,
        section_type: type,
        label: '',
        note_number: null,
        source: 'manual',
        validated: true,
      })
    } else {
      onToggleMultiTag?.(pageNo, type)
      setTagMenuExpanded(false)
    }
  }, [addingMultiTag, currentType, pageNo, transition, onAddTransition, onToggleMultiTag])

  const handleCategoryClick = (cat) => {
    if (cat.types.length === 0) {
      // Leaf — tag directly (or multi-tag)
      tagOrMultiTag(cat.key)
      setExpandedCat(null)
    } else {
      if (expandedCat === cat.key) {
        // Double-click on group — tag at group level (or multi-tag)
        tagOrMultiTag(cat.key)
      } else {
        setExpandedCat(cat.key)
      }
    }
  }

  const handleSubTypeClick = (type) => {
    tagOrMultiTag(type)
  }

  // Keyboard shortcuts — attached directly to dialog via onKeyDown to bypass Radix focus trap
  const handleKeyDown = useCallback((e) => {
    const tag = e.target?.tagName
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

    const key = e.key.toLowerCase()

    // Arrow keys / [ ] : navigate pages
    if (e.key === 'ArrowLeft' || key === '[') {
      e.preventDefault()
      e.stopPropagation()
      if (hasPrev) onPageChange(pageNo - 1)
      return
    }
    if (e.key === 'ArrowRight' || key === ']') {
      e.preventDefault()
      e.stopPropagation()
      if (hasNext) onPageChange(pageNo + 1)
      return
    }

    // Letter keys: tag current page (or multi-tag if already tagged)
    if (KEY_TO_TYPE[key]) {
      e.preventDefault()
      e.stopPropagation()
      tagOrMultiTag(KEY_TO_TYPE[key])
      return
    }

    // Delete/Backspace: remove tag
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (transition) {
        e.preventDefault()
        e.stopPropagation()
        onRemoveTransition(pageNo)
      }
      return
    }
  }, [pageNo, hasPrev, hasNext, onPageChange, transition, onRemoveTransition, tagOrMultiTag])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[90vw] w-[90vw] h-[93vh] flex flex-col p-0 gap-0" onKeyDown={handleKeyDown}>
        {/* Header: nav + page info */}
        <DialogHeader className="px-3 py-1.5 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-6 px-1.5"
              onClick={() => onPageChange(pageNo - 1)} disabled={!hasPrev}>
              <ChevronLeft className="size-3" />
            </Button>
            <Button variant="outline" size="sm" className="h-6 px-1.5"
              onClick={() => onPageChange(pageNo + 1)} disabled={!hasNext}>
              <ChevronRight className="size-3" />
            </Button>
            <DialogTitle className="text-sm font-semibold tabular-nums">
              Page {pageNo}
            </DialogTitle>
            {transition && !transition.validated && transition.source !== 'manual' && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-yellow-500/15 text-yellow-500">
                Provisional
              </Badge>
            )}
            {/* Features inline */}
            {features && <FeatureChips features={features} />}
            <span className="text-[11px] text-muted-foreground tabular-nums ml-auto">
              {pageNo} / {totalPages}
            </span>
          </div>
        </DialogHeader>

        {/* Tagging row: collapsed (tag + add) or expanded (full categories) */}
        {showFullMenu ? (
          <>
            <div className="flex items-center gap-1 px-3 py-1 border-b border-border shrink-0">
              {/* Current tag chip + multi-tags when adding more */}
              {transition && (
                <button
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:opacity-80 shrink-0"
                  style={{
                    backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}22`,
                    color: ALL_SECTION_TYPES[currentType]?.hex,
                  }}
                  onClick={() => {
                    onRemoveTransition(pageNo)
                    setExpandedCat(null)
                  }}
                  title="Remove tag"
                >
                  <span className="size-2 rounded-full shrink-0"
                    style={{ backgroundColor: ALL_SECTION_TYPES[currentType]?.hex }} />
                  {typeLabel(currentType)}
                  <X className="size-3" />
                </button>
              )}
              {pageMultiTags.map(mt => {
                const meta = ALL_SECTION_TYPES[mt.section_type]
                return (
                  <Badge
                    key={`top-${mt.section_type}`}
                    variant="secondary"
                    className={cn('text-[10px] px-1.5 py-0 gap-0.5 cursor-pointer h-5 shrink-0', meta?.bg, meta?.text)}
                    onClick={() => onToggleMultiTag?.(pageNo, mt.section_type)}
                  >
                    {typeLabel(mt.section_type)}
                    <X className="size-2.5" />
                  </Badge>
                )
              })}
              {(transition || pageMultiTags.length > 0) && (
                <div className="w-px h-4 bg-border shrink-0" />
              )}

              {CATEGORIES.map(cat => {
                const meta = ALL_SECTION_TYPES[cat.key]
                const isTagged = currentType === cat.key
                const hasTaggedChild = cat.types.includes(currentType)
                const isExpanded = expandedCat === cat.key
                return (
                  <button
                    key={cat.key}
                    className={cn(
                      'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors',
                      isExpanded ? 'bg-accent ring-1 ring-primary/30' :
                      (isTagged || hasTaggedChild) ? 'bg-accent/40' :
                      'hover:bg-accent/50',
                    )}
                    onClick={() => handleCategoryClick(cat)}
                  >
                    <span className="size-2 rounded-full shrink-0"
                      style={{ backgroundColor: meta?.hex || '#71717a' }} />
                    <span className={cn(
                      isTagged || hasTaggedChild || isExpanded
                        ? 'text-foreground' : 'text-muted-foreground',
                    )}>
                      {cat.short}
                    </span>
                    {isTagged && <Check className="size-3 text-primary" />}
                  </button>
                )
              })}
              {addingMultiTag && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 text-[10px] px-1.5 ml-1"
                  onClick={() => setTagMenuExpanded(false)}
                >
                  <X className="size-3" />
                </Button>
              )}
            </div>
            {activeCat && activeCat.types.length > 0 && (
              <div className="flex flex-wrap items-center gap-1 px-3 py-1 border-b border-border/50 bg-muted/30 shrink-0">
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
                  const isMultiTagged = pageMultiTags.some(mt => mt.section_type === type)
                  return (
                    <button
                      key={type}
                      className={cn(
                        'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors',
                        (isTagged || isMultiTagged) ? 'bg-accent font-medium' : 'hover:bg-accent/50 text-muted-foreground',
                      )}
                      onClick={() => handleSubTypeClick(type)}
                    >
                      <span className="size-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: meta?.hex || '#71717a' }} />
                      {typeLabel(type)}
                      {(isTagged || isMultiTagged) && <Check className="size-2.5 text-primary" />}
                    </button>
                  )
                })}
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center gap-1.5 px-3 py-1 border-b border-border shrink-0">
            <button
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:opacity-80"
              style={{
                backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}22`,
                color: ALL_SECTION_TYPES[currentType]?.hex,
              }}
              onClick={() => onRemoveTransition(pageNo)}
              title="Remove tag"
            >
              <span className="size-2 rounded-full shrink-0"
                style={{ backgroundColor: ALL_SECTION_TYPES[currentType]?.hex }} />
              {typeLabel(currentType)}
              <X className="size-3" />
            </button>
            {pageMultiTags.map(mt => {
              const meta = ALL_SECTION_TYPES[mt.section_type]
              return (
                <Badge
                  key={mt.section_type}
                  variant="secondary"
                  className={cn('text-[10px] px-1.5 py-0 gap-0.5 cursor-pointer h-5', meta?.bg, meta?.text)}
                  onClick={() => onToggleMultiTag?.(pageNo, mt.section_type)}
                >
                  {typeLabel(mt.section_type)}
                  <X className="size-2.5" />
                </Badge>
              )
            })}
            <Button variant="outline" size="sm" className="h-5 text-[10px] px-2"
              onClick={() => setTagMenuExpanded(true)}>
              + Add Tag
            </Button>
          </div>
        )}

        {/* Page image — with left/right nav bars */}
        <div className="flex-1 min-h-0 relative">
          {/* Left nav bar — fixed to viewport of scroll area */}
          {hasPrev && (
            <button
              className="absolute left-0 top-0 bottom-0 w-16 z-30 flex items-center justify-center
                bg-black/0 hover:bg-black/20 transition-colors cursor-pointer group"
              onClick={() => onPageChange(pageNo - 1)}
              title={`Page ${pageNo - 1}`}
            >
              <ChevronLeft className="size-8 text-white/0 group-hover:text-white/80 transition-colors drop-shadow-lg" />
            </button>
          )}

          {/* Right nav bar */}
          {hasNext && (
            <button
              className="absolute right-0 top-0 bottom-0 w-16 z-30 flex items-center justify-center
                bg-black/0 hover:bg-black/20 transition-colors cursor-pointer group"
              onClick={() => onPageChange(pageNo + 1)}
              title={`Page ${pageNo + 1}`}
            >
              <ChevronRight className="size-8 text-white/0 group-hover:text-white/80 transition-colors drop-shadow-lg" />
            </button>
          )}

          {/* Scrollable page content */}
          <div className="absolute inset-0 overflow-auto bg-muted/20 flex justify-center p-2">
            <div className={cn('relative', transition && 'ring-2 ring-green-500/70 rounded-lg')}
              style={{
                width: '100%',
                maxWidth: `calc((93vh - 7rem) * ${dims.width / dims.height})`,
              }}>
              <PageWithOverlays
                docId={docId}
                pageNo={pageNo}
                pageDims={dims}
                tables={tablesOnPage}
                showDoclingElements={false}
              />
              {(transition || pageMultiTags.length > 0) && (
                <div className="absolute top-2 left-2 z-20 flex items-center gap-1">
                  {transition && (
                    <button
                      className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold shadow-md backdrop-blur-sm"
                      style={{
                        backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}33`,
                        color: ALL_SECTION_TYPES[currentType]?.hex,
                        border: `1px solid ${ALL_SECTION_TYPES[currentType]?.hex}66`,
                      }}
                      onClick={() => onRemoveTransition(pageNo)}
                      title={`Remove ${typeLabel(currentType)} tag`}
                    >
                      {typeLabel(currentType)}
                      <X className="size-2.5" />
                    </button>
                  )}
                  {pageMultiTags.map(mt => {
                    const meta = ALL_SECTION_TYPES[mt.section_type]
                    return (
                      <button
                        key={mt.section_type}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold shadow-md backdrop-blur-sm"
                        style={{
                          backgroundColor: `${meta?.hex}33`,
                          color: meta?.hex,
                          border: `1px solid ${meta?.hex}66`,
                        }}
                        onClick={() => onToggleMultiTag?.(pageNo, mt.section_type)}
                        title={`Remove ${typeLabel(mt.section_type)} tag`}
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
      </DialogContent>
    </Dialog>
  )
}

function FeatureChips({ features }) {
  const predictions = features.predictions || []
  const chips = []
  if (predictions.length > 0) {
    const top = predictions[0]
    chips.push(
      <span key="ml" className="text-[10px] px-1 rounded bg-violet-500/15 text-violet-400"
        title={predictions.map(p => `${p.class} ${(p.score * 100).toFixed(0)}%`).join(', ')}>
        ML:{top.class} {(top.score * 100).toFixed(0)}%
      </span>
    )
  }
  if (features.toc_refs?.length > 0) {
    chips.push(
      <span key="toc" className="text-[10px] px-1 rounded bg-sky-500/15 text-sky-400"
        title={features.toc_refs.map(r => r.label).join(', ')}>
        TOC
      </span>
    )
  }
  if (features.note_refs?.length > 0) {
    chips.push(
      <span key="ref" className="text-[10px] px-1 rounded bg-purple-500/15 text-purple-400">
        {features.note_refs.length} ref
      </span>
    )
  }
  return <div className="flex items-center gap-1">{chips}</div>
}
