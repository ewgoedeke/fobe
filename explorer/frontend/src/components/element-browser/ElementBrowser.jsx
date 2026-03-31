import { useState, useEffect, useCallback } from 'react'
import { Allotment } from 'allotment'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import PageBrowserModal from '../PageBrowserModal.jsx'
import { useElementsBrowse, useGTSets, useDoclingAvailable, useDocRankTags, logTagAction } from '../../api.js'
import { Button } from '../ui/button.jsx'
import { Badge, GaapBadge } from '../ui/badge.jsx'
import { Separator } from '../ui/separator.jsx'
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel,
  SelectTrigger, SelectValue,
} from '../ui/select.jsx'
import { Toggle } from '../ui/toggle.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../ui/table.jsx'
import { Skeleton } from '../ui/skeleton.jsx'
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '../ui/tooltip.jsx'
import {
  ChevronLeft, ChevronRight, Eye, Layers, FileText,
  CheckCircle2, RefreshCw,
} from 'lucide-react'
import {
  TYPE_LABELS, TYPE_ORDER, RANK_CLASSES, TYPE_GROUPS, GROUP_KEYS,
  scoreTextClass, sortTypes, addPageToSections, removePageFromSections,
} from './constants.js'
import { PageZoomModal } from './PageZoomModal.jsx'
import { DocGallerySection } from './DocGallerySection.jsx'

// Score color hex (used only for inline doc-list score display)
const scoreColor = (score) => {
  if (score >= 0.8) return 'text-green-500'
  if (score >= 0.5) return 'text-yellow-500'
  if (score >= 0.3) return 'text-orange-500'
  return 'text-red-500'
}

