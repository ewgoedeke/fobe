import { useState, useEffect, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Separator } from '../ui/separator.jsx'
import { ChevronLeft, ChevronRight, Minus, Plus, RotateCcw, X } from 'lucide-react'
import PageWithOverlays from '../PageWithOverlays.jsx'
import { useDocOverlayTables } from '../../api.js'
import { ClassificationBar } from './ClassificationBar.jsx'

/**
 * Full-screen page zoom modal with keyboard navigation.
 *
 * Props:
 *   docId, initialPageNo, doc, showDoclingElements,
 *   selectedType, localTags, savingPage, handleQuickTag, onClose
 */
export function PageZoomModal({
  docId,
  initialPageNo,
  doc,
  showDoclingElements,
  selectedType,
  localTags,
  savingPage,
  handleQuickTag,
  onClose,
}) {
  const { data: allTables = [] } = useDocOverlayTables(docId)
  const [scale, setScale] = useState(1)
  const [currentPage, setCurrentPage] = useState(initialPageNo)
  const [pageInput, setPageInput] = useState(String(initialPageNo))
  const containerRef = useRef(null)

  const allPageDims = doc?.page_dims || {}
  const totalPages = doc?.page_count || 0
  const maxPage = totalPages || Math.max(...Object.keys(allPageDims).map(Number), currentPage)
  const pageDims = allPageDims[currentPage] || allPageDims[String(currentPage)] || { width: 595, height: 842 }
  const tablesOnPage = allTables.filter(t => t.pageNo === currentPage)

  const getRankPredictions = useCallback((pageNo) => {
    const rt = doc?.rank_tags
    if (!rt?.pages) return null
    const entry = rt.pages[pageNo] || rt.pages[String(pageNo)]
    return entry?.predictions || null
  }, [doc])

  const predictions = getRankPredictions(currentPage)

  const goToPage = useCallback((p) => {
    const clamped = Math.max(1, Math.min(p, maxPage))
    setCurrentPage(clamped)
    setPageInput(String(clamped))
  }, [maxPage])

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === '+' || e.key === '=') setScale(s => Math.min(s + 0.25, 3))
      if (e.key === '-' && document.activeElement?.tagName !== 'INPUT') setScale(s => Math.max(s - 0.25, 0.5))
      if (e.key === '0' && document.activeElement?.tagName !== 'INPUT') setScale(1)
      if (e.key === 'ArrowLeft') goToPage(currentPage - 1)
      if (e.key === 'ArrowRight') goToPage(currentPage + 1)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, currentPage, goToPage])

  const baseWidth = Math.min(window.innerWidth * 0.85, 900)
  const aspect = pageDims.height / pageDims.width
  const displayWidth = baseWidth * scale
  const displayHeight = displayWidth * aspect

  const localKey = `${docId}:${currentPage}`
  const localTag = localTags?.[localKey]
  const isSaving = savingPage === localKey

  const handleTag = (tagType, removeFrom) => {
    if (!handleQuickTag) return
    handleQuickTag(docId, currentPage, tagType, removeFrom)
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/85 flex flex-col items-center overflow-auto py-5"
    >
      <div
        onClick={e => e.stopPropagation()}
        className="flex flex-col items-center gap-2.5 max-w-[95vw]"
      >
        {/* Control bar */}
        <div className="flex items-center gap-2 bg-card rounded-lg px-4 py-1.5 flex-wrap justify-center border border-border">
          <span className="text-sm font-semibold text-muted-foreground">
            {docId}
          </span>
          <Separator orientation="vertical" className="h-4" />

          {/* Page navigation */}
          <Button
            variant="outline" size="icon-sm"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            title="Previous page (←)"
          >
            <ChevronLeft />
          </Button>
          <span className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">p.</span>
            <Input
              value={pageInput}
              onChange={e => setPageInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') goToPage(parseInt(pageInput) || currentPage) }}
              onBlur={() => goToPage(parseInt(pageInput) || currentPage)}
              className="w-11 h-7 text-center text-xs px-1"
            />
            <span className="text-xs text-muted-foreground">/ {maxPage}</span>
          </span>
          <Button
            variant="outline" size="icon-sm"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= maxPage}
            title="Next page (→)"
          >
            <ChevronRight />
          </Button>

          <Separator orientation="vertical" className="h-4" />

          {/* Zoom controls */}
          <Button variant="outline" size="icon-sm"
            onClick={() => setScale(s => Math.max(s - 0.25, 0.5))}>
            <Minus />
          </Button>
          <span className="text-sm text-muted-foreground tabular-nums min-w-10 text-center">
            {(scale * 100).toFixed(0)}%
          </span>
          <Button variant="outline" size="icon-sm"
            onClick={() => setScale(s => Math.min(s + 0.25, 3))}>
            <Plus />
          </Button>
          <Button variant="outline" size="sm"
            onClick={() => setScale(1)}>
            <RotateCcw className="size-3" />
            Reset
          </Button>

          <Separator orientation="vertical" className="h-4" />

          <Button variant="ghost" size="icon-sm"
            onClick={onClose}
            className="text-destructive hover:text-destructive">
            <X />
          </Button>
        </div>

        {/* Classification bar */}
        <ClassificationBar
          predictions={predictions}
          localTag={localTag}
          selectedType={selectedType}
          isPred={false}
          isSaving={isSaving}
          onTag={handleTag}
        />

        {/* Page render */}
        <div
          ref={containerRef}
          className="shrink-0 rounded overflow-hidden border border-border"
          style={{ width: displayWidth, height: displayHeight }}
        >
          <PageWithOverlays
            key={currentPage}
            docId={docId}
            pageNo={currentPage}
            pageDims={pageDims}
            tables={tablesOnPage}
            showDoclingElements={showDoclingElements}
          />
        </div>

        <div className="text-xs text-muted-foreground py-1 pb-5">
          ←/→ navigate pages · +/− zoom · 0 reset · Esc close · click backdrop to close
        </div>
      </div>
    </div>
  )
}
