import { useState, useMemo } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog.jsx'
import { Button } from '../ui/button.jsx'
import { Badge } from '../ui/badge.jsx'
import PageWithOverlays from '../PageWithOverlays.jsx'
import { useDocOverlayTables } from '../../api.js'
import { ChevronLeft, ChevronRight, Check, X } from 'lucide-react'

/**
 * Side-by-side edge comparison modal.
 * Shows source page + target page from a reference edge, with navigation
 * through all edges and Confirm/Reject actions.
 */
export function SideBySideCompare({
  open,
  onOpenChange,
  docId,
  edges,
  initialEdgeIndex = 0,
  pageDims,
  onConfirmEdge,
  onRejectEdge,
}) {
  const [currentIndex, setCurrentIndex] = useState(initialEdgeIndex)
  const edge = edges?.[currentIndex]

  const { data: allTables = [] } = useDocOverlayTables(docId, open)

  const sourceTables = useMemo(
    () => edge ? allTables.filter(t => t.pageNo === edge.source_page) : [],
    [allTables, edge],
  )
  const targetTables = useMemo(
    () => edge ? allTables.filter(t => t.pageNo === edge.target_page) : [],
    [allTables, edge],
  )

  const sourceDims = edge
    ? (pageDims?.[edge.source_page] || pageDims?.[String(edge.source_page)] || { width: 595, height: 842 })
    : { width: 595, height: 842 }
  const targetDims = edge
    ? (pageDims?.[edge.target_page] || pageDims?.[String(edge.target_page)] || { width: 595, height: 842 })
    : { width: 595, height: 842 }

  const hasPrev = currentIndex > 0
  const hasNext = edges && currentIndex < edges.length - 1

  if (!edge) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[85vh] flex flex-col p-0 gap-0">
        {/* Header */}
        <DialogHeader className="px-4 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            <DialogTitle className="text-sm font-semibold">
              Edge Compare
            </DialogTitle>
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              {currentIndex + 1} / {edges.length}
            </Badge>
            {edge.edge_type && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {edge.edge_type}
              </Badge>
            )}
            {edge.label && (
              <span className="text-xs text-muted-foreground truncate max-w-[300px]">
                {edge.label}
              </span>
            )}
          </div>
        </DialogHeader>

        {/* Side-by-side pages */}
        <div className="flex-1 min-h-0 flex gap-2 p-3">
          {/* Source page */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="text-[11px] font-medium text-muted-foreground mb-1 flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-sky-500 shrink-0" />
              Source — p.{edge.source_page}
            </div>
            <div className="flex-1 min-h-0 overflow-auto rounded border border-border bg-muted/30">
              <PageWithOverlays
                docId={docId}
                pageNo={edge.source_page}
                pageDims={sourceDims}
                tables={sourceTables}
                showDoclingElements={false}
              />
            </div>
          </div>

          {/* Target page */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="text-[11px] font-medium text-muted-foreground mb-1 flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-purple-500 shrink-0" />
              Target — {edge.target_page ? `p.${edge.target_page}` : (edge.target_context || edge.target_id || 'unknown')}
            </div>
            <div className="flex-1 min-h-0 overflow-auto rounded border border-border bg-muted/30">
              {edge.target_page ? (
                <PageWithOverlays
                  docId={docId}
                  pageNo={edge.target_page}
                  pageDims={targetDims}
                  tables={targetTables}
                  showDoclingElements={false}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                  <div className="text-center">
                    <div className="font-medium">{edge.target_context || edge.target_id}</div>
                    <div className="text-xs mt-1">Note {edge.note_number}</div>
                    <div className="text-xs text-muted-foreground/60 mt-0.5">Page not annotated yet</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer with navigation + actions */}
        <DialogFooter className="px-4 py-2.5 border-t border-border shrink-0 flex-row items-center justify-between sm:justify-between">
          {/* Navigation */}
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={() => setCurrentIndex(i => i - 1)}
              disabled={!hasPrev}
            >
              <ChevronLeft className="size-3" />
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={() => setCurrentIndex(i => i + 1)}
              disabled={!hasNext}
            >
              Next
              <ChevronRight className="size-3" />
            </Button>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 text-red-400 border-red-500/30 hover:bg-red-500/10"
              onClick={() => {
                onRejectEdge?.(edge)
                if (hasNext) setCurrentIndex(i => i + 1)
              }}
            >
              <X className="size-3" />
              Reject
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 text-green-400 border-green-500/30 hover:bg-green-500/10"
              onClick={() => {
                onConfirmEdge?.(edge)
                if (hasNext) setCurrentIndex(i => i + 1)
              }}
            >
              <Check className="size-3" />
              Confirm
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