export default function ElementBrowser() {
  const [selectedType, setSelectedType] = useState('ALL')
  const [activeDocId, setActiveDocId] = useState(null)
  const [editModal, setEditModal] = useState(null)
  const [showDoclingElements, setShowDoclingElements] = useState(false)
  const [showPredictions, setShowPredictions] = useState(false)
  const [expandedDocs, setExpandedDocs] = useState({})
  const [savingPage, setSavingPage] = useState(null)
  const [localTags, setLocalTags] = useState({})
  const [changeCount, setChangeCount] = useState(0)
  const [retraining, setRetraining] = useState(false)
  const [hideReviewed, setHideReviewed] = useState(false)
  const [zoomPage, setZoomPage] = useState(null)
  const [filterGaap, setFilterGaap] = useState('all')
  const [filterGTSet, setFilterGTSet] = useState('all')
  const [minScore, setMinScore] = useState(0)
  const qc = useQueryClient()

  const { data, isLoading: loading } = useElementsBrowse()
  const { data: gtSets = [] } = useGTSets()

  const handleEditSection = useCallback((doc) => {
    const section = {
      statement_type: selectedType,
      start_page: doc.pages[0] || 1,
      end_page: doc.pages[doc.pages.length - 1] || 1,
      label: '',
    }
    setEditModal({
      docId: doc.doc_id,
      pageCount: doc.page_count,
      pageDims: doc.page_dims,
      section,
    })
  }, [selectedType])

  const handleSaveSection = useCallback(async (updated) => {
    const { docId } = editModal
    const res = await fetch(`/api/annotate/${docId}/toc`)
    const existing = await res.json()
    const gt = existing.ground_truth || {
      version: 1, annotator: '', has_page_numbers: false,
      toc_table_id: null, toc_pages: [], sections: [],
      notes_start_page: null, notes_end_page: null, has_toc: true,
    }
    const sections = gt.sections || []
    const idx = sections.findIndex(s => s.statement_type === updated.statement_type)
    const newSection = {
      label: updated.label,
      statement_type: updated.statement_type,
      start_page: updated.start_page,
      end_page: updated.end_page,
      note_number: null,
      validated: true,
    }
    if (idx >= 0) sections[idx] = newSection
    else sections.push(newSection)
    gt.sections = sections
    gt.annotated_at = new Date().toISOString()
    await fetch(`/api/annotate/${docId}/toc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(gt),
    })
    setEditModal(null)
    qc.invalidateQueries({ queryKey: ['elements-browse'] })
  }, [editModal, qc])

  const handleQuickTag = useCallback(async (docId, pageNo, newType, oldType) => {
    const key = `${docId}:${pageNo}`
    if (savingPage === key) return
    setSavingPage(key)
    setLocalTags(prev => ({ ...prev, [key]: { type: newType, removedFrom: oldType } }))
    setChangeCount(c => c + 1)
    try {
      const res = await fetch(`/api/annotate/${docId}/toc`)
      const existing = await res.json()
      const gt = existing.ground_truth || {
        version: 1, annotator: '', has_page_numbers: false,
        toc_table_id: null, toc_pages: [], sections: [],
        notes_start_page: null, notes_end_page: null, has_toc: true,
      }
      let sections = [...(gt.sections || []).map(s => ({ ...s }))]
      if (oldType) sections = removePageFromSections(sections, pageNo, oldType)
      if (newType) sections = addPageToSections(sections, pageNo, newType)
      gt.sections = sections
      gt.annotated_at = new Date().toISOString()
      await fetch(`/api/annotate/${docId}/toc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(gt),
      })
      const action = newType && oldType ? 'reclassify' : newType ? 'add' : 'remove'
      logTagAction({ doc_id: docId, page_no: pageNo, action, element_type: newType, old_type: oldType })
    } finally {
      setSavingPage(null)
    }
  }, [savingPage])

  const handleRetrain = useCallback(async () => {
    setRetraining(true)
    try {
      const res = await fetch('/api/elements/retrain', { method: 'POST' })
      const result = await res.json()
      if (result.status === 'ok') {
        setChangeCount(0)
        setLocalTags({})
        qc.invalidateQueries({ queryKey: ['elements-browse'] })
      } else {
        console.error('Retrain failed:', result.stderr)
      }
    } catch (e) {
      console.error('Retrain error:', e)
    } finally {
      setRetraining(false)
    }
  }, [qc])

  const getSeenPages = useCallback((doc) => {
    const review = doc?.reviews?.[selectedType]
    if (!review) return new Set()
    if (typeof review === 'string') return new Set()
    if (review.all) return null
    return new Set(review.seen_pages || [])
  }, [selectedType])

  const isDocFullyReviewed = useCallback((doc) => {
    const review = doc?.reviews?.[selectedType]
    if (!review) return false
    if (typeof review === 'string') return true
    return !!review.all
  }, [selectedType])

  const markPagesSeen = useCallback(async (docId, pages) => {
    if (GROUP_KEYS.has(selectedType)) return
    await fetch(`/api/elements/review/${docId}/${selectedType}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pages }),
    })
    qc.setQueryData(['elements-browse'], prev => {
      if (!prev) return prev
      return {
        ...prev,
        documents: prev.documents.map(d => {
          if (d.doc_id !== docId) return d
          const reviews = { ...d.reviews }
          const existing = reviews[selectedType] || {}
          const seen = new Set(existing.seen_pages || [])
          pages.forEach(p => seen.add(p))
          reviews[selectedType] = { ...existing, seen_pages: [...seen].sort((a, b) => a - b) }
          return { ...d, reviews }
        }),
      }
    })
  }, [selectedType, qc])

  const handleToggleReview = useCallback(async (docId) => {
    if (GROUP_KEYS.has(selectedType)) return
    const doc = (data?.documents || []).find(d => d.doc_id === docId)
    const reviewed = isDocFullyReviewed(doc)
    if (reviewed) {
      await fetch(`/api/elements/review/${docId}/${selectedType}`, { method: 'DELETE' })
      qc.setQueryData(['elements-browse'], prev => {
        if (!prev) return prev
        return {
          ...prev,
          documents: prev.documents.map(d => {
            if (d.doc_id !== docId) return d
            const reviews = { ...d.reviews }
            delete reviews[selectedType]
            return { ...d, reviews }
          }),
        }
      })
    } else {
      await fetch(`/api/elements/review/${docId}/${selectedType}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      qc.setQueryData(['elements-browse'], prev => {
        if (!prev) return prev
        return {
          ...prev,
          documents: prev.documents.map(d => {
            if (d.doc_id !== docId) return d
            const reviews = { ...d.reviews }
            reviews[selectedType] = { all: true }
            return { ...d, reviews }
          }),
        }
      })
    }
  }, [data, selectedType, isDocFullyReviewed, qc])

  const allDocuments = data?.documents || []

  // Population filter: apply GT set filter BEFORE computing type counts
  const populationDocs = (() => {
    if (filterGTSet === 'all') return allDocuments
    const set = gtSets.find(s => s.id === filterGTSet)
    if (!set?.doc_ids) return allDocuments
    const docIdSet = new Set(set.doc_ids)
    return allDocuments.filter(d => docIdSet.has(d.doc_id))
  })()
  const documents = populationDocs

  const getBestScore = (doc, type) => {
    const rt = doc.rank_tags
    if (!rt?.pages) return 0
    let best = 0
    for (const v of Object.values(rt.pages)) {
      const preds = v.predictions || []
      for (const p of preds) {
        if (p.class === type && p.score > best) best = p.score
      }
    }
    return best
  }

  const getRankedPages = (doc, type) => {
    const rt = doc.rank_tags
    const scoredMap = {}
    if (rt?.pages) {
      for (const [_, v] of Object.entries(rt.pages)) {
        const preds = v.predictions || []
        const match = preds.find(p => p.class === type)
        const score = match ? match.score : 0
        scoredMap[v.page] = { page: v.page, score, predictions: preds }
      }
    }
    for (let p = 1; p <= (doc.page_count || 0); p++) {
      if (!scoredMap[p]) scoredMap[p] = { page: p, score: 0, predictions: [] }
    }
    const scored = Object.values(scoredMap)
    scored.sort((a, b) => b.score - a.score || a.page - b.page)
    return scored
  }

  // Collect all element types with doc counts
  const typeCounts = {}
  for (const doc of documents) {
    for (const etype of Object.keys(doc.elements || {})) {
      const pages = doc.elements[etype]?.pages || []
      if (pages.length > 0) typeCounts[etype] = (typeCounts[etype] || 0) + 1
    }
  }

  // Build grouped type list for dropdown
  const availableTypes = new Set(Object.keys(typeCounts))
  const assignedTypes = new Set()
  const groupedOptions = TYPE_GROUPS.map(group => {
    const items = group.types.filter(t => availableTypes.has(t))
    items.forEach(t => assignedTypes.add(t))
    return { key: group.key, label: group.label, items }
  }).filter(g => g.items.length > 0)

  const discTypes = [...availableTypes].filter(t => t.startsWith('DISC.')).sort()
  discTypes.forEach(t => assignedTypes.add(t))
  if (discTypes.length > 0) {
    groupedOptions.push({ key: 'DISC', label: 'Disclosures', items: discTypes })
  }

  const otherTypes = [...availableTypes].filter(t => !assignedTypes.has(t)).sort()
  if (otherTypes.length > 0) {
    groupedOptions.push({ key: 'OTHER_GROUP', label: 'Other', items: otherTypes })
  }

  // Resolve selected type to a set of active types for filtering
  const groupTypeSet = {}
  for (const g of groupedOptions) {
    groupTypeSet[g.key] = new Set(g.items)
  }
  const activeTypes = selectedType === 'ALL'
    ? null
    : groupTypeSet[selectedType]
      ? groupTypeSet[selectedType]
      : new Set([selectedType])

  const docsWithType = documents.map(doc => {
    // Merge pages/tables from matching element types
    const matchingTypes = activeTypes
      ? Object.keys(doc.elements || {}).filter(t => activeTypes.has(t))
      : Object.keys(doc.elements || {})

    const mergedPages = new Set()
    const mergedTables = []
    for (const etype of matchingTypes) {
      const el = doc.elements[etype]
      for (const p of (el?.pages || [])) mergedPages.add(p)
      for (const t of (el?.tables || [])) mergedTables.push(t)
    }
    const gtPages = [...mergedPages].sort((a, b) => a - b)
    return { ...doc, pages: gtPages, tables: mergedTables, gtPages, bestScore: getBestScore(doc, selectedType), rankedPages: getRankedPages(doc, selectedType) }
  })

  if (showPredictions) {
    docsWithType.sort((a, b) => b.bestScore - a.bestScore)
  }

  const totalSeenPages = documents.reduce((sum, d) => {
    const review = d.reviews?.[selectedType]
    if (!review) return sum
    if (typeof review === 'string') return sum
    if (review.all) {
      const el = d.elements?.[selectedType]
      const gtCount = el?.pages?.length || 0
      const rt = d.rank_tags?.pages
      const totalPages = rt ? Object.keys(rt).length : 0
      return sum + Math.max(gtCount, totalPages)
    }
    return sum + (review.seen_pages?.length || 0)
  }, 0)

  let filteredDocs = docsWithType
  if (filterGaap !== 'all') filteredDocs = filteredDocs.filter(d => d.gaap === filterGaap)
  if (minScore > 0 && showPredictions) filteredDocs = filteredDocs.filter(d => d.bestScore >= minScore / 100)
  if (hideReviewed) filteredDocs = filteredDocs.filter(d => !isDocFullyReviewed(d))
  const reviewedCount = docsWithType.filter(d => isDocFullyReviewed(d)).length

  const activeDocIdx = filteredDocs.findIndex(d => d.doc_id === activeDocId)
  const activeDocRaw = activeDocIdx >= 0 ? filteredDocs[activeDocIdx] : null
  const { data: activeRankTags } = useDocRankTags(activeDocId)
  // Merge lazy-loaded rank_tags into the active doc so gallery/zoom can use it
  const activeDoc = activeDocRaw && activeRankTags
    ? { ...activeDocRaw, rank_tags: activeRankTags }
    : activeDocRaw
  const { data: doclingAvailable = false } = useDoclingAvailable(activeDocId)

  useEffect(() => {
    if (!activeDocId && filteredDocs.length > 0) {
      const first = filteredDocs.find(d => d.pages.length > 0 && d.has_pdf) || filteredDocs[0]
      if (first) setActiveDocId(first.doc_id)
    }
  }, [activeDocId, filteredDocs])

  const goNextDoc = useCallback(() => {
    const idx = filteredDocs.findIndex(d => d.doc_id === activeDocId)
    if (idx >= 0 && idx < filteredDocs.length - 1) setActiveDocId(filteredDocs[idx + 1].doc_id)
  }, [filteredDocs, activeDocId])

  const goPrevDoc = useCallback(() => {
    const idx = filteredDocs.findIndex(d => d.doc_id === activeDocId)
    if (idx > 0) setActiveDocId(filteredDocs[idx - 1].doc_id)
  }, [filteredDocs, activeDocId])

  // (typeCounts, groupedOptions, activeTypes already computed above)

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background text-foreground">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 lg:px-6 py-1.5 border-b border-border shrink-0">
        {/* Population selector */}
        <Select value={filterGTSet} onValueChange={setFilterGTSet}>
          <SelectTrigger className="h-7 w-auto min-w-[120px] text-xs">
            <FileText className="size-3 mr-1 shrink-0 text-muted-foreground" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All documents ({allDocuments.length})</SelectItem>
            {gtSets.map(s => (
              <SelectItem key={s.id} value={s.id}>
                {s.name} ({s.doc_count ?? s.doc_ids?.length ?? 0})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Separator orientation="vertical" className="h-4" />

        {/* Type selector */}
        <Select
          value={selectedType}
          onValueChange={v => { setSelectedType(v); setExpandedDocs({}) }}
        >
          <SelectTrigger className="h-7 w-auto min-w-[160px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All types ({documents.length} docs)</SelectItem>
            {groupedOptions.map(group => {
              const groupDocCount = new Set(documents.filter(d =>
                group.items.some(t => (d.elements?.[t]?.pages || []).length > 0)
              ).map(d => d.doc_id)).size
              return (
                <SelectGroup key={group.key}>
                  <SelectLabel className="flex items-center justify-between">
                    <span>{group.label}</span>
                    <span className="text-[10px] text-muted-foreground font-normal ml-2">{groupDocCount}</span>
                  </SelectLabel>
                  <SelectItem value={group.key} className="font-medium">
                    All {group.label} ({groupDocCount})
                  </SelectItem>
                  {group.items.map(t => (
                    <SelectItem key={t} value={t} className="pl-6">
                      {TYPE_LABELS[t] || t}
                      <span className="text-muted-foreground ml-1">({typeCounts[t]})</span>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )
            })}
          </SelectContent>
        </Select>

        <Separator orientation="vertical" className="h-4" />

        {/* Compact toggles */}
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Toggle
                size="sm"
                variant="outline"
                pressed={showPredictions}
                onPressedChange={setShowPredictions}
              >
                <Eye className="size-3.5" />
                <span className="text-xs">Predictions</span>
              </Toggle>
            </TooltipTrigger>
            <TooltipContent side="bottom">Show ML predictions</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Toggle
                size="sm"
                variant="outline"
                pressed={showDoclingElements}
                onPressedChange={setShowDoclingElements}
                disabled={!doclingAvailable}
                className={!doclingAvailable ? 'opacity-40' : ''}
              >
                <Layers className="size-3.5" />
                <span className="text-xs">Docling</span>
              </Toggle>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              {doclingAvailable ? 'Show Docling elements' : 'No Docling data for this document'}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Toggle
                size="sm"
                variant="outline"
                pressed={hideReviewed}
                onPressedChange={setHideReviewed}
              >
                <CheckCircle2 className="size-3.5" />
                <span className="text-xs">Hide reviewed</span>
              </Toggle>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              {hideReviewed ? 'Showing unreviewed only' : 'Hide fully reviewed docs'}
            </TooltipContent>
          </Tooltip>
        </div>

        {(totalSeenPages > 0 || changeCount > 0) && (
          <div className="flex items-center gap-1.5">
            {totalSeenPages > 0 && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {totalSeenPages} seen
              </Badge>
            )}
            {changeCount > 0 && (
              <Badge className="bg-green-500/15 text-green-500 border-green-500/30 text-[10px] px-1.5 py-0">
                {changeCount} tagged
              </Badge>
            )}
          </div>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={handleRetrain}
          disabled={retraining}
          className="h-7 gap-1.5 text-xs"
        >
          <RefreshCw className={cn('size-3', retraining && 'animate-spin')} />
          Retrain
        </Button>

        {/* Right-aligned filters & nav */}
        <div className="ml-auto flex items-center gap-1.5">
          <Select value={filterGaap} onValueChange={setFilterGaap}>
            <SelectTrigger className="h-7 w-auto min-w-[70px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All GAAP</SelectItem>
              <SelectItem value="IFRS">IFRS</SelectItem>
              <SelectItem value="UGB">UGB</SelectItem>
            </SelectContent>
          </Select>
          {showPredictions && (
            <Select value={String(minScore)} onValueChange={v => setMinScore(Number(v))}>
              <SelectTrigger className="h-7 w-auto min-w-[70px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Min: Any</SelectItem>
                <SelectItem value="10">Min: 10%</SelectItem>
                <SelectItem value="30">Min: 30%</SelectItem>
                <SelectItem value="50">Min: 50%</SelectItem>
                <SelectItem value="80">Min: 80%</SelectItem>
              </SelectContent>
            </Select>
          )}
          <Separator orientation="vertical" className="h-4 mx-0.5" />
          <div className="flex items-center gap-0.5">
            <Button variant="ghost" size="icon-sm"
              disabled={activeDocIdx <= 0}
              onClick={goPrevDoc}>
              <ChevronLeft className="size-3.5" />
            </Button>
            <span className="text-xs text-muted-foreground tabular-nums min-w-[3.5rem] text-center">
              {activeDocIdx >= 0 ? activeDocIdx + 1 : '-'}/{filteredDocs.length}
            </span>
            <Button variant="ghost" size="icon-sm"
              disabled={activeDocIdx >= filteredDocs.length - 1}
              onClick={goNextDoc}>
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
          <span className="text-[11px] text-muted-foreground">
            {filteredDocs.length}/{populationDocs.length} docs
            {reviewedCount > 0 && <span className="text-green-500 ml-1">({reviewedCount} done)</span>}
          </span>
        </div>
      </div>

      {/* Main content */}
      {loading ? (
        <div className="flex-1 flex gap-4 p-4">
          <div className="w-1/4 flex flex-col gap-2">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
          <div className="flex-1 flex flex-wrap gap-4">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-48 w-56 rounded-lg" />)}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <Allotment defaultSizes={[25, 75]}>
            {/* Left: Document list */}
            <Allotment.Pane minSize={200}>
              <div className="h-full overflow-y-auto">
                <Table>
                  <TableHeader className="bg-muted sticky top-0 z-10">
                    <TableRow>
                      <TableHead className="w-6"></TableHead>
                      <TableHead>Document</TableHead>
                      <TableHead>GAAP</TableHead>
                      <TableHead className="text-right">Pages</TableHead>
                      <TableHead className="text-right">Tables</TableHead>
                      {showPredictions && <TableHead className="text-right">Score</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredDocs.map(doc => {
                      const hasPages = doc.pages.length > 0
                      const isActive = doc.doc_id === activeDocId
                      const bestPredScore = showPredictions ? (doc.bestScore || 0) : null
                      const isReviewed = isDocFullyReviewed(doc)
                      return (
                        <TableRow
                          key={doc.doc_id}
                          className={cn(
                            'cursor-pointer',
                            isActive && 'bg-accent',
                            !hasPages && !isReviewed && 'opacity-40',
                            isReviewed && !hasPages && 'opacity-50',
                          )}
                          onClick={() => (hasPages || showPredictions) && doc.has_pdf && setActiveDocId(doc.doc_id)}
                        >
                          <TableCell className="px-1 text-center">
                            <button
                              onClick={e => { e.stopPropagation(); handleToggleReview(doc.doc_id) }}
                              title={isReviewed ? 'Mark as unreviewed' : 'Mark as reviewed'}
                              className={cn(
                                'text-sm leading-none cursor-pointer bg-transparent border-none p-0',
                                isReviewed ? 'text-green-500' : 'text-muted-foreground/30',
                              )}
                            >
                              {isReviewed ? '\u2713' : '\u25cb'}
                            </button>
                          </TableCell>
                          <TableCell className="text-xs max-w-[200px] truncate">{doc.doc_id}</TableCell>
                          <TableCell><GaapBadge gaap={doc.gaap} /></TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {doc.pages.length || '-'}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {doc.tables.length || '-'}
                          </TableCell>
                          {showPredictions && (
                            <TableCell className="text-right">
                              {bestPredScore > 0 ? (
                                <span className={cn('font-semibold text-xs', scoreColor(bestPredScore))}>
                                  {(bestPredScore * 100).toFixed(0)}%
                                </span>
                              ) : '-'}
                            </TableCell>
                          )}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </Allotment.Pane>

            {/* Right: Document gallery */}
            <Allotment.Pane minSize={400}>
              <div className="h-full overflow-y-auto p-4 bg-muted/30">
                {activeDoc && activeDoc.has_pdf ? (
                  <DocGallerySection
                    key={activeDoc.doc_id}
                    doc={activeDoc}
                    selectedType={selectedType}
                    showPredictions={showPredictions}
                    showDoclingElements={showDoclingElements}
                    expandedDocs={expandedDocs}
                    setExpandedDocs={setExpandedDocs}
                    localTags={localTags}
                    savingPage={savingPage}
                    handleQuickTag={handleQuickTag}
                    getSeenPages={getSeenPages}
                    isDocFullyReviewed={isDocFullyReviewed}
                    markPagesSeen={markPagesSeen}
                    handleToggleReview={handleToggleReview}
                    handleEditSection={handleEditSection}
                    onPageZoom={(pageNo) => setZoomPage({
                      docId: activeDoc.doc_id, pageNo, doc: activeDoc,
                    })}
                  />
                ) : (
                  <div className="flex-1 flex items-center justify-center text-muted-foreground h-full">
                    {filteredDocs.length === 0
                      ? `No documents found for ${selectedType}.`
                      : 'Select a document from the list.'}
                  </div>
                )}
              </div>
            </Allotment.Pane>
          </Allotment>
        </div>
      )}

      {/* Page zoom modal */}
      {zoomPage && (
        <PageZoomModal
          docId={zoomPage.docId}
          initialPageNo={zoomPage.pageNo}
          doc={zoomPage.doc}
          showDoclingElements={showDoclingElements}
          selectedType={selectedType}
          localTags={localTags}
          savingPage={savingPage}
          handleQuickTag={handleQuickTag}
          onClose={() => setZoomPage(null)}
        />
      )}

      {/* Page browser modal for editing section page ranges */}
      {editModal && (
        <PageBrowserModal
          docId={editModal.docId}
          pageCount={editModal.pageCount}
          pageDims={editModal.pageDims}
          currentSection={editModal.section}
          onSave={handleSaveSection}
          onClose={() => setEditModal(null)}
        />
      )}
    </div>
  )
}
