import { cn } from '@/lib/utils'
import { Button } from '../ui/button.jsx'
import { GaapBadge } from '../ui/badge.jsx'
import { Maximize2 } from 'lucide-react'
import PageWithOverlays from '../PageWithOverlays.jsx'
import { useDocOverlayTables } from '../../api.js'
import { ClassificationBar } from './ClassificationBar.jsx'

/**
 * Page gallery for a single document — GT pages + predicted pages with tagging.
 */
export function DocGallerySection({
  doc,
  selectedType,
  showPredictions,
  showDoclingElements,
  expandedDocs,
  setExpandedDocs,
  localTags,
  savingPage,
  handleQuickTag,
  getSeenPages,
  isDocFullyReviewed,
  markPagesSeen,
  handleToggleReview,
  handleEditSection,
  onPageZoom,
}) {
  const { data: allTables = [] } = useDocOverlayTables(doc.doc_id)
  const docDone = isDocFullyReviewed(doc)
  const gtPageSet = new Set(doc.gtPages || [])
  const gtPageNos = doc.pages.filter(p => gtPageSet.has(p))
  const allPredRanked = showPredictions
    ? (doc.rankedPages || []).filter(r => !gtPageSet.has(r.page))
    : []
  const predLimit = expandedDocs[doc.doc_id] || 5
  const predPageNos = allPredRanked.slice(0, predLimit).map(r => r.page)
  const hasMorePred = allPredRanked.length > predLimit
  const seenPages = getSeenPages(doc)
  const allSeen = seenPages === null
  const isPageSeen = (p) => allSeen || seenPages.has(p)
  const unseenPredCount = predPageNos.filter(p => !isPageSeen(p)).length

  const getPagePredictions = (pageNo) => {
    const rt = doc.rank_tags
    if (!rt?.pages) return null
    const entry = rt.pages[pageNo] || rt.pages[String(pageNo)]
    return entry?.predictions || null
  }

  const renderPage = (pageNo, isPred) => {
    const dims = doc.page_dims[pageNo] || doc.page_dims[String(pageNo)] || { width: 595, height: 842 }
    const tablesOnPage = allTables.filter(t => t.pageNo === pageNo)
    const predictions = getPagePredictions(pageNo)
    const localKey = `${doc.doc_id}:${pageNo}`
    const localTag = localTags[localKey]
    const isLocallyTagged = localTag?.type != null
    const isLocallyRemoved = localTag?.type === null && localTag?.removedFrom
    const pageSeen = isPageSeen(pageNo) && !isLocallyTagged
    const isSaving = savingPage === localKey

    const handleTag = (tagType, removeFrom) => {
      handleQuickTag(doc.doc_id, pageNo, tagType, removeFrom)
    }

    return (
      <div
        key={pageNo}
        className={cn(
          'rounded border-2 overflow-hidden relative shadow-sm',
          isLocallyTagged ? 'border-green-500' :
          isLocallyRemoved ? 'border-destructive' :
          isPred ? 'border-violet-700/40' : 'border-border',
          pageSeen && 'ring-2 ring-inset ring-muted-foreground/20',
        )}
      >
        {/* Zoom button */}
        <Button
          variant="secondary"
          size="icon-sm"
          className="absolute top-1 right-1 z-10 opacity-70 hover:opacity-100"
          onClick={() => onPageZoom && onPageZoom(pageNo)}
          title="Open larger view"
        >
          <Maximize2 className="size-3" />
        </Button>

        {/* Classification pills */}
        <ClassificationBar
          predictions={predictions}
          localTag={localTag}
          selectedType={selectedType}
          isPred={isPred}
          isSaving={isSaving}
          onTag={handleTag}
          compact
        />

        <PageWithOverlays
          docId={doc.doc_id}
          pageNo={pageNo}
          pageDims={dims}
          tables={tablesOnPage}
          showDoclingElements={showDoclingElements}
        />
      </div>
    )
  }

  return (
    <div className="mb-6 border-b border-border pb-4">
      {/* Document header */}
      <div className="flex items-center gap-2 py-1.5 border-b border-border mb-3">
        <span className="text-sm font-semibold text-foreground">{doc.doc_id}</span>
        <GaapBadge gaap={doc.gaap} />
        <span className="text-xs text-muted-foreground">
          {doc.pages.length} page{doc.pages.length !== 1 ? 's' : ''}
          {' \u00b7 '}
          {doc.tables.length} table{doc.tables.length !== 1 ? 's' : ''}
          {' \u00b7 '}
          source: {doc.source}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            variant={docDone ? 'secondary' : 'outline'}
            size="sm"
            className={cn(docDone && 'bg-green-500/15 text-green-500 border-green-500/30')}
            onClick={(e) => { e.stopPropagation(); handleToggleReview(doc.doc_id) }}
            title={docDone ? 'Mark as not reviewed' : 'Mark as fully reviewed'}
          >
            {docDone ? '\u2713 Done' : 'Done'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => { e.stopPropagation(); handleEditSection(doc) }}
            title="Edit page range for this section"
          >
            Edit pages
          </Button>
        </div>
      </div>

      {/* GT pages */}
      {gtPageNos.length > 0 && (
        <>
          {showPredictions && (
            <div className="text-xs font-semibold text-muted-foreground py-2 flex items-center gap-1.5">
              <span className="text-green-500">{'\u25cf'}</span> Ground Truth
              <span className="font-normal text-muted-foreground/60">
                — {gtPageNos.length} page{gtPageNos.length !== 1 ? 's' : ''}
              </span>
            </div>
          )}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
            {gtPageNos.map(p => renderPage(p, false))}
          </div>
          {(() => {
            const unseenGt = gtPageNos.filter(p => !isPageSeen(p))
            return unseenGt.length > 0 ? (
              <Button
                variant="outline"
                size="sm"
                className="w-full mt-2"
                onClick={() => markPagesSeen(doc.doc_id, unseenGt)}
              >
                Mark {unseenGt.length} GT page{unseenGt.length !== 1 ? 's' : ''} as seen
              </Button>
            ) : gtPageNos.length > 0 ? (
              <div className="text-xs text-green-500 py-1">
                {'\u2713'} GT pages seen
              </div>
            ) : null
          })()}
        </>
      )}

      {/* Predicted pages */}
      {predPageNos.length > 0 && (
        <>
          <div className="text-xs font-semibold text-muted-foreground py-2 flex items-center gap-1.5">
            <span className="text-violet-400">{'\u25cf'}</span> Predicted
            <span className="font-normal text-muted-foreground/60">
              — showing {predPageNos.length} of {allPredRanked.length}
            </span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
            {predPageNos.map(p => renderPage(p, true))}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full mt-2"
            onClick={() => {
              const unseenVisible = predPageNos.filter(p => !isPageSeen(p))
              if (unseenVisible.length > 0) {
                markPagesSeen(doc.doc_id, unseenVisible)
              }
              if (hasMorePred) {
                setExpandedDocs(prev => ({
                  ...prev,
                  [doc.doc_id]: predLimit + 5,
                }))
              }
            }}
          >
            {unseenPredCount > 0
              ? `Mark ${unseenPredCount} as seen`
              : '\u2713 all seen'}
            {hasMorePred && ` \u00b7 load 5 more (${allPredRanked.length - predLimit} remaining)`}
          </Button>
        </>
      )}

      {/* Empty states */}
      {showPredictions && predPageNos.length === 0 && gtPageNos.length === 0 && (
        <div className="text-muted-foreground text-xs p-2">
          No predictions available (run rank_pages.py)
        </div>
      )}
      {!showPredictions && gtPageNos.length === 0 && (
        <div className="text-muted-foreground text-xs p-2">No pages</div>
      )}
    </div>
  )
}
