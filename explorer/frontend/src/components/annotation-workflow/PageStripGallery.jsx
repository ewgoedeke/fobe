import { useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { ALL_SECTION_TYPES } from '../section-hierarchy.js'

/**
 * Responsive grid of page thumbnails with colored left border and feature badges.
 * Uses /api/page-image/{doc_id}/{page} for thumbnails.
 */
export function PageStripGallery({
  docId,
  totalPages,
  pageMap,
  pageFeatures,
  selectedPage,
  onPageClick,
}) {
  const selectedRef = useRef(null)

  // Scroll selected page into view
  useEffect(() => {
    if (selectedRef.current) {
      selectedRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [selectedPage])

  if (!totalPages || !docId) return null

  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-2">
        {Array.from({ length: totalPages }, (_, i) => {
          const page = i + 1
          const info = pageMap.get(page)
          const typeMeta = info ? ALL_SECTION_TYPES[info.type] : null
          const isSelected = page === selectedPage
          const features = pageFeatures?.pages?.[page] || pageFeatures?.pages?.[String(page)]

          return (
            <div
              key={page}
              ref={isSelected ? selectedRef : null}
              className={cn(
                'relative rounded overflow-hidden cursor-pointer border bg-muted',
                isSelected
                  ? 'ring-2 ring-primary border-primary'
                  : 'border-border hover:border-muted-foreground/50',
              )}
              style={{
                borderLeftWidth: 3,
                borderLeftColor: typeMeta?.hex || 'transparent',
              }}
              onClick={() => onPageClick(page)}
            >
              {/* Thumbnail */}
              <div className="aspect-[0.707] relative">
                <img
                  src={`/api/page-image/${docId}/${page}`}
                  alt={`Page ${page}`}
                  loading="lazy"
                  className="absolute inset-0 w-full h-full object-contain"
                />
              </div>

              {/* Page number + badges */}
              <div className="absolute bottom-0 left-0 right-0 flex items-center gap-1 px-1.5 py-0.5 bg-background/80 backdrop-blur-sm">
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {page}
                </span>
                {info && (
                  <span
                    className="text-[10px] font-medium truncate"
                    style={{ color: typeMeta?.hex }}
                  >
                    {info.type}
                    {info.noteNumber && ` n.${info.noteNumber}`}
                  </span>
                )}
                <div className="ml-auto flex items-center gap-0.5">
                  <FeatureBadges features={features} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FeatureBadges({ features }) {
  if (!features) return null

  const badges = []
  const predictions = features.predictions || []
  if (predictions.length > 0) {
    const top = predictions[0]
    badges.push(
      <span
        key="ml"
        className="text-[10px] font-medium px-1 rounded bg-violet-500/15 text-violet-400"
        title={`ML: ${top.class} (${(top.score * 100).toFixed(0)}%)`}
      >
        ML
      </span>
    )
  }
  if (features.toc_refs?.length > 0) {
    badges.push(
      <span
        key="toc"
        className="text-[10px] font-medium px-1 rounded bg-sky-500/15 text-sky-400"
        title={`TOC: ${features.toc_refs.map(r => r.label).join(', ')}`}
      >
        TOC
      </span>
    )
  }
  if (features.note_refs?.length > 0) {
    badges.push(
      <span
        key="ref"
        className="text-[10px] font-medium px-1 rounded bg-purple-500/15 text-purple-400"
        title={`Note refs: ${features.note_refs.length}`}
      >
        REF
      </span>
    )
  }

  return badges
}
